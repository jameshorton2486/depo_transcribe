"""Speaker normalization only for deterministic transcript enforcement."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable

from .models import TranscriptBlock, TranscriptWord


def _propagate_speaker_to_words(
    words: list[TranscriptWord] | None,
    new_speaker: str,
) -> list[TranscriptWord] | None:
    """Rebuild a word list with each word's speaker set to `new_speaker`.

    Step B.1 policy: when speaker_mapper reassigns a block's speaker,
    the per-word `speaker` field is propagated so downstream consumers
    see "who is speaking this word in the final transcript," not
    Deepgram's pre-correction guess. Uses `dataclasses.replace` to
    match the rebuild-not-mutate convention used elsewhere in
    spec_engine.

    See docs/plans/_archive/step_b1_word_carry_merge_split_2026-05-12.md.
    """
    if words is None:
        return None
    return [dataclasses.replace(w, speaker=new_speaker) for w in words]

_TRAILING_PUNCT_RE = re.compile(r"[:.;,\s]+$")
_MULTISPACE_RE = re.compile(r"\s+")
ROLE_ATTORNEY = "ATTORNEY"
ROLE_WITNESS = "WITNESS"
ROLE_COURT_REPORTER = "COURT_REPORTER"
ROLE_VIDEOGRAPHER = "VIDEOGRAPHER"
ROLE_UNKNOWN = "UNKNOWN"


def normalize_speaker_label(label: str) -> str:
    """Uppercase speaker labels and normalize trailing punctuation to a colon."""
    cleaned = _MULTISPACE_RE.sub(" ", str(label or "").strip())
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned).upper()
    if not cleaned:
        return "UNKNOWN:"
    if not cleaned.endswith(":"):
        cleaned = f"{cleaned}:"
    return cleaned


def normalize_examiner_name(name: str) -> str:
    """Uppercase examiner identity without the BY prefix or trailing colon."""
    cleaned = _MULTISPACE_RE.sub(" ", str(name or "").strip())
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned).upper()
    if cleaned.startswith("BY "):
        cleaned = cleaned[3:].strip()
    return cleaned


def normalize_directive_text(text: str) -> str:
    """Normalize BY-line formatting without changing identity."""
    examiner = normalize_examiner_name(text)
    return f"BY {examiner}:" if examiner else "BY UNKNOWN:"


def detect_speaker_role(block: TranscriptBlock) -> str:
    text = str(block.text or "").strip().lower()
    speaker = str(block.speaker or "").strip().upper().rstrip(":")

    if speaker == "COURT REPORTER":
        return ROLE_COURT_REPORTER

    if speaker == "VIDEOGRAPHER":
        return ROLE_VIDEOGRAPHER

    if text.startswith(("yes", "no", "i do", "i did", "i don't")):
        return ROLE_WITNESS

    if text.endswith("?"):
        return ROLE_ATTORNEY

    return ROLE_UNKNOWN


def smooth_speaker_sequence(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    smoothed = list(blocks)

    for index in range(1, len(smoothed) - 1):
        previous = smoothed[index - 1]
        current = smoothed[index]
        following = smoothed[index + 1]

        if (
            current.speaker != previous.speaker
            and previous.speaker == following.speaker
        ):
            if len(str(current.text or "").split()) < 6:
                smoothed[index] = TranscriptBlock(
                    speaker=previous.speaker,
                    text=current.text,
                    type=current.type,
                    source_type=current.source_type,
                    examiner=current.examiner,
                    words=_propagate_speaker_to_words(
                        current.words, previous.speaker
                    ),
                )

    return smoothed


def enforce_role_consistency(blocks: list[TranscriptBlock]) -> list[str]:
    roles: list[str] = []
    last_role: str | None = None

    for block in blocks:
        role = detect_speaker_role(block)
        if role == ROLE_UNKNOWN and last_role:
            role = last_role
        roles.append(role)
        last_role = role

    return roles


def normalize_speakers(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    """Normalize speaker and examiner formatting only."""
    blocks = smooth_speaker_sequence(blocks)
    _roles = enforce_role_consistency(blocks)

    normalized: list[TranscriptBlock] = []
    for block in blocks:
        speaker = normalize_speaker_label(block.speaker)
        examiner = normalize_examiner_name(block.examiner) if block.examiner else None
        text = block.text
        if block.type == "directive":
            text = normalize_directive_text(block.text)
        normalized.append(
            TranscriptBlock(
                speaker=speaker,
                text=text,
                type=block.type,
                source_type=block.source_type,
                examiner=examiner,
                words=_propagate_speaker_to_words(block.words, speaker),
            )
        )
    return normalized
