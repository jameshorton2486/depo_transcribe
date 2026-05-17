"""Deterministic regex primitives for legal transcript formatting.

These patterns are intentionally lexical/structural only. They must never
rewrite testimony semantics.
"""
from __future__ import annotations

import re

QA_PREFIX_RE = re.compile(r"^\s*([QA])\s*[:.]\s*(.*)$", re.IGNORECASE)
CANONICAL_QA_RE = re.compile(r"^\t[QA]\.\t.+$")
SPEAKER_LABEL_RE = re.compile(r"^\s*([A-Z][A-Z .'-]+)\s*:+\s*$")
ELLIPSIS_VARIANTS_RE = re.compile(r"\.\s*\.\s*\.+")
DASH_VARIANTS_RE = re.compile(r"\s*[—–]\s*|\s*--\s*")
DUP_PUNCT_RE = re.compile(r"([,;:!?\.])\1+")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,;:.!?])")
MULTISPACE_RE = re.compile(r"[ ]{2,}")
TRAILING_SPACE_RE = re.compile(r"[ \t]+$")
