"""
pipeline/assembler.py

Merges multiple chunk results into a single coherent transcript.

Deduplication removes words that appear in the overlap window of adjacent
chunks by comparing timestamps. The last word timestamp of chunk N is used
as the cutoff for the start of chunk N+1.
"""

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


def _build_speaker_remap(
    prev_utterances: List[Dict],
    next_utterances: List[Dict],
    overlap_start: float,
    offset: float,
) -> Dict[int, int]:
    """
    Map next-chunk speaker IDs onto the already-assembled speaker IDs.

    Uses the overlap window between adjacent chunks to find the most likely
    speaker correspondence by temporal overlap. Returns an empty dict when
    no confident mapping can be made, allowing speaker IDs to pass through
    unchanged for that chunk.
    """
    prev_overlap = [
        u for u in prev_utterances
        if float(u.get("end", 0.0) or 0.0) >= overlap_start
    ]
    next_overlap = [
        u for u in next_utterances
        if (float(u.get("start", 0.0) or 0.0) + offset) <= (overlap_start + CHUNK_OVERLAP_SECONDS)
        and (float(u.get("end", 0.0) or 0.0) + offset) >= overlap_start
    ]

    if not prev_overlap or not next_overlap:
        _logger.debug(
            "[ASSEMBLE] No overlap utterances found for speaker remap (prev=%d next=%d)",
            len(prev_overlap),
            len(next_overlap),
        )
        return {}

    remap: Dict[int, int] = {}
    used_global_speakers: set[int] = set()

    for next_utt in next_overlap:
        next_speaker = next_utt.get("speaker")
        if next_speaker is None:
            continue
        next_speaker_id = int(next_speaker)
        if next_speaker_id in remap:
            continue

        next_start = float(next_utt.get("start", 0.0) or 0.0) + offset
        next_end = float(next_utt.get("end", 0.0) or 0.0) + offset

        best_overlap = 0.0
        best_global_speaker: int | None = None

        for prev_utt in prev_overlap:
            prev_speaker = prev_utt.get("speaker")
            if prev_speaker is None:
                continue
            prev_speaker_id = int(prev_speaker)
            if prev_speaker_id in used_global_speakers:
                continue

            prev_start = float(prev_utt.get("start", 0.0) or 0.0)
            prev_end = float(prev_utt.get("end", 0.0) or 0.0)
            overlap = max(0.0, min(next_end, prev_end) - max(next_start, prev_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_global_speaker = prev_speaker_id

        if best_global_speaker is not None and best_overlap > 0.1:
            remap[next_speaker_id] = best_global_speaker
            used_global_speakers.add(best_global_speaker)
            _logger.debug(
                "[ASSEMBLE] Speaker remap: chunk_speaker=%d -> global_speaker=%d (overlap=%.2fs)",
                next_speaker_id,
                best_global_speaker,
                best_overlap,
            )

    return remap


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

        utterance_boundary: float | None = None

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
            if deduplicated:
                utterance_boundary = deduplicated[0]["start"]
        else:
            all_words.extend(adjusted_words)

        speaker_remap: Dict[int, int] = {}
        if i > 0 and all_utterances:
            overlap_start = max(0.0, chunk_start_offsets[i] - CHUNK_OVERLAP_SECONDS)
            speaker_remap = _build_speaker_remap(
                prev_utterances=all_utterances,
                next_utterances=result["utterances"],
                overlap_start=overlap_start,
                offset=offset,
            )
            if speaker_remap:
                _logger.info("[ASSEMBLE] Chunk %d speaker remap: %s", i, speaker_remap)

        if speaker_remap:
            for word in all_words[-len(adjusted_words):]:
                speaker = word.get("speaker")
                if speaker is None:
                    continue
                raw_speaker = int(speaker)
                word["speaker"] = speaker_remap.get(raw_speaker, raw_speaker)

        for u in result["utterances"]:
            u_start = round(float(u.get("start", 0.0) or 0.0) + offset, 3)
            u_end = round(float(u.get("end", 0.0) or 0.0) + offset, 3)

            if utterance_boundary is not None and u_end <= utterance_boundary:
                _logger.debug(
                    "[ASSEMBLE] Dropping overlap utterance: start=%.3f end=%.3f boundary=%.3f",
                    u_start,
                    u_end,
                    utterance_boundary,
                )
                continue

            speaker = u.get("speaker")
            normalized_speaker = int(speaker) if speaker is not None else None
            if normalized_speaker is not None:
                normalized_speaker = speaker_remap.get(normalized_speaker, normalized_speaker)
            all_utterances.append({
                **u,
                "speaker": normalized_speaker,
                "start": u_start,
                "end":   u_end,
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
