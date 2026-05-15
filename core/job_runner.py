"""
core/job_runner.py

Runs the full transcription pipeline:
  audio file -> normalize -> chunk -> transcribe -> assemble -> save

Called from ui/tab_transcribe.py in a background thread.

Phase A note
------------
The immutable raw-response save (``pipeline.raw_store.save_raw_response``)
now receives full forensic provenance: the post-validation Deepgram
request parameters and the post-sanitization keyterm list. Both come
out of the first chunk's transcribe result, which is representative
because every chunk in a single run uses the same params and keyterms.

Failure policy for the raw-store save is fail-soft at the orchestrator
level: a filesystem error here is logged at ERROR severity and recorded
in the output JSON (``raw_store_failure``), but the run continues so
that the merged transcript and the legacy ``raw_deepgram.json`` are
still produced. Module-level errors propagate per the raw_store
contract; the policy choice to continue is made here.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from config import DEFAULT_KEYTERMS, LOW_CONFIDENCE_THRESHOLD
from core.file_manager import resolve_or_create_case


def _build_transcript_from_utterances(utterances: list[dict]) -> str:
    lines: list[str] = []
    for utterance in utterances or []:
        speaker = (
                utterance.get("speaker_label") or f"Speaker {utterance.get('speaker', 0)}"
        )
        text = (utterance.get("transcript") or "").strip()
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n\n".join(lines)


def _safe_write_text(path: Path, content: str, log) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log(f"[SAVE SUCCESS] {path}")
    except Exception as exc:
        log(f"[SAVE ERROR] {path} -> {exc}")
        raise


def _safe_write_json(path: Path, payload: dict, log) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        log(f"[SAVE SUCCESS] {path}")
    except Exception as exc:
        log(f"[SAVE ERROR] {path} -> {exc}")
        raise


def _validate_assembled_result(assembled: dict) -> None:
    if not assembled.get("utterances"):
        raise RuntimeError("No utterances returned from Deepgram")
    if len(assembled.get("words", [])) == 0:
        raise RuntimeError("No words returned from Deepgram")


def _build_chunk_summaries(chunks: list) -> list[dict]:
    summaries: list[dict] = []
    for chunk in chunks:
        summaries.append(
            {
                "file_path": getattr(chunk, "file_path", ""),
                "start_seconds": getattr(chunk, "start_seconds", 0.0),
                "end_seconds": getattr(chunk, "end_seconds", 0.0),
            }
        )
    return summaries


def _extract_request_provenance(
        chunk_results: list[dict],
        fallback_keyterms: list[str],
) -> tuple[dict, list[str]]:
    """Pull Phase A provenance out of the first successful chunk result.

    Every chunk in a single run is sent with the same parameters and
    keyterm list, so chunk[0] is representative. If for any reason the
    expected keys are missing (older transcriber on disk, silence-skip
    path that returned an empty result, etc.), we fall back to empty
    params and the upstream-merged keyterm list — the saved record
    will still parse, and the absence will be visible to a forensic
    reader.
    """
    if not chunk_results:
        return {}, list(fallback_keyterms or [])

    first = chunk_results[0] if isinstance(chunk_results[0], dict) else {}
    params = first.get("deepgram_request_params") or {}
    keyterms = first.get("keyterms_sent")
    if keyterms is None:
        keyterms = list(fallback_keyterms or [])
    return params, list(keyterms)


def run_transcription_job(
        audio_path: str,
        model: str,
        quality: str,
        base_dir: str,
        cause_number: str = "",
        last_name: str = "",
        first_name: str = "",
        date_str: str = "",
        keyterms: list = None,
        confirmed_spellings: dict | None = None,
        ufm_fields: dict = None,
        progress_callback=None,
        log_callback=None,
        done_callback=None,
        allow_cause_mismatch_reuse: bool = False,
):
    """
    Run the full pipeline. Calls callbacks for UI updates.
    Must be called in a background thread.
    """

    def _progress(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    def _log(msg):
        if log_callback:
            log_callback(msg)

    def _done(result):
        if done_callback:
            done_callback(result)

    CONFIDENCE_LOW = LOW_CONFIDENCE_THRESHOLD

    # Tracked so that if anything after chunk_audio() raises, we can still
    # clean up the temp WAV files in the except block.
    chunks: list | None = None

    # Phase A: if the immutable raw-store save fails, we surface it in
    # both the main JSON and the raw JSON outputs so downstream
    # consumers can detect the forensic gap. ``None`` means success.
    raw_store_failure: str | None = None

    try:
        from pipeline.preprocessor import (
            validate_audio_file,
            normalize_audio,
            QUALITY_CONFIGS,
            AUTO_DETECT_KEY,
            check_ffmpeg,
        )
        from pipeline.chunker import chunk_audio, cleanup_chunks
        from pipeline.transcriber import transcribe_chunk
        from pipeline.assembler import reassemble_chunks
        from pipeline.audio_quality import analyze_audio
        from pipeline.vad_trimmer import trim_silence
        from core.job_config_manager import merge_and_save

        _progress(2, "Checking FFmpeg…")
        if not check_ffmpeg():
            raise RuntimeError(
                "FFmpeg is not installed or not on PATH.\n"
                "Download from https://ffmpeg.org and add to Windows PATH."
            )

        _progress(5, "Validating audio file…")
        v = validate_audio_file(audio_path)
        if not v["valid"]:
            raise ValueError(v["error"])
        duration_min = v["duration"] / 60
        _log(f"File valid: {v['format'].upper()}  {duration_min:.1f} minutes")

        from pipeline.transcriber import trim_keyterms_for_deepgram

        merged_keyterms = list(dict.fromkeys((keyterms or []) + DEFAULT_KEYTERMS))
        if merged_keyterms:
            _log(f"Deepgram keyterms: {len(merged_keyterms)} (includes defaults)")
            merged_keyterms, kt_stats = trim_keyterms_for_deepgram(merged_keyterms)
            _log(
                f"Sending {kt_stats['sent']} keyterms to Deepgram "
                f"(~{kt_stats['used_tokens']}/{kt_stats['budget']} tokens)"
            )
            if kt_stats["dropped_oversize"]:
                examples = ", ".join(
                    repr(s[:60] + ("..." if len(s) > 60 else ""))
                    for s in kt_stats["oversize_examples"]
                )
                _log(
                    f"  Dropped {kt_stats['dropped_oversize']} oversize keyterms "
                    f"(>{kt_stats['max_entry_chars']} chars, likely form-template "
                    f"noise): {examples}"
                )
            if kt_stats["dropped_budget"]:
                _log(
                    f"  Dropped {kt_stats['dropped_budget']} keyterms to fit "
                    f"the {kt_stats['budget']}-token budget"
                )
        else:
            merged_keyterms = []

        case_path, folder_status = resolve_or_create_case(
            base_dir,
            cause_number,
            last_name,
            first_name,
            date_str,
            allow_cause_mismatch_reuse=allow_cause_mismatch_reuse,
        )
        if folder_status["errors"]:
            raise RuntimeError(
                f"Failed to create required case folders: {folder_status['errors']}"
            )
        if folder_status["created"]:
            _log(f"Created folders: {folder_status['created']}")

        _progress(8, "Analyzing audio quality…")
        analysis = analyze_audio(audio_path)
        _log(
            f"Audio tier: {analysis.tier}  "
            f"Stereo: {analysis.is_stereo}  "
            f"Zoom-dual-mono: {analysis.zoom_dual_mono}"
        )
        for issue in analysis.issues:
            _log(f"  → {issue}")

        if quality == AUTO_DETECT_KEY:
            tier_map = {
                "CLEAN": "CLEAN (good/excellent audio)",
                "ENHANCED": "ENHANCED (fair audio)",
                "RESCUE": "RESCUE (noisy/poor audio)",
            }
            quality = tier_map.get(analysis.tier, "ENHANCED (fair audio)")

        quality_cfg = QUALITY_CONFIGS.get(quality)
        if quality_cfg is None:
            from pipeline.preprocessor import ENHANCED_CONFIG

            quality_cfg = ENHANCED_CONFIG
            _log(f"Unknown quality '{quality}' — using ENHANCED")
        else:
            _log(f"Preprocessing tier: {quality_cfg['description']}")

        _progress(10, "Normalizing audio…")
        normalized_path = normalize_audio(
            audio_path,
            config=quality_cfg,
            auto_detect=False,
            audio_analysis=analysis,
            progress_callback=_log,
        )
        _log(f"Normalized: {os.path.basename(normalized_path)}")

        if quality_cfg.get("noisereduce"):
            _progress(15, "Applying conservative noise reduction…")
            try:
                import noisereduce as nr
                import soundfile as sf

                audio_data, sample_rate = sf.read(normalized_path)
                if getattr(audio_data, "ndim", 1) > 1:
                    audio_data = audio_data.mean(axis=1)
                reduced = nr.reduce_noise(
                    y=audio_data,
                    sr=sample_rate,
                    stationary=True,
                    prop_decrease=0.5,
                )
                sf.write(normalized_path, reduced, sample_rate)
                _log("Noise reduction applied (stationary, prop_decrease=0.5)")
            except Exception as nr_exc:
                _log(f"Noise reduction skipped: {nr_exc}")

        _progress(18, "Trimming silence…")
        try:
            vad_out = normalized_path.replace(".wav", "_vad.wav")
            trim_result = trim_silence(normalized_path, output_path=vad_out)
            if trim_result.was_trimmed:
                normalized_path = trim_result.output_path
                _log(
                    f"Silence trimmed: {trim_result.original_duration_s:.1f}s → "
                    f"{trim_result.trimmed_duration_s:.1f}s "
                    f"({trim_result.silence_removed_s:.1f}s removed, "
                    f"{trim_result.speech_segment_count} speech segments)"
                )
        except Exception as vad_exc:
            _log(f"VAD trim skipped: {vad_exc}")

        from config import PLAYGROUND_MODE

        if PLAYGROUND_MODE:
            from pipeline.chunker import AudioChunk

            _log(
                "PLAYGROUND_MODE on — single-request, no chunking, no preprocessing"
            )
            chunks = [
                AudioChunk(
                    index=0,
                    file_path=normalized_path,
                    start_seconds=0.0,
                    end_seconds=float(v["duration"]),
                    duration_seconds=float(v["duration"]),
                    overlap_seconds=0.0,
                )
            ]
        else:
            _progress(20, "Splitting into chunks…")
            chunks = chunk_audio(
                normalized_path,
                total_duration=v["duration"],
                progress_callback=_log,
            )
        _log(f"Split into {len(chunks)} chunk(s)")

        chunk_results = []
        chunk_offsets = []
        for i, chunk in enumerate(chunks):
            pct = 22 + int((i / max(1, len(chunks))) * 58)
            _progress(pct, f"Transcribing chunk {i + 1} of {len(chunks)}…")
            _log(
                f"Chunk {i + 1}/{len(chunks)}: {chunk.start_seconds:.0f}s – {chunk.end_seconds:.0f}s"
            )
            result = transcribe_chunk(
                chunk.file_path,
                model=model,
                keyterms=merged_keyterms,
                progress_callback=_log,
            )
            chunk_results.append(result)
            chunk_offsets.append(chunk.start_seconds)
            _log(
                f"Chunk {i + 1} data: "
                f"{len(result.get('utterances', []))} utterances, "
                f"{len(result.get('words', []))} words"
            )

        # Phase A — immutable raw store. Writes the unmutated per-chunk
        # Deepgram responses to a timestamped read-only JSON BEFORE
        # any cross-chunk merge / smoothing / speaker-remap runs.
        #
        # Provenance pulled from chunk_results[0]: every chunk in a
        # single run uses the same params and keyterms list, so the
        # first chunk's snapshot is representative.
        #
        # Failure policy: only filesystem/write failures are fail-soft.
        # Contract/data errors from raw_store (for example the explicit
        # length-mismatch ValueError) must abort so a broken forensic
        # anchor cannot be silently downgraded into a "successful" run.
        try:
            from pipeline.raw_store import save_raw_response

            dg_request_params, dg_keyterms_sent = _extract_request_provenance(
                chunk_results,
                fallback_keyterms=merged_keyterms,
            )

            _raw_store_result = save_raw_response(
                case_path,
                chunk_results=chunk_results,
                chunk_offsets=chunk_offsets,
                audio_file=audio_path,
                model=model,
                request_params=dg_request_params,
                keyterms=dg_keyterms_sent,
            )
            _log(
                f"[VALIDATION] [RAW RESPONSE SAVED] {_raw_store_result.path.name} "
                f"(chunks={_raw_store_result.chunk_count}, "
                f"keyterms={len(dg_keyterms_sent)})"
            )
        except (FileExistsError, OSError) as raw_store_exc:
            raw_store_failure = f"{type(raw_store_exc).__name__}: {raw_store_exc}"
            _log(
                f"[ERROR] [RAW_STORE] Immutable raw-response save FAILED: "
                f"{raw_store_failure}. Run continues; legacy raw save "
                f"will still be attempted, but forensic regression-"
                f"comparison may be impossible for this run."
            )

        _log("[VALIDATION] [TRANSCRIPT MUTATION BEGINS] cross-chunk assembler about to run")
        _progress(82, "Assembling transcript…")
        assembled = reassemble_chunks(chunk_results, chunk_offsets)
        _validate_assembled_result(assembled)

        word_count = len(assembled.get("words", []))
        utterance_count = len(assembled.get("utterances", []))
        raw_utterance_count = len(assembled.get("raw_utterances", []))
        _log(f"Assembled: {word_count} words, {utterance_count} utterances")
        _log(f"Raw utterances: {raw_utterance_count}")
        _log(f"Chunks: {len(chunks)}")

        _progress(90, "Building output files…")

        # Prefer the transcript text reconstructed from Deepgram word order so
        # app output stays aligned with Playground-style readability.
        transcript_text = (assembled.get("transcript") or "").strip()
        if not transcript_text:
            transcript_text = _build_transcript_from_utterances(
                assembled.get("utterances", [])
            )
        if not transcript_text.strip():
            raise RuntimeError("Transcript text could not be built from utterances")

        _progress(95, "Saving files…")
        out_dir = Path(case_path)
        deepgram_dir = out_dir / "Deepgram"
        deepgram_dir.mkdir(parents=True, exist_ok=True)

        base_name = Path(audio_path).stem[:40]
        txt_path = deepgram_dir / f"{base_name}.txt"
        json_path = deepgram_dir / f"{base_name}.json"
        raw_txt_path = deepgram_dir / f"{base_name}_raw.txt"
        canonical_raw_txt_path = deepgram_dir / "raw_deepgram.txt"

        _safe_write_text(txt_path, transcript_text, _log)

        raw_transcript_text = _build_transcript_from_utterances(
            assembled.get("raw_utterances", assembled.get("utterances", []))
        )
        if not raw_transcript_text.strip():
            raise RuntimeError(
                "Raw transcript text could not be built from Deepgram utterances"
            )
        _safe_write_text(raw_txt_path, raw_transcript_text, _log)
        _safe_write_text(canonical_raw_txt_path, raw_transcript_text, _log)

        # Optional walkthrough capture (no-op when WALKTHROUGH_CAPTURE unset).
        from tools.walkthrough import capture_stage
        capture_stage(out_dir, "01_deepgram_raw", raw_transcript_text)

        json_data = {
            "audio_file": audio_path,
            "model": model,
            "audio_quality": quality,
            "audio_tier": analysis.tier if analysis else "",
            "created_at": datetime.now().isoformat(),
            "duration_sec": v["duration"],
            "word_count": word_count,
            "utterance_count": utterance_count,
            "chunk_count": len(chunks),
            "deepgram_keyterms_used": merged_keyterms,
            "raw_store_failure": raw_store_failure,
            "transcript": transcript_text,
            "chunk_summaries": _build_chunk_summaries(chunks),
            "utterances": assembled.get("utterances", []),
            "raw_utterances": assembled.get("raw_utterances", []),
            "words": assembled.get("words", []),
        }
        _safe_write_json(json_path, json_data, _log)

        raw_json_path = deepgram_dir / f"{base_name}_raw.json"
        raw_data = {
            "audio_file": audio_path,
            "model": model,
            "audio_quality": quality,
            "audio_tier": analysis.tier if analysis else "",
            "created_at": datetime.now().isoformat(),
            "chunk_count": len(chunks),
            "deepgram_keyterms_used": merged_keyterms,
            "raw_store_failure": raw_store_failure,
            "transcript": raw_transcript_text,
            "chunk_summaries": _build_chunk_summaries(chunks),
            "utterances": assembled.get("utterances", []),
            "raw_utterances": assembled.get("raw_utterances", []),
            "words": assembled.get("words", []),
            "chunks": assembled.get("raw_chunks", []),
        }
        _safe_write_json(raw_json_path, raw_data, _log)
        _safe_write_json(deepgram_dir / "raw_deepgram.json", raw_data, _log)

        raw_words = assembled.get("words", [])
        low_conf_words = [
            {
                "word": w.get("word", ""),
                "confidence": round(float(w.get("confidence", 1.0)), 4),
                "start": w.get("start", 0.0),
                "end": w.get("end", 0.0),
            }
            for w in raw_words
            if isinstance(w, dict) and float(w.get("confidence", 1.0)) < CONFIDENCE_LOW
        ]
        if low_conf_words:
            _log(f"Low-confidence words: {len(low_conf_words)}")

        job_config_path = merge_and_save(
            str(out_dir),
            # Pass None when empty so merge_and_save preserves the existing
            # values rather than overwriting them with empty dicts/lists.
            model=model,
            audio_quality=quality,
            ufm_fields=ufm_fields if ufm_fields else None,
            confirmed_spellings=confirmed_spellings if confirmed_spellings else None,
            low_confidence_words=low_conf_words if low_conf_words else None,
            # Phase 2 audit fix: persist the post-trim merged list that
            # was actually sent to Deepgram, not the pre-trim input
            # `keyterms`. This keeps job_config.json's audit trail
            # honest about what reached the API.
            deepgram_keyterms=merged_keyterms if merged_keyterms else None,
        )
        _log("Saved job_config.json → source_docs/")

        cleanup_chunks(chunks)
        chunks = None  # prevent double-cleanup in the except block below

        _progress(100, "Complete ✓")
        _log(f"✓ Transcription complete — {word_count} words")
        _log(f"Output folder: {out_dir}")

        _done(
            {
                "success": True,
                "transcript_path": str(txt_path),
                "json_path": str(json_path),
                "raw_json_path": str(raw_json_path),
                "raw_txt_path": str(raw_txt_path),
                "job_config_path": str(job_config_path) if job_config_path else None,
                "output_dir": str(out_dir),
                "transcript_text": transcript_text,
                "audio_tier": analysis.tier if analysis else "",
                "raw_store_failure": raw_store_failure,
                "error": None,
            }
        )

    except Exception as exc:
        _log(f"ERROR: {exc}")
        _progress(0, "Failed")

        # Clean up any chunk temp files created before the failure. Without
        # this, every failed run leaks its chunk WAVs to disk.
        if chunks:
            try:
                from pipeline.chunker import cleanup_chunks

                cleanup_chunks(chunks)
                _log("Cleaned up temp chunk files after error")
            except Exception as cleanup_exc:
                _log(f"Chunk cleanup failed: {cleanup_exc}")

        _done(
            {
                "success": False,
                "transcript_path": None,
                "json_path": None,
                "transcript_text": "",
                "error": str(exc),
            }
        )
