"""
core/job_runner.py

Runs the full transcription pipeline:
  audio file -> normalize -> chunk -> transcribe -> assemble -> save

Called from ui/tab_transcribe.py in a background thread.
"""

import json
import os
from pathlib import Path
from datetime import datetime

from config import DEFAULT_KEYTERMS

from core.file_manager import resolve_or_create_case


def _build_transcript_from_utterances(utterances: list[dict]) -> str:
    lines: list[str] = []
    for utterance in utterances or []:
        speaker = utterance.get("speaker_label") or f"Speaker {utterance.get('speaker', 0)}"
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


def _transcribe_prepared_audio(
    prepared_audio_path: str,
    *,
    duration_seconds: float,
    model: str,
    utt_split: float,
    keyterms: list[str],
    progress,
    log,
    transcribe_chunk,
    chunk_audio,
    reassemble_chunks,
    channel_label: str = "",
):
    chunks = chunk_audio(
        prepared_audio_path,
        total_duration=duration_seconds,
        progress_callback=log,
    )
    prefix = f"{channel_label} " if channel_label else ""
    log(f"{prefix}split into {len(chunks)} chunk(s)")

    chunk_results = []
    chunk_offsets = []

    for i, chunk in enumerate(chunks):
        pct = 22 + int((i / max(1, len(chunks))) * 58)
        progress(pct, f"Transcribing {prefix.lower()}chunk {i+1} of {len(chunks)}…".strip())
        log(f"{prefix}chunk {i+1}/{len(chunks)}: {chunk.start_seconds:.0f}s – {chunk.end_seconds:.0f}s")

        try:
            result = transcribe_chunk(
                chunk.file_path,
                model=model,
                utt_split=utt_split,
                keyterms=keyterms,
                progress_callback=log,
            )
            chunk_results.append(result)
            chunk_offsets.append(chunk.start_seconds)
            log(f"{prefix}chunk {i+1} OK")
        except Exception as chunk_exc:
            log(
                f"ERROR: {prefix}chunk {i+1}/{len(chunks)} failed "
                f"({chunk.start_seconds:.0f}s–{chunk.end_seconds:.0f}s): {chunk_exc}"
            )
            raise

    return reassemble_chunks(chunk_results, chunk_offsets), chunks


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


def run_transcription_job(
    audio_path: str,
    model: str,
    quality: str,
    utt_split: float,
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

    try:
        from pipeline.preprocessor import (
            validate_audio_file, normalize_audio,
            QUALITY_CONFIGS, AUTO_DETECT_KEY, check_ffmpeg,
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

        merged_keyterms = list(dict.fromkeys((keyterms or []) + DEFAULT_KEYTERMS))
        _log(f"Utterance split: {utt_split:.2f}")
        if merged_keyterms:
            _log(f"Deepgram keyterms: {len(merged_keyterms)} (includes defaults)")

        case_path, folder_status = resolve_or_create_case(
            base_dir,
            cause_number,
            last_name,
            first_name,
            date_str,
        )
        if folder_status["errors"]:
            raise RuntimeError(f"Failed to create required case folders: {folder_status['errors']}")
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
            _progress(pct, f"Transcribing chunk {i+1} of {len(chunks)}…")
            _log(f"Chunk {i+1}/{len(chunks)}: {chunk.start_seconds:.0f}s – {chunk.end_seconds:.0f}s")
            result = transcribe_chunk(
                chunk.file_path,
                model=model,
                utt_split=utt_split,
                keyterms=merged_keyterms,
                progress_callback=_log,
            )
            chunk_results.append(result)
            chunk_offsets.append(chunk.start_seconds)
            _log(
                f"Chunk {i+1} data: "
                f"{len(result.get('utterances', []))} utterances, "
                f"{len(result.get('words', []))} words"
            )

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

        transcript_text = _build_transcript_from_utterances(assembled.get("utterances", []))
        if not transcript_text.strip():
            raise RuntimeError("Transcript text could not be built from utterances")

        _progress(95, "Saving files…")
        out_dir = Path(case_path)
        deepgram_dir = out_dir / "Deepgram"
        deepgram_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = Path(audio_path).stem[:40]
        txt_name = f"{base_name}_{stamp}.txt"
        json_name = f"{base_name}_{stamp}.json"

        txt_path = deepgram_dir / txt_name
        json_path = deepgram_dir / json_name
        raw_txt_path = deepgram_dir / f"{base_name}_{stamp}_raw.txt"

        _safe_write_text(txt_path, transcript_text, _log)

        raw_transcript_text = _build_transcript_from_utterances(
            assembled.get("raw_utterances", assembled.get("utterances", []))
        )
        if not raw_transcript_text.strip():
            raise RuntimeError("Raw transcript text could not be built from Deepgram utterances")
        _safe_write_text(raw_txt_path, raw_transcript_text, _log)

        json_data = {
            "audio_file": audio_path,
            "model": model,
            "audio_quality": quality,
            "audio_tier": analysis.tier if analysis else "",
            "utt_split": utt_split,
            "created_at": datetime.now().isoformat(),
            "duration_sec": v["duration"],
            "word_count": word_count,
            "utterance_count": utterance_count,
            "chunk_count": len(chunks),
            "deepgram_keyterms_used": merged_keyterms,
            "transcript": transcript_text,
            "chunk_summaries": _build_chunk_summaries(chunks),
            "utterances": assembled.get("utterances", []),
            "raw_utterances": assembled.get("raw_utterances", []),
            "words": assembled.get("words", []),
        }
        _safe_write_json(json_path, json_data, _log)

        raw_json_path = deepgram_dir / f"{base_name}_{stamp}_raw.json"
        raw_data = {
            "audio_file": audio_path,
            "model": model,
            "audio_quality": quality,
            "audio_tier": analysis.tier if analysis else "",
            "utt_split": utt_split,
            "created_at": datetime.now().isoformat(),
            "chunk_count": len(chunks),
            "deepgram_keyterms_used": merged_keyterms,
            "transcript": raw_transcript_text,
            "chunk_summaries": _build_chunk_summaries(chunks),
            "utterances": assembled.get("utterances", []),
            "raw_utterances": assembled.get("raw_utterances", []),
            "words": assembled.get("words", []),
            "chunks": assembled.get("raw_chunks", []),
        }
        _safe_write_json(raw_json_path, raw_data, _log)

        from core.word_data_loader import CONFIDENCE_LOW
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
            utt_split=utt_split,
            ufm_fields=ufm_fields if ufm_fields else None,
            confirmed_spellings=confirmed_spellings if confirmed_spellings else None,
            low_confidence_words=low_conf_words if low_conf_words else None,
            deepgram_keyterms=keyterms if keyterms else None,
        )
        _log("Saved job_config.json → source_docs/")

        cleanup_chunks(chunks)

        _progress(100, "Complete ✓")
        _log(f"✓ Transcription complete — {word_count} words")
        _log(f"Output folder: {out_dir}")

        _done({
            "success": True,
            "transcript_path": str(txt_path),
            "json_path": str(json_path),
            "raw_json_path": str(raw_json_path),
            "raw_txt_path": str(raw_txt_path),
            "job_config_path": str(job_config_path) if job_config_path else None,
            "output_dir": str(out_dir),
            "transcript_text": transcript_text,
            "audio_tier": analysis.tier if analysis else "",
            "error": None,
        })

    except Exception as exc:
        _log(f"ERROR: {exc}")
        _progress(0, "Failed")
        _done({
            "success": False,
            "transcript_path": None,
            "json_path": None,
            "transcript_text": "",
            "error": str(exc),
        })
