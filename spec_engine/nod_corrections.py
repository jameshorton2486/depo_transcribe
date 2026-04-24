"""
spec_engine/nod_corrections.py

Deterministic case-specific corrections sourced from JobConfig.
This module only applies explicit confirmed spellings and preserves raw text.
"""

from __future__ import annotations

import re
from typing import List

from .models import Block, CorrectionRecord, JobConfig


def _get_confirmed_spellings(job_config: JobConfig) -> dict[str, str]:
    if isinstance(job_config, dict):
        confirmed = job_config.get("confirmed_spellings", {}) or {}
    else:
        confirmed = getattr(job_config, "confirmed_spellings", {}) or {}
    return confirmed if isinstance(confirmed, dict) else {}


def apply_nod_corrections(blocks: List[Block], job_config: JobConfig) -> List[Block]:
    confirmed_spellings = _get_confirmed_spellings(job_config)
    if not confirmed_spellings:
        return blocks

    for block_index, block in enumerate(blocks):
        text = block.text
        if not text:
            continue

        records = block.meta.setdefault("corrections", [])

        for wrong, correct in confirmed_spellings.items():
            if not wrong or not correct:
                continue

            pattern = re.compile(r"\b" + re.escape(str(wrong)) + r"\b", re.IGNORECASE)
            new_text = pattern.sub(str(correct), text)
            if new_text == text:
                continue

            records.append(
                CorrectionRecord(
                    original=text,
                    corrected=new_text,
                    pattern=f"nod_correction:{wrong}",
                    block_index=block_index,
                )
            )
            text = new_text

        block.text = text

    return blocks
