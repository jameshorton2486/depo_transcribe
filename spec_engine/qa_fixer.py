"""Q/A structural enforcement only for classified transcript blocks."""

from __future__ import annotations

import re

from .models import TranscriptBlock

_SPEAKER_IN_QA_RE = re.compile(
    r"^\s*(?:[A-Z][A-Z.\-'\s]+:|SPEAKER\s+\d+:|BY\s+[A-Z.\-'\s]+:)"
)
QUESTION_WORDS = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "did",
    "do",
    "does",
    "is",
    "are",
    "was",
    "were",
    "can",
    "could",
    "would",
    "will",
    "have",
    "has",
    "had",
    "please",
)
STANDALONE_ANSWER_WORDS = {
    "yes",
    "no",
    "yeah",
    "nope",
    "correct",
    "incorrect",
    "right",
    "wrong",
    "i do",
    "i did",
    "i didn't",
    "uh-huh",
    "nuh-uh",
    "okay",
    "ok",
}


def _directive_examiner_name(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("BY "):
        cleaned = cleaned[3:]
    return cleaned.rstrip(":").strip()


def enforce_qa_sequence(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    """
    FINAL PASS: Enforce strict Q/A structure.

    This does NOT replace detection logic.
    It CORRECTS structure after detection.
    """
    fixed: list[TranscriptBlock] = []
    last_type: str | None = None

    for block in blocks:
        text = block.text.strip().lower()
        normalized = block

        if block.type not in {"directive", "oath"}:
            if any(text.startswith(word) for word in QUESTION_WORDS) or text.endswith("?"):
                normalized = TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type="question",
                    source_type=block.source_type,
                    examiner=block.examiner,
                )
            elif text in STANDALONE_ANSWER_WORDS or len(text.split()) <= 6:
                if last_type == "question":
                    normalized = TranscriptBlock(
                        speaker=block.speaker,
                        text=block.text,
                        type="answer",
                        source_type=block.source_type,
                        examiner=block.examiner,
                    )

        if normalized.type == "answer" and last_type != "question":
            if fixed and fixed[-1].type == "question":
                previous = fixed[-1]
                fixed[-1] = TranscriptBlock(
                    speaker=previous.speaker,
                    text=f"{previous.text} {normalized.text}".strip(),
                    type=previous.type,
                    source_type=previous.source_type,
                    examiner=previous.examiner,
                )
                last_type = fixed[-1].type
                continue

        fixed.append(normalized)
        last_type = normalized.type

    return fixed


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

    fixed = enforce_qa_sequence(fixed)

    pending_question = None
    for block in fixed:
        if block.type == "question":
            if pending_question is not None:
                raise ValueError("No Q without A: encountered consecutive question blocks")
            pending_question = block
        elif block.type == "answer":
            if pending_question is None:
                raise ValueError("No orphan answers: answer encountered without a prior question")
            pending_question = None
        else:
            pending_question = None

    if pending_question is not None:
        raise ValueError("No Q without A: transcript ended with an unanswered question")

    return fixed
