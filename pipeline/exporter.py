"""
pipeline/exporter.py

Writes the final transcript and JSON output files from Deepgram results.
This exporter belongs to the pipeline layer and handles raw transcription-side
outputs before the clean-format cleanup/DOCX stage.

OUTPUT FILES:
  1. {prefix}_transcript.txt    — Plain text with speaker labels and timestamps.
  2. {prefix}_deepgram.json     — Full structured output with word-level data.
  3. {prefix}_flagged_words.txt — Words below the confidence threshold.
  4. raw_deepgram.txt           — Latest raw utterance transcript baseline.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from app_logging import get_logger
from pipeline.assembler import build_transcript_text, format_timestamp
from config import OUTPUT_DIR, LOW_CONFIDENCE_THRESHOLD

LOGGER = get_logger(__name__)


def save_raw_deepgram_output(utterances: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for utterance in utterances:
            speaker = utterance.get("speaker", "?")
            text = (utterance.get("transcript") or "").strip()
            if text:
                f.write(f"Speaker {speaker}: {text}\n\n")


def export_results(
    assembled_result: Dict[str, Any],
    source_filename: str,
    case_info: Dict[str, str] = None,
    confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    progress_callback=None,
    formatted_transcript: str = None,
    speaker_map: Dict[int, str] = None,
) -> Dict[str, str]:
    """
    Write all output files for a completed transcription.

    Returns:
        { "transcript": path, "json": path, "flagged": path, "raw_deepgram": path }
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    LOGGER.info("[EXPORT] Writing output files to %s/", OUTPUT_DIR)

    if case_info is None:
        case_info = {}

    base = os.path.splitext(os.path.basename(source_filename))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{base}_{timestamp}"

    # ── JSON output ───────────────────────────────────────────────────────────
    json_path = os.path.join(OUTPUT_DIR, f"{prefix}_deepgram.json")
    json_output = {
        "meta": {
            "source_file":          source_filename,
            "exported_at":          datetime.now().isoformat(),
            "word_count":           len(assembled_result.get("words", [])),
            "utterance_count":      len(assembled_result.get("utterances", [])),
            "case_name":            case_info.get("case_name", ""),
            "cause_number":         case_info.get("cause_number", ""),
            "deponent_name":        case_info.get("deponent_name", ""),
            "deposition_date":      case_info.get("deposition_date", ""),
            "confidence_threshold": confidence_threshold,
        },
        "transcript":              assembled_result.get("transcript", ""),
        "words":                   assembled_result.get("words", []),
        "utterances":              assembled_result.get("utterances", []),
        "raw_deepgram_response":   assembled_result.get("raw_chunks", []),
    }

    # Wrap each file write so a disk/permission error produces a useful log
    # message with the target path before re-raising.
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        LOGGER.error("[EXPORT] Failed to write JSON output %s: %s", json_path, exc)
        raise

    if progress_callback:
        progress_callback(f"JSON written: {os.path.basename(json_path)}")

    # ── Plain text transcript ─────────────────────────────────────────────────
    txt_path = os.path.join(OUTPUT_DIR, f"{prefix}_transcript.txt")

    if formatted_transcript and formatted_transcript.strip():
        transcript_content = formatted_transcript
        LOGGER.info("[EXPORT] Using corrected transcript (%s chars)", len(transcript_content))
    else:
        transcript_content = build_transcript_text(
            assembled_result.get("utterances", []),
            speaker_map=speaker_map or assembled_result.get("speaker_map"),
        ) or assembled_result.get("transcript", "")
        LOGGER.warning("[EXPORT] No corrected transcript provided — writing raw Deepgram output")

    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript_content)
    except OSError as exc:
        LOGGER.error("[EXPORT] Failed to write transcript %s: %s", txt_path, exc)
        raise

    if progress_callback:
        progress_callback(f"Transcript written: {os.path.basename(txt_path)}")

    raw_deepgram_path = os.path.join(OUTPUT_DIR, "raw_deepgram.txt")
    try:
        save_raw_deepgram_output(
            assembled_result.get("raw_utterances", assembled_result.get("utterances", [])),
            raw_deepgram_path,
        )
    except OSError as exc:
        LOGGER.error(
            "[EXPORT] Failed to write raw Deepgram output %s: %s",
            raw_deepgram_path, exc,
        )
        raise

    if progress_callback:
        progress_callback(f"Raw Deepgram transcript written: {os.path.basename(raw_deepgram_path)}")

    # ── Flagged words ─────────────────────────────────────────────────────────
    words = assembled_result.get("words", [])
    flagged: List[Dict] = [
        w for w in words
        if w.get("confidence", 1.0) < confidence_threshold
    ]

    flagged_path = os.path.join(OUTPUT_DIR, f"{prefix}_flagged_words.txt")
    try:
        with open(flagged_path, "w", encoding="utf-8") as f:
            f.write(f"FLAGGED WORDS — Confidence Below {confidence_threshold}\n")
            f.write(f"Source: {source_filename}\n")
            f.write(f"Total flagged: {len(flagged)} of {len(words)} words\n")
            f.write("=" * 70 + "\n\n")
            for w in flagged:
                ts = format_timestamp(w["start"])
                f.write(
                    f"[{ts}]  \"{w['word']}\"  "
                    f"confidence={w.get('confidence', 0):.3f}  "
                    f"speaker={w.get('speaker', '?')}\n"
                )
    except OSError as exc:
        LOGGER.error(
            "[EXPORT] Failed to write flagged words %s: %s", flagged_path, exc
        )
        raise

    if progress_callback:
        progress_callback(
            f"Flagged words: {len(flagged)} of {len(words)} "
            f"below threshold {confidence_threshold}"
        )

    LOGGER.info("[EXPORT] Done")
    return {
        "transcript": txt_path,
        "json": json_path,
        "flagged": flagged_path,
        "raw_deepgram": raw_deepgram_path,
    }
