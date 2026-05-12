"""Create a minimized raw JSON containing only QA-failure context windows.

Utility script to help reproduce Q/A structure issues with smaller fixtures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.corrections_runner import _adapt_saved_utterances, _select_utterance_source
from spec_engine.block_builder import build_blocks
from spec_engine.classifier import classify_blocks
from spec_engine.qa_fixer import enforce_qa_sequence


def _find_consecutive_q_indices(blocks: list) -> list[int]:
    keep: set[int] = set()
    pending_q: int | None = None
    for i, block in enumerate(blocks):
        t = getattr(block, "type", None)
        if t == "question":
            if pending_q is not None:
                keep.update(range(max(0, pending_q - 2), min(len(blocks), i + 3)))
            pending_q = i
        elif t == "answer":
            pending_q = None
        else:
            pending_q = None
    return sorted(keep)


def _main() -> int:
    ap = argparse.ArgumentParser(description="Minimize raw JSON for QA bug repro")
    ap.add_argument("raw_json", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    raw_path = args.raw_json.resolve()
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    utterances, _source = _select_utterance_source(payload)
    adapted = _adapt_saved_utterances(utterances)
    blocks = enforce_qa_sequence(classify_blocks(build_blocks({"utterances": adapted})))
    keep_idx = _find_consecutive_q_indices(blocks)

    if not keep_idx:
        print("No consecutive-question failures detected; nothing to minimize.")
        return 0

    minimized = {
        "utterances": [adapted[i] for i in keep_idx if i < len(adapted)],
        "meta": {"source": str(raw_path), "kept_indices": keep_idx},
    }
    out_path = args.out or raw_path.with_name(raw_path.stem + "_minimized_raw.json")
    out_path.write_text(json.dumps(minimized, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote minimized fixture: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
