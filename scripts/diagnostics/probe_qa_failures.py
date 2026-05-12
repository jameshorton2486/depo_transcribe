"""Compatibility wrapper for residual Q/A failure probing.

Historical runbooks reference ``scripts/probe_qa_failures.py``. The active
implementation lives in ``scripts/probe_residual_qa_failures.py``.
"""

from __future__ import annotations

from pathlib import Path
import argparse

from scripts.probe_residual_qa_failures import probe


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Run residual consecutive-question failure probe"
    )
    parser.add_argument("raw_json", type=Path, help="Path to *_raw.json or *_split_raw.json")
    args = parser.parse_args()
    return probe(args.raw_json.resolve())


if __name__ == "__main__":
    raise SystemExit(_main())
