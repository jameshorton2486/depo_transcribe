from __future__ import annotations

import re
from typing import List

# ---------------------------------------
# CONSTANTS
# ---------------------------------------

INDENT = "    "
DOUBLE_SPACE = "\n\n"
_LEADING_QA_RE = re.compile(r"^\s*[QA]\.\s*")
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


# ---------------------------------------
# SAFE UTILITIES
# ---------------------------------------


def normalize_time(text: str) -> str:
    """
    Convert time formats:
    08:12 AM  8:12 a.m.
    """
    text = re.sub(r"\b0?(\d{1,2}:\d{2})\s*AM\b", r"\1 a.m.", text, flags=re.IGNORECASE)
    text = re.sub(r"\b0?(\d{1,2}:\d{2})\s*PM\b", r"\1 p.m.", text, flags=re.IGNORECASE)
    text = re.sub(r"\b([ap]\.m\.)\.", r"\1", text, flags=re.IGNORECASE)
    return text


def double_space_after_punctuation(text: str) -> str:
    return re.sub(r"([.!?])\s+", r"\1  ", str(text or "").strip())


def normalize_speaker(speaker: str | None) -> str:
    """
    Normalize speaker label to uppercase with colon.
    """
    if not speaker:
        return ""

    speaker = speaker.strip().upper()

    if not speaker.endswith(":"):
        speaker += ":"

    return speaker


# ---------------------------------------
# Q/A FORMATTING
# ---------------------------------------


def format_qa(block) -> str:
    """
    Strict UFM Q/A formatting.
    """
    text = _LEADING_QA_RE.sub("", block.text.strip(), count=1)
    text = normalize_time(double_space_after_punctuation(text))

    if block.type == "question":
        return f"\tQ.\t{text}"

    if block.type == "answer":
        return f"\tA.\t{text}"

    return text


# ---------------------------------------
# COLLOQUY FORMATTING (GROUPED)
# ---------------------------------------


def format_colloquy(blocks: List, start_index: int):
    """
    Group consecutive same-speaker colloquy into one block.
    """
    speaker = normalize_speaker(blocks[start_index].speaker)

    lines = [f"{INDENT}{speaker}"]

    i = start_index

    while i < len(blocks):
        block = blocks[i]

        if block.type != "colloquy":
            break

        if normalize_speaker(block.speaker) != speaker:
            break

        text = normalize_time(double_space_after_punctuation(block.text.strip()))
        lines.append(f"{INDENT*2}{text}")

        i += 1

    return "\n".join(lines), i


# ---------------------------------------
# DIRECTIVE FORMATTING
# ---------------------------------------


def format_directive(block) -> str:
    """
    Format directives like:
    BY MS. MALONEY:
    """
    text = block.text.strip().upper()
    return f"\n{text}\n"


def _split_sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in _SENTENCE_RE.findall(str(text or "").strip())
        if part.strip()
    ]


def split_blocks_into_paragraphs(blocks: List) -> List:
    split = []

    for block in blocks:
        if getattr(block, "type", None) != "answer":
            split.append(block)
            continue

        content = _LEADING_QA_RE.sub("", block.text.strip(), count=1)
        sentences = _split_sentences(content)
        if len(sentences) <= 2:
            split.append(block)
            continue

        for index in range(0, len(sentences), 2):
            split.append(
                type(block)(
                    speaker=block.speaker,
                    text=" ".join(sentences[index : index + 2]).strip(),
                    type=block.type,
                    source_type=block.source_type,
                    examiner=block.examiner,
                )
            )

    return split


# ---------------------------------------
# MAIN EMITTER
# ---------------------------------------


def format_blocks_to_text(blocks: List) -> str:
    """
    Final UFM-compliant output generator.
    """

    blocks = split_blocks_into_paragraphs(blocks)
    output = []
    i = 0

    while i < len(blocks):
        block = blocks[i]

        # -----------------------------------
        # Q/A
        # -----------------------------------
        if block.type in ("question", "answer"):
            if block.type == "answer" and output and output[-1] != "":
                output.append("")
            output.append(format_qa(block))

            # Add spacing after A (Q/A pair separation)
            if block.type == "answer":
                output.append("")  # blank line

            i += 1
            continue

        # -----------------------------------
        # DIRECTIVE
        # -----------------------------------
        if block.type == "directive":
            output.append(format_directive(block))
            i += 1
            continue

        # -----------------------------------
        # COLLOQUY
        # -----------------------------------
        if block.type == "colloquy":
            formatted, new_i = format_colloquy(blocks, i)
            output.append(formatted)
            output.append("")  # spacing after speaker block
            i = new_i
            continue

        # -----------------------------------
        # FALLBACK
        # -----------------------------------
        text = normalize_time(double_space_after_punctuation(block.text.strip()))
        output.append(text)
        i += 1

    # Clean extra whitespace
    final_text = "\n".join(output)

    # Remove triple newlines
    final_text = re.sub(r"\n{3,}", "\n\n", final_text)

    return final_text.strip("\n")


def emit_blocks(blocks: List) -> str:
    return format_blocks_to_text(blocks)
