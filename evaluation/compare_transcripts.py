"""
Lightweight CLI for transcript-vs-reference evaluation.

Usage:
    python evaluation/compare_transcripts.py your_output.txt court_reporter.txt
"""

from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.diff_engine import tokenize_words
from evaluation.metrics import calculate_wer as calculate_wer_metrics


def compare_texts(a: str, b: str) -> list[dict[str, list[str]]]:
    a_words = a.split()
    b_words = b.split()
    matcher = SequenceMatcher(None, a_words, b_words, autojunk=False)

    changes: list[dict[str, list[str]]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append(
            {
                "type": tag,
                "a": a_words[i1:i2],
                "b": b_words[j1:j2],
            }
        )
    return changes


def calculate_wer(a: str, b: str) -> tuple[float, int, int, int]:
    metrics = calculate_wer_metrics(b, a)
    return (
        metrics["wer"],
        metrics["substitutions"],
        metrics["insertions"],
        metrics["deletions"],
    )


def categorize(change: dict[str, list[str]]) -> str:
    tokens = [token.lower() for token in change["a"] + change["b"]]
    text = " ".join(tokens)

    if any(name in text for name in ("stone", "benavides", "jones")):
        return "proper_noun"
    if any(token in {"q", "a", "mr", "ms", "mrs", "speaker", "reporter", "witness"} for token in tokens):
        return "speaker"
    if "?" in text:
        return "question_structure"
    return "general"


def build_category_summary(changes: list[dict[str, list[str]]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for change in changes:
        category = categorize(change)
        summary[category] = summary.get(category, 0) + 1
    return summary


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python evaluation/compare_transcripts.py your_output.txt court_reporter.txt")
        return 1

    output_path = Path(argv[1])
    reference_path = Path(argv[2])

    if not output_path.is_file():
        print(f"File not found: {output_path}")
        return 1
    if not reference_path.is_file():
        print(f"File not found: {reference_path}")
        return 1

    your_text = output_path.read_text(encoding="utf-8")
    correct_text = reference_path.read_text(encoding="utf-8")

    changes = compare_texts(your_text, correct_text)
    wer, substitutions, insertions, deletions = calculate_wer(correct_text, your_text)
    category_summary = build_category_summary(changes)

    print(f"WER: {wer:.4f}")
    print(f"Substitutions: {substitutions}")
    print(f"Insertions: {insertions}")
    print(f"Deletions: {deletions}")
    print(f"Total changes: {len(changes)}")
    if category_summary:
        print("Category breakdown:")
        for category, count in sorted(category_summary.items()):
            print(f"  {category}: {count}")

    print()
    print(
        json.dumps(
            {
                "wer": wer,
                "substitutions": substitutions,
                "insertions": insertions,
                "deletions": deletions,
                "total_changes": len(changes),
                "categories": category_summary,
                "changes": changes,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
