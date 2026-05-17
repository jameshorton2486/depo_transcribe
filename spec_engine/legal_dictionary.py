"""Deterministic legal dictionary placeholders for transcript-safe lookups.

No automatic semantic rewriting is performed in this module.
"""
from __future__ import annotations

LEGAL_TERMS = {
    "objection",
    "foundation",
    "leading",
    "whereupon",
    "off the record",
}


def is_legal_term(token: str) -> bool:
    return (token or "").strip().lower() in LEGAL_TERMS
