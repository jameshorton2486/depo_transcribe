"""
Word-level transcript diff utilities for evaluation against ground truth.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")


@dataclass(frozen=True)
class DiffOp:
    kind: str
    original: str
    reference: str


@dataclass(frozen=True)
class TranscriptDiff:
    substitutions: list[DiffOp]
    insertions: list[DiffOp]
    deletions: list[DiffOp]


def tokenize_words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def compare_transcripts(original: str, reference: str) -> TranscriptDiff:
    original_words = tokenize_words(original)
    reference_words = tokenize_words(reference)
    matcher = difflib.SequenceMatcher(None, original_words, reference_words, autojunk=False)

    substitutions: list[DiffOp] = []
    insertions: list[DiffOp] = []
    deletions: list[DiffOp] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            overlap = min(i2 - i1, j2 - j1)
            for offset in range(overlap):
                substitutions.append(
                    DiffOp(
                        kind="substitution",
                        original=original_words[i1 + offset],
                        reference=reference_words[j1 + offset],
                    )
                )
            for token in original_words[i1 + overlap:i2]:
                deletions.append(DiffOp(kind="deletion", original=token, reference=""))
            for token in reference_words[j1 + overlap:j2]:
                insertions.append(DiffOp(kind="insertion", original="", reference=token))
            continue
        if tag == "delete":
            for token in original_words[i1:i2]:
                deletions.append(DiffOp(kind="deletion", original=token, reference=""))
            continue
        if tag == "insert":
            for token in reference_words[j1:j2]:
                insertions.append(DiffOp(kind="insertion", original="", reference=token))

    return TranscriptDiff(
        substitutions=substitutions,
        insertions=insertions,
        deletions=deletions,
    )
