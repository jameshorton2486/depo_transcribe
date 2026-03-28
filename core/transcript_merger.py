"""
Post-process Deepgram utterances to reduce over-splitting noise.
"""

from __future__ import annotations

from typing import Any


def _copy_utterance(utterance: dict[str, Any]) -> dict[str, Any]:
    copied = dict(utterance)
    copied["words"] = list(utterance.get("words", []))
    return copied


def merge_utterances(
    utterances: list[dict[str, Any]],
    gap_threshold_seconds: float = 1.5,
    min_word_count: int = 2,
) -> list[dict[str, Any]]:
    """
    Merge nearby consecutive utterances from the same speaker.

    Short utterances from a different speaker are kept separate but flagged for
    downstream review because they are common diarization failure cases.
    """
    if not utterances:
        return []

    merged: list[dict[str, Any]] = []
    current = _copy_utterance(utterances[0])

    for utterance in utterances[1:]:
        next_utt = _copy_utterance(utterance)
        same_speaker = next_utt.get("speaker") == current.get("speaker")
        gap = float(next_utt.get("start", 0) or 0) - float(current.get("end", 0) or 0)
        word_count = len((next_utt.get("transcript") or "").split())
        is_short = word_count < min_word_count

        if same_speaker and gap <= gap_threshold_seconds:
            current_text = (current.get("transcript") or "").strip()
            next_text = (next_utt.get("transcript") or "").strip()
            current["transcript"] = " ".join(part for part in (current_text, next_text) if part)
            current["end"] = next_utt.get("end", current.get("end"))
            current["words"] = list(current.get("words", [])) + list(next_utt.get("words", []))
            continue

        if is_short and gap <= 0.5:
            next_utt["flagged"] = True
            next_utt["flag_reason"] = "short_utterance_possible_diarization_error"

        merged.append(current)
        current = next_utt

    merged.append(current)
    return merged
