"""Deterministic punctuation normalization aligned to safe Morson-style forms."""
from __future__ import annotations

from spec_engine.regex_patterns import DASH_VARIANTS_RE, ELLIPSIS_VARIANTS_RE


def normalize_interruptions(text: str) -> str:
    """Canonical interruption marker: spaced double hyphen."""
    return DASH_VARIANTS_RE.sub(" -- ", text or "")


def normalize_ellipsis(text: str) -> str:
    """Canonical ellipsis marker: three dots."""
    fixed = ELLIPSIS_VARIANTS_RE.sub("...", text or "")
    while "...." in fixed:
        fixed = fixed.replace("....", "...")
    fixed = fixed.replace(" ...", "...")
    return fixed
