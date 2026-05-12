"""Probe merged-utterance candidates in a saved raw transcript JSON.

This diagnostic highlights utterances that appear to contain multiple Q/A turns
in one block using ``spec_engine.utterance_splitter.is_merged_utterance``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.corrections_runner import _adapt_saved_utterances, _select_utterance_source
from spec_engine.utterance_splitter import is_merged_utterance


def _main() -> int:
    parser = argparse.ArgumentParser(description="Count merged-utterance candidates")
    parser.add_argument("raw_json", type=Path, help="Path to *_raw.json or *_split_raw.json")
    parser.add_argument("--max", type=int, default=20, dest="max_samples")
    args = parser.parse_args()

    payload = json.loads(args.raw_json.resolve().read_text(encoding="utf-8"))
    utterances, source = _select_utterance_source(payload)
    adapted = _adapt_saved_utterances(utterances)

    flagged = [u for u in adapted if is_merged_utterance(u.get("text", ""))]
    print(f"Source: {source}")
    print(f"Utterances: {len(adapted)}")
    print(f"Merged-candidate utterances: {len(flagged)}")

    for i, utt in enumerate(flagged[: max(0, args.max_samples)], start=1):
        speaker = utt.get("speaker", "?")
        text = (utt.get("text", "") or "").strip().replace("\n", " ")
        if len(text) > 200:
            text = text[:200] + "…"
        print(f"{i:>3}. {speaker}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
