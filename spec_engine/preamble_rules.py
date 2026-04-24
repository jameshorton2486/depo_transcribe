"""
spec_engine/preamble_rules.py

Deterministic cleanup for reporter-preamble boilerplate near the start of a
transcript. This pass is intentionally bounded to the opening blocks only.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .models import Block, CorrectionRecord


PREAMBLE_SCAN_LIMIT = 10
PREAMBLE_SIGNALS = ("court reporter", "csr", "deposition", "sworn")
PREAMBLE_REPLACEMENTS: List[Tuple[str, str]] = [
    (r"\bcourt\s+for\s+a\s+license\b", "court reporter, licensed"),
    (r"\bcsr\s+number\b", "CSR No."),
    (r"\bso\s+help\s+you\s+god\b", "so help you God"),
]


def _looks_like_preamble(text: str) -> bool:
    lowered = text.lower()
    return any(signal in lowered for signal in PREAMBLE_SIGNALS)


def apply_preamble_rules(blocks: List[Block]) -> List[Block]:
    for block_index, block in enumerate(blocks[:PREAMBLE_SCAN_LIMIT]):
        text = block.text
        if not text or not _looks_like_preamble(text):
            continue

        records = block.meta.setdefault("corrections", [])

        for pattern, replacement in PREAMBLE_REPLACEMENTS:
            new_text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            if new_text == text:
                continue

            records.append(
                CorrectionRecord(
                    original=text,
                    corrected=new_text,
                    pattern=f"preamble_rule:{pattern}",
                    block_index=block_index,
                )
            )
            text = new_text

        block.text = text

    return blocks
