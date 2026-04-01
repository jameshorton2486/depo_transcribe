"""
pipeline/exporter.py

Writes the final transcript and JSON output files from Deepgram results.
This exporter belongs to the pipeline layer and handles raw transcription-side
outputs. It is distinct from spec_engine/exporter.py, which handles final
legal-transcript export after structured correction/formatting.

OUTPUT FILES:
  1. {prefix}_transcript.txt    — Plain text with speaker labels and timestamps.
  2. {prefix}_deepgram.json     — Full structured output with word-level data.
  3. {prefix}_flagged_words.txt — Words below the confidence threshold.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from app_logging import get_logger
from pipeline.assembler import build_transcript_text, format_timestamp
from config import OUTPUT_DIR, LOW_CONFIDENCE_THRESHOLD

LOGGER = get_logger(__name__)


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
        { "transcript": path, "json": path, "flagged": path }
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[EXPORT] Writing output files to {OUTPUT_DIR}/")

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
            "word_count":           len(assembled_result["words"]),
            "utterance_count":      len(assembled_result["utterances"]),
            "case_name":            case_info.get("case_name", ""),
            "cause_number":         case_info.get("cause_number", ""),
            "deponent_name":        case_info.get("deponent_name", ""),
            "deposition_date":      case_info.get("deposition_date", ""),
            "confidence_threshold": confidence_threshold,
        },
        "transcript":              assembled_result["transcript"],
        "words":                   assembled_result["words"],
        "utterances":              assembled_result["utterances"],
        "raw_deepgram_response":   assembled_result.get("raw_chunks", []),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)

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

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(transcript_content)

    if progress_callback:
        progress_callback(f"Transcript written: {os.path.basename(txt_path)}")

    # ── Flagged words ─────────────────────────────────────────────────────────
    flagged: List[Dict] = [
        w for w in assembled_result["words"]
        if w.get("confidence", 1.0) < confidence_threshold
    ]

    flagged_path = os.path.join(OUTPUT_DIR, f"{prefix}_flagged_words.txt")
    with open(flagged_path, "w", encoding="utf-8") as f:
        f.write(f"FLAGGED WORDS — Confidence Below {confidence_threshold}\n")
        f.write(f"Source: {source_filename}\n")
        f.write(f"Total flagged: {len(flagged)} of {len(assembled_result['words'])} words\n")
        f.write("=" * 70 + "\n\n")
        for w in flagged:
            ts = format_timestamp(w["start"])
            f.write(
                f"[{ts}]  \"{w['word']}\"  "
                f"confidence={w.get('confidence', 0):.3f}  "
                f"speaker={w.get('speaker', '?')}\n"
            )

    if progress_callback:
        progress_callback(
            f"Flagged words: {len(flagged)} of {len(assembled_result['words'])} "
            f"below threshold {confidence_threshold}"
        )

    print("[EXPORT] Done")
    return {"transcript": txt_path, "json": json_path, "flagged": flagged_path}
