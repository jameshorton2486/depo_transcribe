"""Final output formatting for deterministic transcript blocks."""

from __future__ import annotations

import re

from .models import TranscriptBlock

_LEADING_QA_RE = re.compile(r"^\s*[QA]\.\s*")


def _double_space_after_punctuation(text: str) -> str:
    return re.sub(r"([.!?])\s+", r"\1  ", str(text or "").strip())


def _align_continuation(text: str, prefix: str) -> str:
    parts = [part.strip() for part in str(text or "").splitlines()]
    if not parts:
        return prefix
    first = f"{prefix}{parts[0]}"
    if len(parts) == 1:
        return first
    continuation = "\n".join(f"\t\t{part}" for part in parts[1:] if part)
    return f"{first}\n{continuation}" if continuation else first


def _qa_text(text: str, marker: str) -> str:
    stripped = _LEADING_QA_RE.sub("", str(text or "").strip(), count=1)
    return _align_continuation(_double_space_after_punctuation(stripped), f"\t{marker}\t")


def _speaker_body_text(text: str) -> str:
    return "\n".join(
        f"\t{_double_space_after_punctuation(line.strip())}"
        for line in str(text or "").splitlines()
        if line.strip()
    )


def _directive_line(block: TranscriptBlock) -> str:
    examiner = block.examiner or block.text.rstrip(":").removeprefix("BY ").strip()
    return f"BY {examiner}:"


def emit_blocks(blocks: list[TranscriptBlock]) -> str:
    """Render classified blocks into strict final transcript text."""
    output: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]

        if block.type == "question":
            output.append(_qa_text(block.text, "Q."))
            index += 1
            continue

        if block.type == "answer":
            output.append(_qa_text(block.text, "A."))
            index += 1
            continue

        if block.type == "directive":
            output.append(_directive_line(block))
            index += 1
            continue

        speaker = block.speaker
        grouped_lines = [block.text]
        index += 1
        while index < len(blocks):
            candidate = blocks[index]
            if candidate.type not in {"colloquy", "oath"}:
                break
            if candidate.speaker != speaker:
                break
            grouped_lines.append(candidate.text)
            index += 1

        body = _speaker_body_text("\n".join(grouped_lines))
        output.append(f"{speaker}\n{body}" if body else speaker)

    return "\n\n".join(part for part in output if part.strip()).strip()
