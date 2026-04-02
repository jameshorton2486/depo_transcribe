"""
Q/A structure repair for block-based processing.
"""

from __future__ import annotations

import re
from typing import Any, List

from .models import Block, BlockType


ANSWER_TOKENS = (
    "yes", "no", "yeah", "yep", "nope",
    "uh-huh", "uh uh", "mm-hmm", "correct", "right",
    "yes,", "no,", "yes sir", "no sir", "yes ma'am", "no ma'am",
    "i do", "i don't", "i do not", "i did", "i did not",
    "i remember", "i recall", "i don't recall", "i don't remember",
)

TOKEN_RE = re.compile(r"[a-z0-9']+")
REPORTER_PREAMBLE_START_RE = re.compile(
    r"\bthis\s+is\s+cause\s+number\b"
    r"|\bcause\s+number\b"
    r"|\bthis\s+deposition\s+is\s+being\s+taken\s+in\s+accordance\s+with\b"
    r"|\bcounsel,\s+will\s+you\s+please\s+state\s+your\s+agreement\b",
    re.IGNORECASE,
)


def _witness_identity(job_config: Any, original: Block) -> tuple[Any, str | None]:
    if hasattr(job_config, "witness_id"):
        witness_id = getattr(job_config, "witness_id", original.speaker_id)
    elif isinstance(job_config, dict):
        witness_id = job_config.get("witness_id", original.speaker_id)
    else:
        witness_id = original.speaker_id

    witness_name = None
    if hasattr(job_config, "speaker_map"):
        witness_name = (getattr(job_config, "speaker_map", {}) or {}).get(witness_id)
    elif isinstance(job_config, dict):
        speaker_map = job_config.get("speaker_map", {}) or {}
        witness_name = speaker_map.get(witness_id)
        if witness_name is None:
            witness_name = speaker_map.get(str(witness_id))
    return witness_id, witness_name


def _is_reporter_block(block: Block) -> bool:
    speaker_name = (block.speaker_name or "").upper()
    speaker_role = (block.speaker_role or "").upper()
    return "REPORTER" in speaker_name or "REPORTER" in speaker_role


def _merge_reporter_preamble_blocks(blocks: List[Block]) -> List[Block]:
    """
    Join the reporter's opening multi-paragraph preamble before later Q/A fixes.
    """
    if not blocks:
        return blocks

    result: List[Block] = []
    i = 0
    while i < len(blocks):
        current = blocks[i]
        if (
            _is_reporter_block(current)
            and REPORTER_PREAMBLE_START_RE.search((current.text or "").strip())
        ):
            merged = current
            j = i + 1
            while j < len(blocks):
                nxt = blocks[j]
                if not _is_reporter_block(nxt):
                    break
                if merged.speaker_id != nxt.speaker_id:
                    break
                merged = Block(
                    raw_text=((merged.raw_text or "") + " " + (nxt.raw_text or "")).strip(),
                    text=((merged.text or "").rstrip() + " " + (nxt.text or "").lstrip()).strip(),
                    speaker_id=merged.speaker_id,
                    speaker_name=merged.speaker_name,
                    speaker_role=merged.speaker_role,
                    block_type=merged.block_type,
                    words=list(merged.words) + list(nxt.words),
                    flags=list(merged.flags),
                    meta={**merged.meta, "merged_reporter_preamble": True},
                )
                j += 1
            result.append(merged)
            i = j
            continue

        result.append(current)
        i += 1
    return result


def split_inline_answers(blocks: List[Block], job_config: Any = None) -> List[Block]:
    """
    Split blocks like 'Did you go there? Yes.' into Q + A blocks.
    """
    new_blocks: List[Block] = []

    for block in blocks:
        if block.block_type != BlockType.QUESTION:
            new_blocks.append(block)
            continue

        text = block.text.strip()
        match = re.match(r"(.+\?)\s+(.+)", text)
        if not match:
            new_blocks.append(block)
            continue

        q_part, a_part = match.groups()
        if not a_part.lower().startswith(ANSWER_TOKENS):
            new_blocks.append(block)
            continue

        witness_id, witness_name = _witness_identity(job_config, block)
        q_block = Block(
            raw_text=block.raw_text,
            text=q_part.strip(),
            speaker_id=block.speaker_id,
            speaker_name=block.speaker_name,
            block_type=BlockType.QUESTION,
            words=list(block.words),
            meta=dict(block.meta),
        )
        a_block = Block(
            raw_text=block.raw_text,
            text=a_part.strip(),
            speaker_id=witness_id,
            speaker_name=witness_name,
            block_type=BlockType.ANSWER,
            words=[],
            meta={**block.meta, "split_from_question": True},
        )
        new_blocks.extend([q_block, a_block])

    return new_blocks


def _merge_orphaned_continuations(blocks: List[Block]) -> List[Block]:
    """
    Merge a tiny continuation block into the preceding same-speaker block.
    Handles Deepgram pause fragmentation.
    """
    if not blocks:
        return blocks

    result = [blocks[0]]
    mergeable_types = (BlockType.QUESTION, BlockType.ANSWER, BlockType.COLLOQUY)

    for block in blocks[1:]:
        prev = result[-1]
        word_count = len((block.text or "").split())
        same_speaker = prev.speaker_id == block.speaker_id
        same_type = prev.block_type == block.block_type
        is_tiny = word_count <= 3
        is_mergeable = block.block_type in mergeable_types

        if same_speaker and same_type and is_tiny and is_mergeable:
            merged = Block(
                raw_text=((prev.raw_text or "") + " " + (block.raw_text or "")).strip(),
                text=((prev.text or "").rstrip() + " " + (block.text or "").lstrip()).strip(),
                speaker_id=prev.speaker_id,
                speaker_name=prev.speaker_name,
                speaker_role=prev.speaker_role,
                block_type=prev.block_type,
                words=list(prev.words) + list(block.words),
                flags=list(prev.flags),
                meta={**prev.meta, "merged_continuation": True},
            )
            result[-1] = merged
        else:
            result.append(block)
    return result


def _remove_near_duplicate_blocks(blocks: List[Block]) -> List[Block]:
    """
    Remove near-duplicate consecutive blocks from chunk overlap artifacts.
    """
    if not blocks:
        return blocks

    result = [blocks[0]]
    for block in blocks[1:]:
        prev = result[-1]
        if prev.block_type != block.block_type or prev.speaker_id != block.speaker_id:
            result.append(block)
            continue

        prev_words = set(TOKEN_RE.findall((prev.text or "").lower()))
        curr_words = set(TOKEN_RE.findall((block.text or "").lower()))
        if not prev_words or not curr_words:
            result.append(block)
            continue

        union = prev_words | curr_words
        similarity = len(prev_words & curr_words) / len(union) if union else 0.0
        prev_start = (prev.meta or {}).get("start")
        curr_start = (block.meta or {}).get("start")
        try:
            time_diff = abs(float(curr_start) - float(prev_start))
        except (TypeError, ValueError):
            time_diff = None

        if similarity >= 0.85 and time_diff is not None and time_diff < 1.0:
            if len(block.text or "") > len(prev.text or ""):
                result[-1] = block
        else:
            result.append(block)
    return result


def fix_qa_structure(blocks: List[Block], job_config: Any = None) -> List[Block]:
    """
    Apply Q/A structural repairs in priority order.
    """
    blocks = _merge_reporter_preamble_blocks(blocks)
    blocks = split_inline_answers(blocks, job_config=job_config)
    blocks = _merge_orphaned_continuations(blocks)
    blocks = _remove_near_duplicate_blocks(blocks)
    return blocks
