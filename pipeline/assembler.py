"""
pipeline/assembler.py

Merges multiple chunk results into a single coherent transcript.

Deduplication removes words that appear in the overlap window of adjacent
chunks by comparing timestamps. The last word timestamp of chunk N is used
as the cutoff for the start of chunk N+1.
"""

from collections import defaultdict
from typing import Any, Dict, List

from config import CHUNK_OVERLAP_SECONDS
from app_logging import get_logger

_logger = get_logger(__name__)

ROLE_SEQUENCE = [
    "THE WITNESS",
    "EXAMINING ATTORNEY",
    "OPPOSING COUNSEL",
    "THE REPORTER",
    "THE VIDEOGRAPHER",
    "THE INTERPRETER",
]


def _count_utterance_words(utterance: Dict) -> int:
    words = utterance.get("words") or []
    if words:
        return len(words)
    return len((utterance.get("transcript") or "").split())


def _build_speaker_role_map(utterances: List[Dict]) -> Dict[int, str]:
    speaker_ids = sorted(set(
        int(u.get("speaker", 0) or 0) for u in utterances
    ))
    return {sid: f"Speaker {sid}" for sid in speaker_ids}


def _attach_speaker_labels(
    utterances: List[Dict],
    speaker_map: Dict[int, str] | None = None,
) -> List[Dict]:
    role_map = speaker_map or _build_speaker_role_map(utterances)
    labeled: List[Dict] = []
    for utterance in utterances:
        speaker_id = int(utterance.get("speaker", 0) or 0)
        labeled.append({
            **utterance,
            "speaker_label": role_map.get(speaker_id, f"SPEAKER {speaker_id}"),
        })
    return labeled


def build_transcript_text(
    utterances: List[Dict],
    speaker_map: Dict[int, str] | None = None,
) -> str:
    """
    Build a plain text transcript from utterances.
    If speaker_map is provided, use those labels; otherwise fall back
    to generic Speaker N labels.
    """
    if not utterances:
        return ""
    labeled = _attach_speaker_labels(utterances, speaker_map)
    lines = []
    for u in sorted(labeled, key=lambda x: x.get("start", 0)):
        speaker = u.get("speaker_label") or f"SPEAKER {u.get('speaker', 0)}"
        text = (u.get("transcript") or "").strip()
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n\n".join(lines)


def reassemble_chunks(
    chunk_results: List[Dict[str, Any]],
    chunk_start_offsets: List[float],
) -> Dict[str, Any]:
    """
    Merge chunk results into a single transcript, adjusting timestamps
    and deduplicating overlapping words.

    Args:
        chunk_results:       List of result dicts from transcriber.transcribe_chunk().
        chunk_start_offsets: Start-second offset for each chunk.

    Returns:
        { "words", "utterances", "transcript", "raw_chunks" }
    """
    _logger.info("[ASSEMBLE] Joining %d chunks...", len(chunk_results))
    if not chunk_results:
        return {"words": [], "utterances": [], "transcript": "", "raw_chunks": []}

    if len(chunk_results) == 1:
        result = chunk_results[0]
        labeled_utterances = _attach_speaker_labels(result["utterances"])
        transcript = build_transcript_text(labeled_utterances)
        return {
            "words":       result["words"],
            "utterances":  labeled_utterances,
            "transcript":  transcript or result["transcript"],
            "raw_chunks":  [result["raw"]],
        }

    all_words: List[Dict] = []
    all_utterances: List[Dict] = []
    raw_chunks = []

    for i, result in enumerate(chunk_results):
        offset = chunk_start_offsets[i]
        raw_chunks.append(result["raw"])

        adjusted_words = [
            {**w, "start": round(w["start"] + offset, 3), "end": round(w["end"] + offset, 3)}
            for w in result["words"]
        ]

        if i > 0 and all_words:
            last_ts = all_words[-1]["end"]
            last_word_text = (all_words[-1].get("word") or "").lower().strip()

            deduplicated = []
            for w in adjusted_words:
                w_text = (w.get("word") or "").lower().strip()
                if w["start"] <= last_ts and w_text == last_word_text:
                    continue
                if w["start"] < last_ts - 0.5:
                    continue
                deduplicated.append(w)

            # Fallback if too many words were removed (poor audio at boundary)
            if len(deduplicated) < len(adjusted_words) * 0.5:
                cutoff = last_ts - (CHUNK_OVERLAP_SECONDS / 2)
                deduplicated = [w for w in adjusted_words if w["start"] > cutoff]

            all_words.extend(deduplicated)
        else:
            all_words.extend(adjusted_words)

        for u in result["utterances"]:
            all_utterances.append({
                **u,
                "start": round(u["start"] + offset, 3),
                "end":   round(u["end"] + offset, 3),
            })

    all_utterances.sort(key=lambda u: u["start"])
    labeled_utterances = _attach_speaker_labels(all_utterances)
    full_transcript = build_transcript_text(labeled_utterances)
    if not full_transcript.strip():
        # Fallback if no utterances (shouldn't happen with diarize=True)
        full_transcript = " ".join(w.get("word", "") for w in all_words)
    merged = {
        "words": all_words,
        "utterances": labeled_utterances,
        "transcript": full_transcript,
        "raw_chunks": raw_chunks,
    }
    _logger.info("[ASSEMBLE] Total words: %d", len(merged.get("words", [])))

    return merged


def format_timestamp(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS.cs string."""
    total_ms = int(seconds * 100)
    cs = total_ms % 100
    total_s = total_ms // 100
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"
