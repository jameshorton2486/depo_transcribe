"""Classify raw transcript blocks into deterministic structural types."""

from __future__ import annotations

import re
from typing import Any

from .models import TranscriptBlock, TranscriptWord
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


def _convert_word_dicts(
    raw_words: list[dict[str, Any]] | None,
) -> list[TranscriptWord] | None:
    """Convert Deepgram word dicts into TranscriptWord instances.

    Returns None when:
    - `raw_words` is None or empty
    - Any word dict lacks required fields or has malformed types

    The all-or-nothing semantic is deliberate: Step C/D treats None as
    "no carried words for this block" and degrades to plain rendering.
    Constructing partial / inconsistent TranscriptWord lists would mask
    upstream data shape problems and silently corrupt downstream
    highlighting.
    """
    if not raw_words:
        return None

    words: list[TranscriptWord] = []
    for w in raw_words:
        try:
            words.append(
                TranscriptWord(
                    text=str(w["word"]),
                    start=float(w["start"]),
                    end=float(w["end"]),
                    confidence=float(w.get("confidence", 0.0)),
                    speaker=w.get("speaker"),
                    punctuated_word=w.get("punctuated_word"),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None
    return words


def classify_blocks(blocks: list[dict[str, Any]]) -> list[TranscriptBlock]:
    """Classify block-builder dictionaries into structural transcript blocks.

    Step B.0: word-level data from `raw["words"]` is converted to
    TranscriptWord instances and attached to the block. When source
    data is missing or malformed, the block's `words` field is None.
    """
    classified: list[TranscriptBlock] = []
    for raw in blocks:
        speaker = str(raw.get("speaker", "UNKNOWN") or "").strip()
        source_type = str(raw.get("type", "") or "")
        block_type = _classify_type(speaker, str(raw.get("text", "")))
        text = str(raw.get("text", "") or "").strip()
        words = _convert_word_dicts(raw.get("words"))
        classified.append(
            TranscriptBlock(
                speaker=speaker,
                text=text,
                type=block_type,
                source_type=source_type,
                words=words,
            )
        )
    return classified
