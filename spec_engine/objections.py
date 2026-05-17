"""Deterministic objection + parenthetical formatting helpers.

Formatting-only transforms; no semantic rewriting.
"""
from __future__ import annotations

import re

_OBJECTION_PREFIX_RE = re.compile(r"^\s*objection\s*[,:.-]*\s*", re.IGNORECASE)
_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_PAREN_RE = re.compile(r"^\s*\((.*?)\)\s*$")


def normalize_objection_line(text: str) -> str:
    """Normalize common objection line prefixes.

    Example: "objection form" -> "Objection, form."
    """
    raw = str(text or "").strip()
    if not raw.lower().startswith("objection"):
        return raw

    tail = _OBJECTION_PREFIX_RE.sub("", raw)
    tail = _MULTI_SPACE_RE.sub(" ", tail).strip(" .,:;")
    if not tail:
        return "Objection."
    return f"Objection, {tail.lower()}."


def normalize_parenthetical_line(text: str) -> str:
    """Normalize parenthetical wrapper and punctuation only."""
    raw = str(text or "").strip()
    m = _PAREN_RE.match(raw)
    if not m:
        return raw
    inner = _MULTI_SPACE_RE.sub(" ", m.group(1).strip())
    if inner and inner[-1] not in ".?!":
        inner += "."
    if inner:
        inner = inner[0].upper() + inner[1:]
    return f"({inner})" if inner else "()"


def looks_like_parenthetical(text: str) -> bool:
    return bool(_PAREN_RE.match(str(text or "").strip()))
