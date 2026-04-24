"""
spec_engine/deepgram_patterns.py

Deterministic cleanup for a small set of known Deepgram-specific garbles that
do not fit the existing correction tables cleanly.

This pass is intentionally narrow:
- no structure changes
- no speaker changes
- no word-map changes
- no case-specific guessing
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .models import Block, CorrectionRecord


DEEPGRAM_PATTERNS: List[Tuple[str, str]] = [
    (r"\bshall\s+help\s+you\s+God\b", "so help you God"),
    (r"\bcourt\s+for\s+a\s+license\b", "court reporter, licensed"),
    (r"\bmouth\s+swearing\s+the\s+witness\b", "remote swearing of the witness"),
    (r"\bmouth\s+swearing\s+of\s+the\s+witness\b", "remote swearing of the witness"),
]


def apply_deepgram_patterns(blocks: List[Block]) -> List[Block]:
    for block_index, block in enumerate(blocks):
        text = block.text
        if not text:
            continue

        records = block.meta.setdefault("corrections", [])

        for pattern, replacement in DEEPGRAM_PATTERNS:
            new_text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            if new_text == text:
                continue

            records.append(
                CorrectionRecord(
                    original=text,
                    corrected=new_text,
                    pattern=f"deepgram_pattern:{pattern}",
                    block_index=block_index,
                )
            )
            text = new_text

        block.text = text

    return blocks
