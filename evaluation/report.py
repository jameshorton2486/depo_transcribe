"""
Structured transcript evaluation report generation.
"""

from __future__ import annotations

import difflib
import re

from evaluation.diff_engine import compare_transcripts
from evaluation.metrics import calculate_wer


PUNCT_RE = re.compile(r"\.\.\.|--|[.,!?;:()\[\]\"']")
SPEAKER_RE = re.compile(r"^\s*(Q\.|A\.|(?:MR|MS|MRS)\.\s+[A-Z][A-Z .'\-]*:|THE REPORTER:|THE WITNESS:)")
PROPER_NOUN_RE = re.compile(r"^[A-Z][a-z]+(?:[-'][A-Za-z]+)*$|^[A-Z]{2,}$")
SPEAKER_TOKENS = {"Q", "A", "MR", "MS", "MRS", "THE", "REPORTER", "WITNESS"}


def _token_is_proper_noun(token: str) -> bool:
    return bool(PROPER_NOUN_RE.match(token or ""))


def _punctuation_error_count(original: str, reference: str) -> int:
    original_tokens = PUNCT_RE.findall(original or "")
    reference_tokens = PUNCT_RE.findall(reference or "")
    matcher = difflib.SequenceMatcher(None, original_tokens, reference_tokens, autojunk=False)
    count = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            count += max(i2 - i1, j2 - j1)
    return count


def _extract_line_prefix(line: str) -> str:
    match = SPEAKER_RE.match(line or "")
    return match.group(1) if match else ""


def _formatting_and_speaker_counts(original: str, reference: str) -> tuple[int, int]:
    original_lines = (original or "").splitlines()
    reference_lines = (reference or "").splitlines()
    matcher = difflib.SequenceMatcher(None, original_lines, reference_lines, autojunk=False)
    formatting = 0
    speaker = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        old_chunk = original_lines[i1:i2]
        new_chunk = reference_lines[j1:j2]
        overlap = min(len(old_chunk), len(new_chunk))

        for offset in range(overlap):
            old_line = old_chunk[offset]
            new_line = new_chunk[offset]
            old_prefix = _extract_line_prefix(old_line)
            new_prefix = _extract_line_prefix(new_line)
            if old_prefix != new_prefix and old_prefix and new_prefix:
                if old_prefix in {"Q.", "A."} or new_prefix in {"Q.", "A."}:
                    formatting += 1
                else:
                    speaker += 1
                continue

            if " ".join(old_line.split()) == " ".join(new_line.split()) and old_line != new_line:
                formatting += 1

        formatting += max(len(old_chunk), len(new_chunk)) - overlap

    return formatting, speaker


def classify_errors(original: str, reference: str) -> dict[str, int]:
    diff = compare_transcripts(original, reference)
    proper_noun = 0
    phonetic = 0

    for op in diff.substitutions:
        if op.original in SPEAKER_TOKENS or op.reference in SPEAKER_TOKENS:
            continue
        if _token_is_proper_noun(op.original) or _token_is_proper_noun(op.reference):
            proper_noun += 1
        else:
            phonetic += 1

    for op in diff.insertions + diff.deletions:
        token = op.original or op.reference
        if token in SPEAKER_TOKENS:
            continue
        if _token_is_proper_noun(token):
            proper_noun += 1
        else:
            phonetic += 1

    punctuation = _punctuation_error_count(original, reference)
    formatting, speaker = _formatting_and_speaker_counts(original, reference)

    return {
        "phonetic": phonetic,
        "punctuation": punctuation,
        "formatting": formatting,
        "proper_noun": proper_noun,
        "speaker": speaker,
    }


def generate_report(original: str, reference: str) -> dict:
    metrics = calculate_wer(original, reference)
    by_category = classify_errors(original, reference)
    total_changes = sum(by_category.values())

    return {
        "wer": metrics["wer"],
        "total_changes": total_changes,
        "substitutions": metrics["substitutions"],
        "insertions": metrics["insertions"],
        "deletions": metrics["deletions"],
        "total_words": metrics["total_words"],
        "by_category": by_category,
    }
