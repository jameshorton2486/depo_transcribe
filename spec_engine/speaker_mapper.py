"""Speaker normalization only for deterministic transcript enforcement."""

from __future__ import annotations

import re

from .models import TranscriptBlock

_TRAILING_PUNCT_RE = re.compile(r"[:.;,\s]+$")
_MULTISPACE_RE = re.compile(r"\s+")


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


def normalize_speakers(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    """Normalize speaker and examiner formatting only."""
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
            )
        )
    return normalized

