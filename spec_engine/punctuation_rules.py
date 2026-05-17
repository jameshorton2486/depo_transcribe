"""Deterministic punctuation/whitespace rules (non-semantic only)."""
from __future__ import annotations

import re

from spec_engine.regex_patterns import (
    DASH_VARIANTS_RE,
    DUP_PUNCT_RE,
    ELLIPSIS_VARIANTS_RE,
    MULTISPACE_RE,
    SPACE_BEFORE_PUNCT_RE,
    TRAILING_SPACE_RE,
)


_SPACE_AFTER_PUNCT_RE = re.compile(r"([,;:.!?])(?![0-9\s\n\t\"')\]])")
_QUOTED_INNER_SPACE_RE = re.compile(r'"\s*([^"\n]*?)\s*"')
_MULTIBLANK_RE = re.compile(r"\n{3,}")


def normalize_punctuation_spacing(text: str) -> str:
    """Apply safe punctuation spacing normalization without semantic edits."""
    value = text or ""
    value = value.replace("...", "\u0000")
    value = SPACE_BEFORE_PUNCT_RE.sub(r"\1", value)
    value = DUP_PUNCT_RE.sub(r"\1", value)
    value = _SPACE_AFTER_PUNCT_RE.sub(r"\1 ", value)
    value = MULTISPACE_RE.sub(" ", value)
    return value.replace("<ELLIPSIS>", "...").strip()


def normalize_ellipsis(text: str) -> str:
    """Normalize ellipsis variants to canonical three-dot form."""
    value = ELLIPSIS_VARIANTS_RE.sub("...", text or "")
    value = re.sub(r"\.{4,}", "...", value)
    return re.sub(r"\s+\.\.\.", "...", value)


def normalize_dashes(text: str) -> str:
    """Normalize interruption dashes to canonical spaced double-hyphen."""
    return DASH_VARIANTS_RE.sub(" -- ", text or "")


def normalize_quote_spacing(text: str) -> str:
    """Normalize spaces inside paired quotes without changing words."""
    value = text or ""
    value = _QUOTED_INNER_SPACE_RE.sub(lambda m: f'"{m.group(1)}"', value)
    return value


def normalize_whitespace(text: str) -> str:
    """Normalize trailing spaces, tab runs, and excessive blank lines."""
    value = text or ""
    lines = [re.sub(r"[ ]+$", "", re.sub(r"\t+", "\t", line)) for line in value.splitlines()]
    return _MULTIBLANK_RE.sub("\n\n", "\n".join(lines)).strip("\n")


def enforce_deterministic_formatting(text: str) -> str:
    """Run safe formatting pipeline; preserves words and ordering."""
    value = normalize_whitespace(text)
    value = normalize_dashes(value)
    value = normalize_ellipsis(value)
    value = normalize_quote_spacing(value)
    return normalize_punctuation_spacing(value)
