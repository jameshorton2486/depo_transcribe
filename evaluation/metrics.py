"""
Evaluation metrics for transcript comparison.
"""

from __future__ import annotations

from evaluation.diff_engine import compare_transcripts, tokenize_words


def calculate_wer(original: str, reference: str) -> dict:
    diff = compare_transcripts(original, reference)
    total_words = len(tokenize_words(reference))
    substitutions = len(diff.substitutions)
    insertions = len(diff.insertions)
    deletions = len(diff.deletions)
    denominator = max(total_words, 1)

    return {
        "wer": (substitutions + insertions + deletions) / denominator,
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "total_words": total_words,
    }
