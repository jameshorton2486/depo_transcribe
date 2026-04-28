"""
spec_engine/flag_rules.py

Deterministic scopist-flag insertion for unresolved numeric and phrase garbles.
This pass inserts new FLAG blocks without altering source blocks.
"""

from __future__ import annotations

import copy
import re
from typing import List

from .models import Block, BlockType


GARBLED_NUMBER_RE = re.compile(
    r"\b(?:case|cause)\s+number\b.{0,30}(?:\$\s*\d|\b\d(?:\s+\d){3,}\b)",
    re.IGNORECASE,
)
GARBLED_CURRENCY_RE = re.compile(
    r"\$\s*\d(?:\s+\d){2,}|\$\s*\d{1,2}(?:\s+\$\s*\d{1,2})+",
    re.IGNORECASE,
)
UNRESOLVED_PHRASE_RE = re.compile(
    r"\b(?:court\s+for\s+a\s+license|mouth\s+swearing\s+(?:of\s+)?the\s+witness)\b",
    re.IGNORECASE,
)


def _make_flag_block(source_block: Block, flag_number: int, description: str, block_index: int) -> Block:
    flag_block = copy.copy(source_block)
    flag_block.text = f"[SCOPIST: FLAG {flag_number}: {description}]"
    flag_block.raw_text = flag_block.text
    flag_block.block_type = BlockType.FLAG
    # Build the FLAG block's meta fresh rather than spreading source_block.meta.
    # Spreading carried over the 'corrections' list populated by
    # apply_corrections(), so _serialize_corrections() in correction_runner.py
    # (which scans every block including FLAG blocks) counted each correction
    # once for the source block and once for every FLAG generated from it.
    flag_block.meta = {
        "is_scopist_flag": True,
        "source_block_index": block_index,
    }
    return flag_block


def generate_scopist_flags(blocks: List[Block]) -> List[Block]:
    result: List[Block] = []
    flag_number = 1

    for block_index, block in enumerate(blocks):
        result.append(block)
        if block.block_type == BlockType.FLAG:
            continue
        text = block.text or ""

        descriptions: list[str] = []
        has_garbled_number = bool(GARBLED_NUMBER_RE.search(text))
        if has_garbled_number:
            descriptions.append("possible garbled number")
        if not has_garbled_number and GARBLED_CURRENCY_RE.search(text):
            descriptions.append("possible malformed currency")
        if UNRESOLVED_PHRASE_RE.search(text):
            descriptions.append("possible unresolved Deepgram garble")
        for detail in (block.meta or {}).get("verification_flags", []):
            if detail and detail not in descriptions:
                descriptions.append(detail)

        if not text and not descriptions:
            continue

        for description in descriptions:
            result.append(_make_flag_block(block, flag_number, description, block_index))
            flag_number += 1

    return result
