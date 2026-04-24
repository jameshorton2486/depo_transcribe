"""
CLI entry point for transcript evaluation.

Usage:
    python evaluation/run_evaluation.py your_output.txt court_reporter.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.report import generate_report


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python evaluation/run_evaluation.py your_output.txt court_reporter.txt")
        return 1

    original_path = Path(argv[1])
    reference_path = Path(argv[2])

    if not original_path.is_file():
        print(f"File not found: {original_path}")
        return 1
    if not reference_path.is_file():
        print(f"File not found: {reference_path}")
        return 1

    original = original_path.read_text(encoding="utf-8")
    reference = reference_path.read_text(encoding="utf-8")
    report = generate_report(original, reference)

    print(f"WER: {report['wer']:.4f}")
    print(f"Total changes: {report['total_changes']}")
    print(f"Substitutions: {report['substitutions']}")
    print(f"Insertions: {report['insertions']}")
    print(f"Deletions: {report['deletions']}")
    print("Category breakdown:")
    for category, count in report["by_category"].items():
        print(f"  {category}: {count}")
    print()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
