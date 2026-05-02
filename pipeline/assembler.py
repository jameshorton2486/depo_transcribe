"""
pipeline/assembler.py

Merges multiple chunk results into a single coherent transcript.

Deduplication removes words that appear in the overlap window of adjacent
chunks by comparing timestamps. The last word timestamp of chunk N is used
as the cutoff for the start of chunk N+1.
"""

import re
from difflib import SequenceMatcher
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

_OVERLAP_WORD_RE = re.compile(r"^\W+|\W+$")
GAP_THRESHOLD_SECONDS = 1.25
SHORT_GAP_THRESHOLD_SECONDS = 0.6
MIN_UTTERANCE_WORDS = 2
SPEAKER_GLITCH_DURATION_SECONDS = 0.5


def _count_utterance_words(utterance: Dict) -> int:
    words = utterance.get("words") or []
    if words:
        return len(words)
    return len((utterance.get("transcript") or "").split())


def _normalize_utterance(utterance: Dict) -> Dict | None:
    text = " ".join((utterance.get("transcript") or "").split()).strip()
    if not text:
        return None

    normalized = {
        **utterance,
        "transcript": text,
        "start": float(utterance.get("start", 0.0) or 0.0),
        "end": float(utterance.get("end", 0.0) or 0.0),
    }
    if normalized.get("speaker") is not None:
        normalized["speaker"] = int(normalized["speaker"])
    return normalized


def _join_transcript_text(prev_text: str, next_text: str) -> str:
    return " ".join(
        part for part in [prev_text.rstrip(), next_text.lstrip()] if part
    ).strip()


def _append_utterance_words(target: Dict, source: Dict) -> None:
    target_words = list(target.get("words") or [])
    source_words = list(source.get("words") or [])
    if target_words and source_words:
        target["words"] = target_words + source_words
    elif source_words and not target_words:
        target["words"] = source_words


def _merge_two_utterances(current: Dict, following: Dict) -> Dict:
    merged = {
        **current,
        "transcript": _join_transcript_text(
            current.get("transcript") or "",
            following.get("transcript") or "",
        ),
        "start": float(current.get("start", 0.0) or 0.0),
        "end": max(
            float(current.get("end", 0.0) or 0.0),
            float(following.get("end", 0.0) or 0.0),
        ),
    }
    _append_utterance_words(merged, following)
    return merged


def _is_duplicate_utterance(current: Dict, following: Dict) -> bool:
    return (
        current.get("speaker") == following.get("speaker")
        and (current.get("transcript") or "").strip()
        == (following.get("transcript") or "").strip()
    )


def _is_speaker_flip_glitch(
    utterances: List[Dict],
    index: int,
    gap_threshold_seconds: float,
) -> bool:
    if index <= 0 or index >= len(utterances) - 1:
        return False

    previous = utterances[index - 1]
    current = utterances[index]
    following = utterances[index + 1]

    current_speaker = current.get("speaker")
    if current_speaker is None:
        return False

    if previous.get("speaker") != following.get("speaker"):
        return False
    if previous.get("speaker") == current_speaker:
        return False

    duration = float(current.get("end", 0.0) or 0.0) - float(
        current.get("start", 0.0) or 0.0
    )
    if duration >= SPEAKER_GLITCH_DURATION_SECONDS:
        return False

    gap_before = float(current.get("start", 0.0) or 0.0) - float(
        previous.get("end", 0.0) or 0.0
    )
    gap_after = float(following.get("start", 0.0) or 0.0) - float(
        current.get("end", 0.0) or 0.0
    )
    return gap_before <= gap_threshold_seconds and gap_after <= gap_threshold_seconds


def _should_merge_utterances(
    current: Dict,
    following: Dict,
    gap_threshold_seconds: float,
    short_gap_threshold_seconds: float,
    min_word_count: int,
) -> bool:
    if current.get("speaker") != following.get("speaker"):
        return False

    gap = float(following.get("start", 0.0) or 0.0) - float(
        current.get("end", 0.0) or 0.0
    )
    if gap < 0:
        gap = 0.0
    if gap > gap_threshold_seconds:
        return False

    current_words = _count_utterance_words(current)
    following_words = _count_utterance_words(following)
    if current_words < min_word_count or following_words < min_word_count:
        return gap <= short_gap_threshold_seconds

    return True


def merge_utterances(
    utterances: List[Dict],
    gap_threshold_seconds: float = GAP_THRESHOLD_SECONDS,
    short_gap_threshold_seconds: float = SHORT_GAP_THRESHOLD_SECONDS,
    min_word_count: int = MIN_UTTERANCE_WORDS,
) -> List[Dict]:
    """
    Deterministically merge adjacent utterances into stable speaker-consistent blocks.

    Input utterances are expected to already be overlap-deduplicated and timestamp-adjusted.
    """
    normalized = [
        normalized_utterance
        for utterance in utterances
        if (normalized_utterance := _normalize_utterance(utterance)) is not None
    ]
    if not normalized:
        return []

    normalized.sort(key=lambda u: (u["start"], u["end"]))
    merged: List[Dict] = []
    current = normalized[0]
    index = 1

    while index < len(normalized):
        candidate = normalized[index]

        if _is_duplicate_utterance(current, candidate):
            _logger.debug(
                "[ASSEMBLE] Skipping duplicate utterance speaker=%s text=%r",
                current.get("speaker"),
                current.get("transcript"),
            )
            index += 1
            continue

        if _should_merge_utterances(
            current,
            candidate,
            gap_threshold_seconds=gap_threshold_seconds,
            short_gap_threshold_seconds=short_gap_threshold_seconds,
            min_word_count=min_word_count,
        ):
            current = _merge_two_utterances(current, candidate)
            index += 1
            continue

        if _is_speaker_flip_glitch(normalized, index, gap_threshold_seconds):
            _logger.debug(
                "[ASSEMBLE] Ignoring speaker flip glitch speaker=%s start=%.3f end=%.3f",
                candidate.get("speaker"),
                candidate.get("start"),
                candidate.get("end"),
            )
            index += 1
            continue

        merged.append(current)
        current = candidate
        index += 1

    merged.append(current)
    return merged


def _build_speaker_role_map(utterances: List[Dict]) -> Dict[int, str]:
    speaker_ids = sorted(set(int(u.get("speaker", 0) or 0) for u in utterances))
    return {sid: f"Speaker {sid}" for sid in speaker_ids}


def _normalize_overlap_token(token: str) -> str:
    return _OVERLAP_WORD_RE.sub("", (token or "").strip().lower())


def is_near_duplicate(
    prev_tail: List[str],
    curr_head: List[str],
    threshold: float = 0.96,
) -> bool:
    prev_str = " ".join(prev_tail).strip().lower()
    curr_str = " ".join(curr_head).strip().lower()
    if not prev_str or not curr_str:
        return False
    ratio = SequenceMatcher(None, prev_str, curr_str).ratio()
    return ratio >= threshold


def _find_overlap_word_count(
    prev_text: str,
    curr_text: str,
    max_overlap_words: int = 25,
) -> int:
    prev_words = prev_text.split()
    curr_words = curr_text.split()
    if not prev_words or not curr_words:
        return 0

    normalized_prev = [_normalize_overlap_token(word) for word in prev_words]
    normalized_curr = [_normalize_overlap_token(word) for word in curr_words]

    max_k = min(max_overlap_words, len(normalized_prev), len(normalized_curr))

    for k in range(max_k, 0, -1):
        prev_tail = normalized_prev[-k:]
        curr_head = normalized_curr[:k]

        if not all(prev_tail) or not all(curr_head):
            continue

        if prev_tail == curr_head:
            return k

    for k in range(max_k, 4, -1):
        prev_tail = normalized_prev[-k:]
        curr_head = normalized_curr[:k]

        if not all(prev_tail) or not all(curr_head):
            continue

        if is_near_duplicate(prev_tail, curr_head):
            return k

    return 0


def merge_with_overlap(
    prev_text: str, curr_text: str, max_overlap_words: int = 25
) -> str:
    """
    Merge two transcript snippets by removing exact/near-duplicate overlap.

    This is deterministic and only trims a leading overlap from curr_text.
    """
    prev_text = (prev_text or "").strip()
    curr_text = (curr_text or "").strip()

    if not prev_text:
        return curr_text
    if not curr_text:
        return prev_text

    curr_words = curr_text.split()
    overlap_count = _find_overlap_word_count(
        prev_text, curr_text, max_overlap_words=max_overlap_words
    )

    if overlap_count <= 0:
        return f"{prev_text} {curr_text}".strip()

    if overlap_count >= len(curr_words):
        return prev_text

    return f"{prev_text} {' '.join(curr_words[overlap_count:])}".strip()


def _merge_adjacent_same_speaker_overlap(
    merged_utterances: List[Dict],
    candidate: Dict,
    max_overlap_words: int = 25,
) -> bool:
    """
    Merge candidate into the previous utterance when the same speaker repeats
    overlap text across a chunk boundary.
    """
    if not merged_utterances:
        return False

    previous = merged_utterances[-1]
    if previous.get("speaker") != candidate.get("speaker"):
        return False

    prev_text = (previous.get("transcript") or "").strip()
    curr_text = (candidate.get("transcript") or "").strip()
    if not prev_text or not curr_text:
        return False
    if len(curr_text.split()) < 4:
        return False

    overlap_count = _find_overlap_word_count(
        prev_text, curr_text, max_overlap_words=max_overlap_words
    )
    if overlap_count <= 0:
        return False

    merged_text = merge_with_overlap(
        prev_text, curr_text, max_overlap_words=max_overlap_words
    )
    if merged_text == prev_text:
        previous["end"] = max(
            float(previous.get("end", 0.0) or 0.0),
            float(candidate.get("end", 0.0) or 0.0),
        )
        return True

    previous["transcript"] = merged_text
    previous["end"] = max(
        float(previous.get("end", 0.0) or 0.0), float(candidate.get("end", 0.0) or 0.0)
    )

    prev_words = list(previous.get("words") or [])
    curr_words = list(candidate.get("words") or [])
    if prev_words and curr_words and overlap_count < len(curr_words):
        previous["words"] = prev_words + curr_words[overlap_count:]
    elif prev_words and curr_words and overlap_count >= len(curr_words):
        previous["words"] = prev_words

    _logger.debug(
        "[ASSEMBLE] Merged overlap utterance speaker=%s overlap_words=%d",
        previous.get("speaker"),
        overlap_count,
    )
    return True


def _attach_speaker_labels(
    utterances: List[Dict],
    speaker_map: Dict[int, str] | None = None,
) -> List[Dict]:
    role_map = speaker_map or _build_speaker_role_map(utterances)
    labeled: List[Dict] = []
    for utterance in utterances:
        speaker_id = int(utterance.get("speaker", 0) or 0)
        labeled.append(
            {
                **utterance,
                "speaker_label": role_map.get(speaker_id, f"SPEAKER {speaker_id}"),
            }
        )
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
        u for u in prev_utterances if float(u.get("end", 0.0) or 0.0) >= overlap_start
    ]
    next_overlap = [
        u
        for u in next_utterances
        if (float(u.get("start", 0.0) or 0.0) + offset)
        <= (overlap_start + CHUNK_OVERLAP_SECONDS)
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
        return {
            "words": [],
            "utterances": [],
            "raw_utterances": [],
            "transcript": "",
            "raw_chunks": [],
        }

    if len(chunk_results) == 1:
        result = chunk_results[0]
        source_utterances = result.get("raw_utterances") or result.get("utterances", [])
        merged_utterances = merge_utterances(source_utterances)
        labeled_utterances = _attach_speaker_labels(merged_utterances)
        labeled_raw_utterances = _attach_speaker_labels(source_utterances)
        transcript = build_transcript_text(labeled_utterances)
        return {
            "words": result.get("words", []),
            "utterances": labeled_utterances,
            "raw_utterances": labeled_raw_utterances,
            "transcript": transcript or result.get("transcript", ""),
            "raw_chunks": [result.get("raw", {})],
        }

    all_words: List[Dict] = []
    all_utterances: List[Dict] = []
    all_raw_utterances: List[Dict] = []
    raw_chunks = []

    for i, result in enumerate(chunk_results):
        offset = chunk_start_offsets[i]
        raw_chunks.append(result.get("raw", {}))
        source_utterances = result.get("raw_utterances") or result.get("utterances", [])

        adjusted_words = [
            {
                **w,
                "start": round(w["start"] + offset, 3),
                "end": round(w["end"] + offset, 3),
            }
            for w in result.get("words", [])
        ]

        utterance_boundary: float | None = None
        # Track how many words we actually appended to all_words this iteration,
        # so the speaker-remap slice below covers exactly those words and never
        # reaches back into words from the previous chunk.
        words_added_count = 0

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
            words_added_count = len(deduplicated)
            if deduplicated:
                utterance_boundary = deduplicated[0]["start"]
        else:
            all_words.extend(adjusted_words)
            words_added_count = len(adjusted_words)

        speaker_remap: Dict[int, int] = {}
        if i > 0 and all_utterances:
            overlap_start = max(0.0, chunk_start_offsets[i] - CHUNK_OVERLAP_SECONDS)
            speaker_remap = _build_speaker_remap(
                prev_utterances=all_utterances,
                next_utterances=source_utterances,
                overlap_start=overlap_start,
                offset=offset,
            )
            if speaker_remap:
                _logger.info("[ASSEMBLE] Chunk %d speaker remap: %s", i, speaker_remap)

        if speaker_remap and words_added_count > 0:
            # Use words_added_count, not len(adjusted_words): deduplication
            # removes overlap words, and slicing by the pre-dedup count would
            # reach back into words from chunk i-1.
            for word in all_words[-words_added_count:]:
                speaker = word.get("speaker")
                if speaker is None:
                    continue
                raw_speaker = int(speaker)
                word["speaker"] = speaker_remap.get(raw_speaker, raw_speaker)

        for u in source_utterances:
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
                normalized_speaker = speaker_remap.get(
                    normalized_speaker, normalized_speaker
                )
            candidate_utterance = {
                **u,
                "speaker": normalized_speaker,
                "start": u_start,
                "end": u_end,
            }

            if _merge_adjacent_same_speaker_overlap(
                all_utterances, candidate_utterance
            ):
                continue

            all_utterances.append(candidate_utterance)
            all_raw_utterances.append(candidate_utterance)

    all_raw_utterances.sort(key=lambda u: u["start"])
    all_utterances = merge_utterances(all_raw_utterances)
    labeled_utterances = _attach_speaker_labels(all_utterances)
    labeled_raw_utterances = _attach_speaker_labels(all_raw_utterances)
    full_transcript = build_transcript_text(labeled_utterances)
    if not full_transcript.strip():
        # Fallback if no utterances (shouldn't happen with diarize=True)
        full_transcript = " ".join(w.get("word", "") for w in all_words)
    merged = {
        "words": all_words,
        "utterances": labeled_utterances,
        "raw_utterances": labeled_raw_utterances,
        "transcript": full_transcript,
        "raw_chunks": raw_chunks,
    }
    _logger.info("[ASSEMBLE] Total words: %d", len(merged.get("words", [])))

    return merged


def merge_channel_assemblies(
    channel_assemblies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Merge independently assembled mono channel transcripts into a single timeline.

    Each input assembly represents one physical audio channel and is treated as a
    distinct speaker lane. Speaker IDs from the underlying ASR output are ignored
    so the merged transcript preserves stable channel identity.
    """
    merged_words: List[Dict] = []
    merged_utterances: List[Dict] = []
    merged_raw_utterances: List[Dict] = []
    raw_chunks: List[Dict[str, Any]] = []

    for channel_index, assembly in enumerate(channel_assemblies):
        if not assembly:
            continue

        for word in assembly.get("words", []) or []:
            merged_words.append({**word, "speaker": channel_index})

        for utterance in assembly.get("utterances", []) or []:
            merged_utterances.append({**utterance, "speaker": channel_index})

        # Collect raw_utterances per channel so the return dict matches the
        # shape of reassemble_chunks (all five keys always present).
        for utterance in assembly.get("raw_utterances", []) or []:
            merged_raw_utterances.append({**utterance, "speaker": channel_index})

        for raw in assembly.get("raw_chunks", []) or []:
            raw_chunks.append({"channel": channel_index, "raw": raw})

    merged_words.sort(
        key=lambda w: (
            float(w.get("start", 0.0) or 0.0),
            float(w.get("end", 0.0) or 0.0),
        )
    )
    merged_utterances.sort(
        key=lambda u: (
            float(u.get("start", 0.0) or 0.0),
            float(u.get("end", 0.0) or 0.0),
        )
    )
    merged_raw_utterances.sort(
        key=lambda u: (
            float(u.get("start", 0.0) or 0.0),
            float(u.get("end", 0.0) or 0.0),
        )
    )

    labeled_utterances = _attach_speaker_labels(merged_utterances)
    labeled_raw_utterances = _attach_speaker_labels(merged_raw_utterances)
    transcript = build_transcript_text(labeled_utterances)

    return {
        "words": merged_words,
        "utterances": labeled_utterances,
        "raw_utterances": labeled_raw_utterances,
        "transcript": transcript,
        "raw_chunks": raw_chunks,
    }


def format_timestamp(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS.cs string."""
    total_ms = int(seconds * 100)
    cs = total_ms % 100
    total_s = total_ms // 100
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"
