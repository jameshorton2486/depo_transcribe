"""Classify raw transcript blocks into deterministic structural types."""

from __future__ import annotations

import re
from typing import Any

from .models import TranscriptBlock
from .ufm_rules import is_answer_loose, is_question_loose

_OATH_RE = re.compile(
    r"\b(swear|sworn|solemnly swear|under penalty of perjury|so help you god|affirm)\b",
    re.IGNORECASE,
)


def _looks_like_directive(text: str) -> bool:
    cleaned = str(text or "").strip().upper()
    return cleaned.startswith("BY ") or cleaned.startswith("BY\t")


def _is_colloquy_speaker(speaker: str) -> bool:
    return str(speaker or "").strip().upper().rstrip(":") in {
        "VIDEOGRAPHER",
        "COURT REPORTER",
    }


def _classify_type(speaker: str, text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.startswith("\tQ.\t") or is_question_loose(stripped):
        return "question"
    if stripped.startswith("\tA.\t") or is_answer_loose(stripped):
        return "answer"
    if _looks_like_directive(stripped):
        return "directive"
    if _OATH_RE.search(stripped):
        return "oath"
    if _is_colloquy_speaker(speaker):
        return "colloquy"
    return "colloquy"


def classify_blocks(blocks: list[dict[str, Any]]) -> list[TranscriptBlock]:
    """Classify block-builder dictionaries into structural transcript blocks."""
    classified: list[TranscriptBlock] = []
    for raw in blocks:
        speaker = str(raw.get("speaker", "UNKNOWN") or "").strip()
        source_type = str(raw.get("type", "") or "")
        block_type = _classify_type(speaker, str(raw.get("text", "")))
        text = str(raw.get("text", "") or "").strip()
        classified.append(
            TranscriptBlock(
                speaker=speaker,
                text=text,
                type=block_type,
                source_type=source_type,
            )
        )
    return classified
