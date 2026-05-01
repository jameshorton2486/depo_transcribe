"""Q/A structural enforcement only for classified transcript blocks."""

from __future__ import annotations

import re

from .models import TranscriptBlock

_SPEAKER_IN_QA_RE = re.compile(
    r"^\s*(?:[A-Z][A-Z.\-'\s]+:|SPEAKER\s+\d+:|BY\s+[A-Z.\-'\s]+:)"
)


def _directive_examiner_name(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("BY "):
        cleaned = cleaned[3:]
    return cleaned.rstrip(":").strip()


def enforce_structure(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    """Apply examiner tracking and structural safety checks."""
    current_examiner: str | None = None
    pending_question: TranscriptBlock | None = None
    fixed: list[TranscriptBlock] = []

    for block in blocks:
        if block.type == "directive":
            current_examiner = _directive_examiner_name(block.text)
            pending_question = None
            fixed.append(
                TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type=block.type,
                    source_type=block.source_type,
                    examiner=current_examiner,
                )
            )
            continue

        if block.type == "question":
            if pending_question is not None:
                raise ValueError("No Q without A: encountered consecutive question blocks")
            if _SPEAKER_IN_QA_RE.match(block.text):
                raise ValueError("No speaker text inside Q/A blocks: invalid question content")
            pending_question = block
            fixed.append(
                TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type=block.type,
                    source_type=block.source_type,
                    examiner=current_examiner,
                )
            )
            continue

        if block.type == "answer":
            if pending_question is None:
                raise ValueError("No orphan answers: answer encountered without a prior question")
            if _SPEAKER_IN_QA_RE.match(block.text):
                raise ValueError("No speaker text inside Q/A blocks: invalid answer content")
            pending_question = None
            fixed.append(
                TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type=block.type,
                    source_type=block.source_type,
                    examiner=current_examiner,
                )
            )
            continue

        pending_question = None
        fixed.append(
            TranscriptBlock(
                speaker=block.speaker,
                text=block.text,
                type=block.type,
                source_type=block.source_type,
                examiner=current_examiner,
            )
        )

    if pending_question is not None:
        raise ValueError("No Q without A: transcript ended with an unanswered question")

    return fixed
