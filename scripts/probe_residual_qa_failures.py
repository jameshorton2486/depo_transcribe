"""Probe residual consecutive-Q failures after the corrections pipeline runs.

Walks the same pipeline as core/corrections_runner.py up through
enforce_qa_sequence, then implements a non-aborting version of the
consecutive-Q check that counts ALL failures and categorizes them
by pattern.

Usage:
    python -m scripts.probe_residual_qa_failures <path-to-_split_raw.json>
    python -m scripts.probe_residual_qa_failures <path-to-_raw.json>

Read-only. No commits. Output goes to stdout; redirect with Tee-Object
if you want it on disk.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.corrections_runner import (  # noqa: E402
    _adapt_saved_utterances,
    _select_utterance_source,
)
from spec_engine.block_builder import build_blocks  # noqa: E402
from spec_engine.classifier import classify_blocks  # noqa: E402
from spec_engine.qa_fixer import enforce_qa_sequence  # noqa: E402
from spec_engine.utterance_splitter import is_merged_utterance  # noqa: E402

_TEXT_TRUNCATE = 200
_CONTEXT_BEFORE = 3
_CONTEXT_AFTER = 3
_MAX_SAMPLES = 5


def _truncate(text: str) -> str:
    text = text or ""
    if len(text) <= _TEXT_TRUNCATE:
        return text
    return text[:_TEXT_TRUNCATE] + "…"


def _was_ai_split(utterance_dict_for_block: dict | None) -> bool:
    """Block-builder strips most utterance metadata. The probe approximates
    "AI-split origin" by checking if the original utterance for this
    block had _split_source set. Since we can't easily back-trace,
    we rely on a different heuristic in the probe — see categorize()."""
    if not utterance_dict_for_block:
        return False
    return utterance_dict_for_block.get("_split_source") == "ai"


def categorize(block_a, block_b, source_utterances) -> dict:
    """Categorize a consecutive-Q failure pair.

    Returns a dict with boolean flags — a single failure may match
    multiple categories.
    """
    same_speaker = (
        getattr(block_a, "speaker", None) == getattr(block_b, "speaker", None)
    )
    text_a = (getattr(block_a, "text", "") or "").strip()
    text_b = (getattr(block_b, "text", "") or "").strip()

    # Detector signals — would the splitter have flagged either text?
    a_flagged = is_merged_utterance(text_a)
    b_flagged = is_merged_utterance(text_b)

    return {
        "same_speaker": same_speaker,
        "different_speaker": not same_speaker,
        "a_was_merged_candidate": a_flagged,
        "b_was_merged_candidate": b_flagged,
        "either_was_merged_candidate": a_flagged or b_flagged,
    }


def find_consecutive_q_failures(blocks) -> list[tuple[int, int]]:
    """Walk blocks linearly. For each Q with no answer before the next Q,
    record the index pair (i_first_q, i_second_q).

    Mirrors enforce_structure's logic but does not raise — it collects.
    """
    failures: list[tuple[int, int]] = []
    pending_q_idx: int | None = None
    for i, block in enumerate(blocks):
        block_type = getattr(block, "type", None)
        if block_type == "question":
            if pending_q_idx is not None:
                failures.append((pending_q_idx, i))
            pending_q_idx = i
        elif block_type == "answer":
            pending_q_idx = None
        else:
            # colloquy / oath / directive resets the pending state, same
            # as enforce_structure.
            pending_q_idx = None
    return failures


def probe(raw_json_path: Path) -> int:
    if not raw_json_path.exists():
        print(f"ERROR: file not found: {raw_json_path}", file=sys.stderr)
        return 2

    raw_data = json.loads(raw_json_path.read_text(encoding="utf-8"))

    try:
        utterances, source = _select_utterance_source(raw_data)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not utterances:
        print("ERROR: no utterances to probe", file=sys.stderr)
        return 2

    adapted = _adapt_saved_utterances(utterances)
    alt = {"utterances": adapted}
    blocks_pre_classify = build_blocks(alt)
    blocks_classified = classify_blocks(blocks_pre_classify)
    blocks = enforce_qa_sequence(blocks_classified)

    type_breakdown = Counter(getattr(b, "type", "unknown") for b in blocks)

    failures = find_consecutive_q_failures(blocks)

    categories = Counter()
    for i_a, i_b in failures:
        cat = categorize(blocks[i_a], blocks[i_b], utterances)
        for k, v in cat.items():
            if v:
                categories[k] += 1

    print("══════════════════════════════════════════════════════════")
    print(f" Residual Q/A probe: {raw_json_path.name}")
    print("══════════════════════════════════════════════════════════")
    print(f" Source consumed:          {source}")
    print(f" Total blocks:             {len(blocks)}")
    print(f" Type breakdown:")
    for type_name in sorted(type_breakdown.keys()):
        print(f"   {type_name:<14} {type_breakdown[type_name]:>5}")
    print(f" Consecutive-question failures: {len(failures)}")
    if not failures:
        print("\n  No residual failures — pipeline would complete.")
        return 0

    print(f"\n  Categorization (overlapping; one failure can match >1):")
    for cat_name in (
        "same_speaker",
        "different_speaker",
        "a_was_merged_candidate",
        "b_was_merged_candidate",
        "either_was_merged_candidate",
    ):
        print(f"   {cat_name:<32} {categories.get(cat_name, 0):>5}")

    print(f"\n  First {min(_MAX_SAMPLES, len(failures))} of {len(failures)} failures with context:")
    for n, (i_a, i_b) in enumerate(failures[:_MAX_SAMPLES], start=1):
        print(f"\n  ── Failure {n} ── (blocks {i_a} → {i_b})")
        ctx_start = max(0, i_a - _CONTEXT_BEFORE)
        ctx_end = min(len(blocks), i_b + _CONTEXT_AFTER + 1)
        for j in range(ctx_start, ctx_end):
            blk = blocks[j]
            marker = ">>>" if j in (i_a, i_b) else "   "
            speaker = getattr(blk, "speaker", "?")
            btype = getattr(blk, "type", "?")
            text = _truncate(getattr(blk, "text", ""))
            print(f"  {marker} [{j:>4}] {speaker:<32} ({btype:<10}) | {text}")

    return 0


def _main() -> int:
    # Windows console default codec (cp1252) can't encode the box-drawing
    # characters used in the report headers; force UTF-8 on both streams
    # before any print runs.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if len(sys.argv) != 2:
        print(
            "Usage: python -m scripts.probe_residual_qa_failures <path-to-_split_raw.json|_raw.json>",
            file=sys.stderr,
        )
        return 2
    return probe(Path(sys.argv[1]).resolve())


if __name__ == "__main__":
    raise SystemExit(_main())
