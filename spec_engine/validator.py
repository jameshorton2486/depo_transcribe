"""
Validation helpers for block-based transcript processing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List

from .models import Block, BlockType


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def _normalize_for_compare(text: str) -> str:
    """
    Normalize text for near-duplicate comparison.
    Keeps terminal punctuation (.?!) which is legally meaningful.
    """
    stripped = re.sub(r"[^a-z0-9\s.?!]", "", (text or "").lower()).strip()
    return re.sub(r"\s+", " ", stripped)


def _block_start_seconds(block: Block) -> float | None:
    start = block.meta.get("start") if isinstance(block.meta, dict) else None
    if isinstance(start, (int, float)):
        return float(start)
    if block.words:
        first_start = getattr(block.words[0], "start", None)
        if isinstance(first_start, (int, float)):
            return float(first_start)
    return None


def _add_issue(result: ValidationResult, message: str, *, strict_mode: bool) -> None:
    if strict_mode:
        result.errors.append(message)
    else:
        result.warnings.append(message)


def validate_blocks(blocks: Iterable[Block], speaker_map_verified: bool = False) -> ValidationResult:
    """
    Validate a processed block stream before rendering or AI correction.
    """
    result = ValidationResult()
    block_list = list(blocks)
    try:
        from config import STRICT_MODE
        strict_mode = bool(STRICT_MODE)
    except ImportError:
        strict_mode = False

    if speaker_map_verified:
        unresolved = [
            block for block in block_list
            if not (block.speaker_role or "").strip()
            and block.block_type != BlockType.FLAG
        ]
        if unresolved:
            result.errors.append(
                f"{len(unresolved)} block(s) have unresolved speaker roles after verification."
            )

    for idx in range(1, len(block_list)):
        prev = block_list[idx - 1]
        curr = block_list[idx]
        if (
            prev.block_type == curr.block_type
            and len((curr.text or "").strip()) > 10
            and _normalize_for_compare(prev.text) == _normalize_for_compare(curr.text)
        ):
            prev_start = _block_start_seconds(prev)
            curr_start = _block_start_seconds(curr)
            if (
                prev_start is not None
                and curr_start is not None
                and abs(curr_start - prev_start) < 1.0
            ):
                result.warnings.append(
                    f"Near-duplicate adjacent blocks at indexes {idx-1} and {idx}."
                )

    for idx, block in enumerate(block_list):
        role = (block.speaker_role or "").strip()
        text_preview = (block.text or "")[:50]

        if block.block_type == BlockType.ANSWER and role not in ("WITNESS", ""):
            _add_issue(
                result,
                f"Answer block at index {idx} has non-witness role {role!r}. "
                f'Text: "{text_preview}"',
                strict_mode=strict_mode,
            )
        if block.block_type == BlockType.QUESTION and role not in (
            "ATTORNEY",
            "EXAMINING_ATTORNEY",
            "OPPOSING_COUNSEL",
            "",
        ):
            _add_issue(
                result,
                f"Question block at index {idx} has non-attorney role {role!r}. "
                f'Text: "{text_preview}"',
                strict_mode=strict_mode,
            )

        if block.block_type == BlockType.COLLOQUY and role == "WITNESS":
            _add_issue(
                result,
                f"COLLOQUY block at index {idx} has WITNESS speaker role — "
                f'likely misclassified (should be ANSWER). Text: "{text_preview}"',
                strict_mode=strict_mode,
            )
        if block.block_type == BlockType.SPEAKER and role == "WITNESS":
            _add_issue(
                result,
                f"SPEAKER block at index {idx} has WITNESS speaker role — "
                f'likely misclassified. Text: "{text_preview}"',
                strict_mode=strict_mode,
            )

    for idx, block in enumerate(block_list):
        text = (block.text or "").strip()
        if not text:
            continue
        if block.block_type == BlockType.QUESTION:
            if not text.endswith("?"):
                _add_issue(
                    result,
                    f'Question at index {idx} does not end with \'?\'. Text: "{text[:60]}"',
                    strict_mode=strict_mode,
                )
        elif block.block_type == BlockType.ANSWER:
            if text[-1] not in ".!?":
                _add_issue(
                    result,
                    f'Answer at index {idx} missing terminal punctuation. Text: "{text[:60]}"',
                    strict_mode=strict_mode,
                )

    return result
