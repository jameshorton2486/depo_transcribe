"""Deterministic legal dictionary helpers.

Contains replacement support only; no semantic generation.
"""
from __future__ import annotations

from collections.abc import Iterable

DEFAULT_LEGAL_TERMS: tuple[str, ...] = (
    "objection",
    "foundation",
    "privilege",
    "voir dire",
    "subpoena duces tecum",
    "cause number",
)


def is_legal_term(value: str) -> bool:
    """Return True when value matches a known legal term case-insensitively."""
    text = str(value or "").strip().lower()
    return text in DEFAULT_LEGAL_TERMS


def build_case_dictionary(terms: Iterable[str]) -> dict[str, str]:
    """Build deterministic identity mapping for case terms.

    This mapping can be merged with per-case correction maps.
    """
    out: dict[str, str] = {}
    for term in terms:
        clean = str(term or "").strip()
        if clean:
            out[clean.lower()] = clean
    return out
