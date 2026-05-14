"""Compare two merge-experiment runs side-by-side.

Each run is expected to be a folder produced by
``tools.investigation.run_merge_experiments`` containing
``metrics.json``, ``utterances.json``, and (optionally)
``transcript.txt``.

Generates a single markdown report under
``docs/investigations/merge_threshold_testing/reports/`` (or a
user-supplied output path).

Investigation-only; no production import.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_metrics(run_dir: Path) -> dict[str, Any]:
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"Missing metrics.json under: {run_dir}")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def _delta(a: Any, b: Any) -> str:
    """Return a 'b - a (+/-)' string for numeric values; '-' otherwise."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        diff = b - a
        sign = "+" if diff > 0 else ("" if diff == 0 else "")
        return f"{sign}{diff:.2f}".rstrip("0").rstrip(".") if isinstance(diff, float) else f"{sign}{diff}"
    return "-"


def _row(label: str, a: Any, b: Any) -> str:
    return f"| {label} | {a} | {b} | {_delta(a, b)} |"


def compare(run_a_dir: Path, run_b_dir: Path, out_path: Path) -> Path:
    a = _load_metrics(run_a_dir)
    b = _load_metrics(run_b_dir)

    a_cfg = a.get("config", {})
    b_cfg = b.get("config", {})
    a_struct = a.get("structure", {})
    b_struct = b.get("structure", {})
    a_cls = a.get("classifier", {})
    b_cls = b.get("classifier", {})

    a_dur = a_struct.get("duration_seconds", {}) or {}
    b_dur = b_struct.get("duration_seconds", {}) or {}
    a_words = a_struct.get("words_per_utterance", {}) or {}
    b_words = b_struct.get("words_per_utterance", {}) or {}

    lines: list[str] = []
    lines.append(
        f"# Merge-Run Comparison — `{a_cfg.get('name', run_a_dir.name)}` vs "
        f"`{b_cfg.get('name', run_b_dir.name)}`"
    )
    lines.append("")
    lines.append(f"- Run A: `{run_a_dir}`")
    lines.append(f"- Run B: `{run_b_dir}`")
    lines.append("")
    lines.append("## Configuration")
    lines.append("")
    lines.append("| Field | A | B |")
    lines.append("|---|---|---|")
    lines.append(f"| name | {a_cfg.get('name', '?')} | {b_cfg.get('name', '?')} |")
    lines.append(
        f"| in_chunk_gap (s) | {a_cfg.get('in_chunk_gap', '?')} | "
        f"{b_cfg.get('in_chunk_gap', '?')} |"
    )
    lines.append(
        f"| cross_chunk_gap (s) | {a_cfg.get('cross_chunk_gap', '?')} | "
        f"{b_cfg.get('cross_chunk_gap', '?')} |"
    )
    lines.append("")

    lines.append("## Structure")
    lines.append("")
    lines.append("| Metric | A | B | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        _row(
            "utterance_count",
            a_struct.get("utterance_count", 0),
            b_struct.get("utterance_count", 0),
        )
    )
    lines.append(
        _row(
            "long_utterance_count (>30s)",
            a_struct.get("long_utterance_count", 0),
            b_struct.get("long_utterance_count", 0),
        )
    )
    lines.append(
        _row(
            "over_100_words_count",
            a_struct.get("over_100_words_count", 0),
            b_struct.get("over_100_words_count", 0),
        )
    )
    lines.append(
        _row(
            "merged_qa_candidates",
            a_struct.get("merged_qa_candidates", 0),
            b_struct.get("merged_qa_candidates", 0),
        )
    )
    lines.append(
        _row(
            "speaker_transition_inside_utterance",
            a_struct.get("speaker_transition_inside_utterance", 0),
            b_struct.get("speaker_transition_inside_utterance", 0),
        )
    )
    lines.append(
        _row(
            "standalone_short_answers",
            a_struct.get("standalone_short_answers", 0),
            b_struct.get("standalone_short_answers", 0),
        )
    )
    lines.append(_row("avg duration (s)", a_dur.get("avg", 0), b_dur.get("avg", 0)))
    lines.append(_row("max duration (s)", a_dur.get("max", 0), b_dur.get("max", 0)))
    lines.append(
        _row("avg words/utt", a_words.get("avg", 0), b_words.get("avg", 0))
    )
    lines.append(
        _row("max words/utt", a_words.get("max", 0), b_words.get("max", 0))
    )
    lines.append("")

    lines.append("## Classifier (spec_engine)")
    lines.append("")
    lines.append("| Type | A | B | Δ |")
    lines.append("|---|---:|---:|---:|")
    type_keys = sorted(
        {*a_cls.keys(), *b_cls.keys()} - {"total_blocks"}
    )
    for t in type_keys:
        lines.append(_row(t, a_cls.get(t, 0), b_cls.get(t, 0)))
    lines.append(
        _row("total_blocks", a_cls.get("total_blocks", 0), b_cls.get("total_blocks", 0))
    )
    lines.append("")

    lines.append("## Read-out")
    lines.append("")
    a_utts = a_struct.get("utterance_count", 0)
    b_utts = b_struct.get("utterance_count", 0)
    a_qa = a_struct.get("merged_qa_candidates", 0)
    b_qa = b_struct.get("merged_qa_candidates", 0)
    a_short = a_struct.get("standalone_short_answers", 0)
    b_short = b_struct.get("standalone_short_answers", 0)
    lines.append(
        f"Going from `{a_cfg.get('name', 'A')}` (in/cross = "
        f"{a_cfg.get('in_chunk_gap', '?')}/{a_cfg.get('cross_chunk_gap', '?')}) to "
        f"`{b_cfg.get('name', 'B')}` (in/cross = "
        f"{b_cfg.get('in_chunk_gap', '?')}/{b_cfg.get('cross_chunk_gap', '?')}):"
    )
    lines.append("")
    if a_utts:
        change = (b_utts - a_utts) / a_utts * 100
        lines.append(
            f"- Utterance count: {a_utts} → {b_utts} ({change:+.1f}%)."
        )
    if a_qa is not None and b_qa is not None:
        lines.append(
            f"- Suspicious merged-Q/A: {a_qa} → {b_qa} "
            f"({b_qa - a_qa:+d})."
        )
    if a_short is not None and b_short is not None:
        lines.append(
            f"- Standalone witness short answers preserved: "
            f"{a_short} → {b_short} ({b_short - a_short:+d})."
        )
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two merge-experiment run folders."
    )
    parser.add_argument("run_a", help="First run folder (e.g. .../runs/TEST_A_CURRENT).")
    parser.add_argument("run_b", help="Second run folder.")
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output markdown path (default: "
            "docs/investigations/merge_threshold_testing/reports/"
            "compare_<A>_vs_<B>.md)."
        ),
    )
    args = parser.parse_args()

    run_a_dir = Path(args.run_a).resolve()
    run_b_dir = Path(args.run_b).resolve()

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = (
            Path("docs/investigations/merge_threshold_testing/reports")
            / f"compare_{run_a_dir.name}_vs_{run_b_dir.name}.md"
        )

    try:
        written = compare(run_a_dir, run_b_dir, out_path)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Wrote: {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
