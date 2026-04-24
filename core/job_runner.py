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
                f"WARNING: {prefix}chunk {i+1}/{len(chunks)} failed "
                f"({chunk.start_seconds:.0f}s–{chunk.end_seconds:.0f}s): "
                f"{chunk_exc} — inserting empty placeholder, continuing."
            )
            chunk_results.append({
                "words": [],
                "utterances": [],
                "transcript": "",
                "raw": {},
            })
            chunk_offsets.append(chunk.start_seconds)

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
        import concurrent.futures

        from pipeline.preprocessor import (
            validate_audio_file, normalize_audio,
            QUALITY_CONFIGS, AUTO_DETECT_KEY, check_ffmpeg,
        )
        from pipeline.chunker import chunk_audio, cleanup_chunks
        from pipeline.transcriber import transcribe_chunk
        from pipeline.assembler import reassemble_chunks, build_transcript_text
        from pipeline.audio_quality import analyze_audio
        from pipeline.vad_trimmer import trim_silence
        from pipeline.pyannote_diarizer import diarize, align_speakers
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

        use_pyannote = analysis.tier in ("ENHANCED", "RESCUE")
        pyannote_future = None
        executor = None
        if use_pyannote:
            _log("Starting pyannote diarization (parallel with transcription)…")
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            pyannote_future = executor.submit(diarize, normalized_path)

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

        _progress(82, "Assembling transcript…")
        assembled = reassemble_chunks(chunk_results, chunk_offsets)

        word_count = len(assembled.get("words", []))
        utterance_count = len(assembled.get("utterances", []))
        _log(f"Assembled: {word_count} words, {utterance_count} utterances")

        if pyannote_future is not None:
            try:
                _progress(85, "Applying pyannote speaker labels…")
                pyannote_segments = pyannote_future.result(timeout=300)
                if pyannote_segments:
                    assembled["utterances"] = align_speakers(
                        assembled.get("utterances", []),
                        pyannote_segments,
                    )
                    assembled["transcript"] = build_transcript_text(assembled["utterances"])
                    _log("Pyannote speaker labels applied successfully")
                else:
                    _log("Pyannote returned no segments — keeping Deepgram labels")
            except Exception as pa_exc:
                _log(f"Pyannote alignment skipped: {pa_exc}")
            finally:
                if executor:
                    executor.shutdown(wait=False)

        _progress(90, "Building output files…")

        transcript_text = assembled.get("transcript", "")
        if not transcript_text.strip():
            lines = []
            for u in assembled.get("utterances", []):
                speaker = u.get("speaker_label") or f"Speaker {u.get('speaker', 0)}"
                text = (u.get("transcript") or "").strip()
                if text:
                    lines.append(f"{speaker}: {text}")
            transcript_text = "\n\n".join(lines)

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

        txt_path.write_text(transcript_text, encoding="utf-8")
        _log(f"Saved: {txt_path.name}")

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
            "words": assembled.get("words", []),
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        _log(f"Saved: {json_path.name}")

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
            "chunk_summaries": _build_chunk_summaries(chunks),
            "chunks": assembled.get("raw_chunks", []),
        }
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        _log(f"Saved raw: {raw_json_path.name}")

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
