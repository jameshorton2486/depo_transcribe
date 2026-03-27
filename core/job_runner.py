"""
core/job_runner.py

Runs the full transcription pipeline:
  audio file -> normalize -> chunk -> transcribe -> assemble -> save

Called from ui/tab_transcribe.py in a background thread.
"""

import json
import os
import threading
from pathlib import Path
from datetime import datetime


def build_output_path(
    base_dir: str,
    cause_number: str = "",
    last_name: str = "",
    date_str: str = "",
) -> Path:
    """
    Build filing path: base_dir / YYYY / Mon / CauseNumber_LastName

    Example: C:\\Users\\james\\Depositions\\2026\\Mar\\2025CI19595_Coger
    """
    # Parse date
    dt = None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            break
        except ValueError:
            continue
    if dt is None:
        dt = datetime.now()

    # Sanitize cause number and last name for use in folder name
    safe_cause = "".join(c for c in cause_number if c.isalnum() or c in "-_") or "UnknownCause"
    safe_name  = "".join(c for c in last_name   if c.isalnum() or c in "-_") or "UnknownWitness"

    folder_name = f"{safe_cause}_{safe_name}"

    return Path(base_dir) / dt.strftime("%Y") / dt.strftime("%b") / folder_name


def run_transcription_job(
    audio_path: str,
    model: str,
    quality: str,
    base_dir: str,
    cause_number: str = "",
    last_name: str = "",
    date_str: str = "",
    keyterms: list = None,
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
            QUALITY_CONFIGS, check_ffmpeg,
        )
        from pipeline.chunker import chunk_audio, cleanup_chunks
        from pipeline.transcriber import transcribe_chunk
        from pipeline.assembler import reassemble_chunks

        # -- 1. Check FFmpeg -------------------------------------------------------
        _progress(2, "Checking FFmpeg\u2026")
        if not check_ffmpeg():
            raise RuntimeError(
                "FFmpeg is not installed or not on PATH.\n"
                "Download from https://ffmpeg.org and add to Windows PATH."
            )

        # -- 2. Validate audio file ------------------------------------------------
        _progress(5, "Validating audio file\u2026")
        v = validate_audio_file(audio_path)
        if not v["valid"]:
            raise ValueError(v["error"])
        duration_min = v["duration"] / 60
        _log(f"File valid: {v['format'].upper()}  {duration_min:.1f} minutes")

        # Log keyterms
        _log(f"Keyterms: {len(keyterms or [])}")

        # -- 3. Normalize audio ----------------------------------------------------
        _progress(10, "Normalizing audio\u2026")
        quality_cfg = QUALITY_CONFIGS.get(quality, list(QUALITY_CONFIGS.values())[0])
        _log(f"Normalizing: {quality_cfg['description']}")
        normalized_path = normalize_audio(
            audio_path,
            config=quality_cfg,
            progress_callback=_log,
        )
        _log(f"Normalized: {os.path.basename(normalized_path)}")

        # -- 4. Chunk audio --------------------------------------------------------
        _progress(20, "Splitting into chunks\u2026")
        chunks = chunk_audio(
            normalized_path,
            total_duration=v["duration"],
            progress_callback=_log,
        )
        _log(f"Split into {len(chunks)} chunk(s)")

        # -- 5. Transcribe each chunk ----------------------------------------------
        chunk_results = []
        chunk_offsets = []

        for i, chunk in enumerate(chunks):
            pct = 22 + int((i / len(chunks)) * 58)
            _progress(pct, f"Transcribing chunk {i+1} of {len(chunks)}\u2026")
            _log(f"Chunk {i+1}/{len(chunks)}: {chunk.start_seconds:.0f}s \u2013 {chunk.end_seconds:.0f}s")

            result = transcribe_chunk(
                chunk.file_path,
                model=model,
                utt_split=0.85,
                keyterms=keyterms,
                progress_callback=_log,
            )
            chunk_results.append(result)
            chunk_offsets.append(chunk.start_seconds)

        # -- 6. Assemble chunks ----------------------------------------------------
        _progress(82, "Assembling transcript\u2026")
        assembled = reassemble_chunks(chunk_results, chunk_offsets)
        word_count = len(assembled.get("words", []))
        utterance_count = len(assembled.get("utterances", []))
        _log(f"Assembled: {word_count} words, {utterance_count} utterances")

        # -- 7. Build output text --------------------------------------------------
        _progress(90, "Building output files\u2026")

        # Plain transcript text -- Speaker N: [text] format
        transcript_text = assembled.get("transcript", "")
        if not transcript_text.strip():
            # Fallback: join all utterances
            lines = []
            for u in assembled.get("utterances", []):
                speaker = u.get("speaker_label") or f"Speaker {u.get('speaker', 0)}"
                text = (u.get("transcript") or "").strip()
                if text:
                    lines.append(f"{speaker}: {text}")
            transcript_text = "\n\n".join(lines)

        # -- 8. Save files ---------------------------------------------------------
        _progress(95, "Saving files\u2026")
        out_dir = build_output_path(base_dir, cause_number, last_name, date_str)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Name files by timestamp
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = Path(audio_path).stem[:40]  # truncate long names
        txt_name  = f"{base_name}_{stamp}.txt"
        json_name = f"{base_name}_{stamp}.json"

        txt_path  = out_dir / txt_name
        json_path = out_dir / json_name

        # Write transcript text
        txt_path.write_text(transcript_text, encoding="utf-8")
        _log(f"Saved: {txt_path.name}")

        # Write JSON -- assembled utterances + raw chunks
        json_data = {
            "audio_file":   audio_path,
            "model":        model,
            "created_at":   datetime.now().isoformat(),
            "duration_sec": v["duration"],
            "word_count":   word_count,
            "utterances":   assembled.get("utterances", []),
            "words":        assembled.get("words", []),
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        _log(f"Saved: {json_path.name}")

        # Write raw Deepgram responses
        raw_json_path = out_dir / f"{base_name}_{stamp}_raw.json"
        raw_data = {
            "audio_file": audio_path,
            "model":      model,
            "created_at": datetime.now().isoformat(),
            "chunks":     [r.get("raw", {}) for r in chunk_results],
        }
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        _log(f"Saved raw: {raw_json_path.name}")

        # Write UFM fields if provided
        ufm_path = None
        if ufm_fields:
            ufm_path = out_dir / f"{base_name}_{stamp}_ufm_fields.json"
            with open(ufm_path, "w", encoding="utf-8") as f:
                json.dump(ufm_fields, f, indent=2, ensure_ascii=False)
            _log(f"Saved UFM fields: {ufm_path.name}")

        # -- 9. Cleanup temp chunks ------------------------------------------------
        cleanup_chunks(chunks)

        # -- 10. Done --------------------------------------------------------------
        _progress(100, "Complete \u2713")
        _log(f"\u2713 Transcription complete \u2014 {word_count} words")
        _log(f"Output folder: {out_dir}")

        _done({
            "success":         True,
            "transcript_path": str(txt_path),
            "json_path":       str(json_path),
            "raw_json_path":   str(raw_json_path),
            "ufm_fields_path": str(ufm_path) if ufm_path else None,
            "output_dir":      str(out_dir),
            "transcript_text": transcript_text,
            "error":           None,
        })

    except Exception as exc:
        _log(f"ERROR: {exc}")
        _progress(0, "Failed")
        _done({
            "success":         False,
            "transcript_path": None,
            "json_path":       None,
            "transcript_text": "",
            "error":           str(exc),
        })
