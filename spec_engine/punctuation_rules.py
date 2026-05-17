"""Deterministic punctuation spacing rules (non-semantic)."""
from __future__ import annotations

from spec_engine.regex_patterns import DUP_PUNCT_RE, MULTISPACE_RE, SPACE_BEFORE_PUNCT_RE


def normalize_punctuation_spacing(text: str) -> str:
    """Apply safe punctuation spacing normalization without semantic edits."""
    value = text or ""
    value = SPACE_BEFORE_PUNCT_RE.sub(r"\1", value)
    value = DUP_PUNCT_RE.sub(r"\1", value)
    value = MULTISPACE_RE.sub(" ", value)
    return value
