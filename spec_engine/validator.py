"""Deterministic validation checks for transcript formatting."""
from __future__ import annotations

import re
from dataclasses import dataclass

from spec_engine.regex_patterns import CANONICAL_QA_RE, QA_PREFIX_RE, SPEAKER_LABEL_RE

_INVALID_ELLIPSIS_RE = re.compile(r"\.\s+\.\s+\.")
_INVALID_DASH_RE = re.compile(r"(?<!\s)--|--(?!\s)")
_DUP_PUNCT_RE = re.compile(r"([,;:!?\.])\1+")
_MALFORMED_PAREN_RE = re.compile(r"^\s*\([^)]*$|^[^(]*\)\s*$")


@dataclass(slots=True)
class ValidationIssue:
    line_number: int
    code: str
    message: str
    line: str


def validate_transcript_lines(lines: list[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for idx, line in enumerate(lines, start=1):
        stripped = (line or "").rstrip("\n")

        if QA_PREFIX_RE.match(stripped) and not CANONICAL_QA_RE.match(stripped):
            issues.append(ValidationIssue(idx, "MALFORMED_QA", "Line looks like Q/A but is not canonical tab format", stripped))

        if stripped.strip().endswith(":") and (
            "::" in stripped or not SPEAKER_LABEL_RE.match(stripped.strip())
        ):
            issues.append(ValidationIssue(idx, "MALFORMED_SPEAKER", "Speaker label appears malformed", stripped))

        if _INVALID_ELLIPSIS_RE.search(stripped):
            issues.append(ValidationIssue(idx, "INVALID_ELLIPSIS", "Ellipsis uses spaced-dot form", stripped))

        if _INVALID_DASH_RE.search(stripped):
            issues.append(ValidationIssue(idx, "INVALID_DASH", "Interruption dash should use ' -- ' canonical form", stripped))

        if _DUP_PUNCT_RE.search(stripped):
            issues.append(ValidationIssue(idx, "DUP_PUNCT", "Duplicate punctuation sequence detected", stripped))

        if _MALFORMED_PAREN_RE.match(stripped):
            issues.append(ValidationIssue(idx, "MALFORMED_PAREN", "Unbalanced parenthetical punctuation", stripped))

    return issues
