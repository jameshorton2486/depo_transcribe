"""
Validation helpers for block-based transcript processing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List

from .models import Block, BlockType


__all__ = ["ValidationResult", "validate_blocks"]


# ── Tunable thresholds ───────────────────────────────────────────────────────
# Minimum block-text length (after strip) below which near-duplicate detection
# is skipped. Short responses ("Yes.", "Correct.") legitimately repeat and
# should not trigger duplicate warnings.
#
# NOTE: This is intentionally distinct from corrections.py's
# DUPLICATE_BLOCK_MIN_LEN (= 15). That constant gates *removal* of duplicates
# during correction; this one gates *warning* during validation. They are
# tuned independently and should not be unified.
DUPLICATE_CHECK_MIN_LEN = 10

# Time window (seconds) within which two identical-text blocks from the same
# speaker are flagged as a chunk-overlap artifact rather than a real
# repetition. Matches the same-named threshold in qa_fixer.py and
# corrections.py.
DUPLICATE_TIME_WINDOW_S = 1.0

# Preview-string lengths used in error messages. Different by category for
# historical reasons — preserved verbatim so existing tests asserting on
# message contents continue to match.
ROLE_MISMATCH_PREVIEW_LEN = 50
PUNCTUATION_PREVIEW_LEN = 60


# ── Pre-compiled normalization patterns ──────────────────────────────────────
# Used by _normalize_for_compare(); compiled once at import so the
# duplicate-detection loop doesn't recompile per block pair.
_NON_TEXT_CHARS_RE = re.compile(r"[^a-z0-9\s.?!]")
_WHITESPACE_RE = re.compile(r"\s+")


# ── STRICT_MODE accessor ─────────────────────────────────────────────────────
# Reads STRICT_MODE from the top-level `config` module dynamically so that
# tests can monkey-patch the attribute without the module-level capture going
# stale. Same pattern used in corrections.py for load_active_rules.

def _get_strict_mode() -> bool:
    try:
        import config  # type: ignore[import-not-found]
        return bool(getattr(config, "STRICT_MODE", False))
    except ImportError:
        return False


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
    stripped = _NON_TEXT_CHARS_RE.sub("", (text or "").lower()).strip()
    return _WHITESPACE_RE.sub(" ", stripped)


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
    strict_mode = _get_strict_mode()

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
            and len((curr.text or "").strip()) > DUPLICATE_CHECK_MIN_LEN
            and _normalize_for_compare(prev.text) == _normalize_for_compare(curr.text)
        ):
            prev_start = _block_start_seconds(prev)
            curr_start = _block_start_seconds(curr)
            if (
                prev_start is not None
                and curr_start is not None
                and abs(curr_start - prev_start) < DUPLICATE_TIME_WINDOW_S
            ):
                result.warnings.append(
                    f"Near-duplicate adjacent blocks at indexes {idx-1} and {idx}."
                )

    for idx, block in enumerate(block_list):
        role = (block.speaker_role or "").strip()
        text_preview = (block.text or "")[:ROLE_MISMATCH_PREVIEW_LEN]

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
                    f'Question at index {idx} does not end with \'?\'. '
                    f'Text: "{text[:PUNCTUATION_PREVIEW_LEN]}"',
                    strict_mode=strict_mode,
                )
        elif block.block_type == BlockType.ANSWER:
            if text[-1] not in ".!?":
                _add_issue(
                    result,
                    f'Answer at index {idx} missing terminal punctuation. '
                    f'Text: "{text[:PUNCTUATION_PREVIEW_LEN]}"',
                    strict_mode=strict_mode,
                )

    return result
