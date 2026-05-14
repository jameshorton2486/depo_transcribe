"""Offline audit pass: apply the speaker-turn repair to a case's raw
transcript and write before/after artifacts for human inspection.

This tool does NOT call Anthropic and does NOT touch the production
pipeline. It loads the case's ``Deepgram/raw_deepgram.txt``, runs
``clean_format.speaker_turn_repair.repair_transcript_blocks`` on it,
and produces under
``output/investigation/speaker_turn_repairs/<case_name>/``:

- ``summary.json``     — block / repair / rule counts
- ``summary.md``       — same data in human-readable form
- ``before_after.md``  — first N repaired blocks rendered as
  before/after pairs (one per rule kind, up to ``--max-samples`` each)
- ``repaired_transcript.txt`` — the full transcript after repair

The audit is purely informational; production behavior is unchanged
unless and until the formatter wiring is enabled by an actual
Start-Transcription run.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from clean_format.speaker_turn_repair import (
    SpeakerTurnRepairResult,
    TranscriptRepairSummary,
    repair_transcript_blocks,
)

SAMPLES_PER_RULE = 5
TEXT_TRUNCATE = 320


def _truncate(text: str, n: int = TEXT_TRUNCATE) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def _bucket_records(
    records: list[SpeakerTurnRepairResult],
    samples_per_rule: int,
) -> dict[str, list[SpeakerTurnRepairResult]]:
    buckets: dict[str, list[SpeakerTurnRepairResult]] = defaultdict(list)
    for r in records:
        if not r.repair_applied:
            continue
        if len(buckets[r.repair_reason]) < samples_per_rule:
            buckets[r.repair_reason].append(r)
    return buckets


def write_outputs(
    case_dir: Path,
    out_root: Path,
    samples_per_rule: int,
) -> Path:
    raw_txt_path = case_dir / "Deepgram" / "raw_deepgram.txt"
    if not raw_txt_path.exists():
        raise FileNotFoundError(f"Missing raw transcript: {raw_txt_path}")

    raw_text = raw_txt_path.read_text(encoding="utf-8")
    repaired_text, summary = repair_transcript_blocks(raw_text)

    case_out = out_root / case_dir.name
    case_out.mkdir(parents=True, exist_ok=True)

    # 1. summary.json
    (case_out / "summary.json").write_text(
        json.dumps(
            {
                "case_dir": str(case_dir),
                "source_file": str(raw_txt_path),
                "block_count": summary.block_count,
                "blocks_repaired": summary.blocks_repaired,
                "splits_emitted": summary.splits_emitted,
                "rule_counts": summary.rule_counts,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 2. summary.md
    md_lines: list[str] = []
    md_lines.append(f"# Speaker-turn repair audit — `{case_dir.name}`")
    md_lines.append("")
    md_lines.append(f"- Source: `{raw_txt_path}`")
    md_lines.append(f"- Blocks scanned: **{summary.block_count}**")
    md_lines.append(f"- Blocks repaired: **{summary.blocks_repaired}**")
    md_lines.append(f"- New paragraph splits emitted: **{summary.splits_emitted}**")
    md_lines.append("")
    md_lines.append("## Rule counts")
    md_lines.append("")
    if summary.rule_counts:
        for rule, count in sorted(summary.rule_counts.items()):
            md_lines.append(f"- `{rule}`: **{count}**")
    else:
        md_lines.append("_no repairs fired_")
    md_lines.append("")
    (case_out / "summary.md").write_text("\n".join(md_lines), encoding="utf-8")

    # 3. before_after.md
    buckets = _bucket_records(summary.records, samples_per_rule)
    ba_lines: list[str] = []
    ba_lines.append(f"# Before/after samples — `{case_dir.name}`")
    ba_lines.append("")
    ba_lines.append(
        "Each sample shows the **original** Deepgram utterance body and "
        "the resulting **repaired** segments. Speaker labels are inherited "
        "from the original utterance and not shown here for brevity."
    )
    ba_lines.append("")
    for rule, items in sorted(buckets.items()):
        ba_lines.append(f"## `{rule}` — {len(items)} samples")
        ba_lines.append("")
        for i, r in enumerate(items, start=1):
            ba_lines.append(f"### Sample {i}")
            ba_lines.append("")
            ba_lines.append("**Before (one block):**")
            ba_lines.append("")
            ba_lines.append("> " + _truncate(r.original_text))
            ba_lines.append("")
            ba_lines.append(f"**After ({len(r.repaired_segments)} blocks):**")
            ba_lines.append("")
            for seg in r.repaired_segments:
                ba_lines.append(f"- {_truncate(seg)}")
            ba_lines.append("")
            if r.metadata:
                ba_lines.append(
                    f"_metadata: {json.dumps(r.metadata, ensure_ascii=False)}_"
                )
                ba_lines.append("")
    if not buckets:
        ba_lines.append("_no repaired blocks_")
    (case_out / "before_after.md").write_text("\n".join(ba_lines), encoding="utf-8")

    # 4. repaired_transcript.txt
    (case_out / "repaired_transcript.txt").write_text(
        repaired_text, encoding="utf-8"
    )

    return case_out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the speaker-turn repair against a case's raw "
            "Deepgram transcript."
        )
    )
    parser.add_argument(
        "--case-dir",
        required=True,
        help="Case folder containing Deepgram/raw_deepgram.txt.",
    )
    parser.add_argument(
        "--out-root",
        default="output/investigation/speaker_turn_repairs",
        help=(
            "Root directory for audit outputs (default: "
            "output/investigation/speaker_turn_repairs)."
        ),
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=SAMPLES_PER_RULE,
        help=f"Maximum before/after samples per rule (default: {SAMPLES_PER_RULE}).",
    )
    args = parser.parse_args()

    try:
        out_dir = write_outputs(
            case_dir=Path(args.case_dir),
            out_root=Path(args.out_root),
            samples_per_rule=args.max_samples,
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Outputs: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
