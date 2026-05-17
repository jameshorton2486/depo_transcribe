"""Deterministic UFM-format enforcement helpers."""
from __future__ import annotations

from spec_engine.regex_patterns import CANONICAL_QA_RE, QA_PREFIX_RE


_LOOSE_Q_RE = ("q", "q.", "q:")
_LOOSE_A_RE = ("a", "a.", "a:")


def is_qa_formatted(line: str) -> bool:
    """Return True when line uses canonical UFM Q/A tab format."""
    return bool(CANONICAL_QA_RE.match(line or ""))


def is_question_loose(line: str) -> bool:
    """Detect loose question prefixes without mutating text."""
    text = (line or "").lstrip()
    lowered = text.lower()
    return any(lowered.startswith(prefix + " ") or lowered == prefix for prefix in _LOOSE_Q_RE)


def is_answer_loose(line: str) -> bool:
    """Detect loose answer prefixes without mutating text."""
    text = (line or "").lstrip()
    lowered = text.lower()
    return any(lowered.startswith(prefix + " ") or lowered == prefix for prefix in _LOOSE_A_RE)


def normalize_qa_line(line: str) -> str:
    """Normalize malformed Q/A prefix to canonical tabbed form.

    Preserves body text verbatim except leading/trailing outer whitespace.
    """
    match = QA_PREFIX_RE.match(line or "")
    if not match:
        return line
    side, body = match.group(1).upper(), (match.group(2) or "").strip()
    return f"\t{side}.\t{body}"


def enforce_qa_tabs(line: str) -> str:
    """Enforce canonical tabs for already-prefixed Q/A lines."""
    return normalize_qa_line(line)
