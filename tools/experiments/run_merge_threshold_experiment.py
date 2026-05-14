"""Controlled experiment: sweep cross-chunk merge thresholds.

Loads ``raw_utterances`` from an existing ``raw_deepgram.json`` (which
already represents Deepgram output after the per-chunk transcriber
merge) and re-runs only the ``pipeline.assembler.merge_utterances``
stage at several gap-threshold values. Each threshold's outputs are
written into a separate folder so they can be compared
side-by-side. Production defaults are NOT modified — the threshold is
passed as a function argument.

Outputs (per threshold, in ``docs/experiments/merge_threshold_tests/<case>/<key>/``):

    01_raw_deepgram.json
    02_after_transcriber_merge.json
    03_after_assembler_merge.json
    04_emitted_transcript.txt
    05_classifier_summary.txt
    06_metrics.json

The case-level folder also receives ``EXPERIMENT_SUMMARY.md`` with
cross-threshold comparison.

Usage::

    python -m tools.experiments.run_merge_threshold_experiment \
        --case-dir "C:\\path\\to\\case_folder" \
        [--thresholds 0.4 0.6 0.8 1.0 1.25] \
        [--out-root docs/experiments/merge_threshold_tests]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

from pipeline.assembler import (
    SHORT_GAP_THRESHOLD_SECONDS as ASSEMBLER_SHORT_GAP_DEFAULT,
    MIN_UTTERANCE_WORDS,
    _attach_speaker_labels,
    build_transcript_text,
    merge_utterances as assembler_merge,
)
from spec_engine.block_builder import build_blocks
from spec_engine.classifier import classify_blocks


DEFAULT_THRESHOLDS = [0.4, 0.6, 0.8, 1.0, 1.25]
SAMPLE_BAD = 5
SAMPLE_GOOD = 5
TEXT_TRUNCATE = 220

_SHORT_ANSWER_PATTERN = re.compile(
    r"\b(yes|no|correct|right|wrong|i\s+do|i\s+did)\b\.?",
    re.IGNORECASE,
)
_STANDALONE_ANSWER_PATTERN = re.compile(
    r"^\s*(yes|no|correct)\.?\s*$",
    re.IGNORECASE,
)
_QUESTION_MARK_RE = re.compile(r"\?")


def _threshold_key(t: float) -> str:
    """Render 0.4 → '0_4', 1.25 → '1_25'."""
    return str(t).replace(".", "_")


def _adapt_utterances_for_blocks(utterances: list[dict]) -> list[dict]:
    """Bridge saved utterance shape onto block_builder's expected shape."""
    out: list[dict] = []
    for u in utterances or []:
        if not isinstance(u, dict):
            continue
        text = (u.get("transcript") or u.get("text") or "").strip()
        if not text:
            continue
        speaker = u.get("speaker_label")
        if not speaker:
            raw_speaker = u.get("speaker")
            speaker = (
                f"Speaker {raw_speaker}"
                if raw_speaker is not None
                else "UNKNOWN"
            )
        out.append({"speaker": str(speaker), "text": text, "type": "utterance"})
    return out


def _utterance_word_count(u: dict) -> int:
    words = u.get("words") or []
    if words:
        return len(words)
    return len((u.get("transcript") or "").split())


def _has_speaker_switch_inside(u: dict) -> bool:
    """Return True when the utterance's word list contains > 1 distinct speaker."""
    words = u.get("words") or []
    speakers = {
        w.get("speaker")
        for w in words
        if isinstance(w, dict) and w.get("speaker") is not None
    }
    return len(speakers) > 1


def _looks_like_merged_qa(u: dict) -> bool:
    """Utterance contains both a question mark and a standalone-answer phrase."""
    text = (u.get("transcript") or "").strip()
    if not text:
        return False
    if not _QUESTION_MARK_RE.search(text):
        return False
    # Look for an answer-like phrase that isn't at position 0 (i.e. is mid-utterance).
    for match in _SHORT_ANSWER_PATTERN.finditer(text):
        if match.start() == 0:
            continue
        # Require the preceding character to be sentence punctuation or whitespace
        # before a capitalized answer-start — best-effort heuristic.
        preceding = text[max(0, match.start() - 2):match.start()].strip()
        if preceding.endswith((".", "?", "!")) or match.start() < 5:
            return True
        # Or, if the answer phrase is followed by a period inside the utterance,
        # treat it as a likely interpolated answer.
        end = match.end()
        if end < len(text) and text[end:end + 2].startswith("."):
            return True
    return False


def _is_standalone_answer(u: dict) -> bool:
    text = (u.get("transcript") or "").strip()
    return bool(_STANDALONE_ANSWER_PATTERN.match(text))


def _truncate(text: str, n: int = TEXT_TRUNCATE) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= n:
        return text
    return text[:n - 1].rstrip() + "…"


def _compute_classifier_counts(utterances: list[dict]) -> dict[str, int]:
    """Run spec_engine block_builder + classifier and count types."""
    adapted = _adapt_utterances_for_blocks(utterances)
    if not adapted:
        return {"total_blocks": 0}
    alt = {"utterances": adapted}
    blocks = build_blocks(alt)
    classified = classify_blocks(blocks)
    counts: dict[str, int] = {"total_blocks": len(classified)}
    for b in classified:
        counts[b.type] = counts.get(b.type, 0) + 1
    return counts


def _compute_metrics(
    utterances: list[dict],
    threshold: float,
) -> dict[str, Any]:
    counts = {
        "threshold": threshold,
        "utterance_count": len(utterances),
        "merged_qa_candidates": 0,
        "speaker_switch_inside_count": 0,
        "standalone_short_answers": 0,
        "long_attorney_turns_with_short_answer_phrases": 0,
        "utterances_over_100_words": 0,
    }

    word_counts: list[int] = []
    for u in utterances:
        wc = _utterance_word_count(u)
        word_counts.append(wc)
        if _looks_like_merged_qa(u):
            counts["merged_qa_candidates"] += 1
        if _has_speaker_switch_inside(u):
            counts["speaker_switch_inside_count"] += 1
        if _is_standalone_answer(u):
            counts["standalone_short_answers"] += 1
        if wc > 100:
            counts["utterances_over_100_words"] += 1
        if wc > 30 and _SHORT_ANSWER_PATTERN.search(u.get("transcript") or ""):
            # rough: long turns that contain short-answer phrases mid-text are
            # candidates for "attorney question merged with witness answer"
            text = (u.get("transcript") or "")
            for match in _SHORT_ANSWER_PATTERN.finditer(text):
                if match.start() > 20:
                    counts["long_attorney_turns_with_short_answer_phrases"] += 1
                    break

    counts["avg_words_per_utterance"] = (
        round(statistics.mean(word_counts), 2) if word_counts else 0.0
    )
    counts["median_words_per_utterance"] = (
        statistics.median(word_counts) if word_counts else 0
    )
    counts["max_words_per_utterance"] = max(word_counts) if word_counts else 0

    counts["classifier"] = _compute_classifier_counts(utterances)
    return counts


def _sample_bad_merges(utterances: list[dict], limit: int = SAMPLE_BAD) -> list[dict]:
    """Pick representative likely-bad merges: speaker-switch, merged Q/A, oversize."""
    samples: list[dict] = []
    seen_keys: set[tuple] = set()

    def _add(kind: str, u: dict) -> None:
        key = (kind, _truncate(u.get("transcript", ""), 80))
        if key in seen_keys:
            return
        seen_keys.add(key)
        samples.append({
            "kind": kind,
            "speaker": u.get("speaker_label") or f"speaker {u.get('speaker', '?')}",
            "word_count": _utterance_word_count(u),
            "start": u.get("start"),
            "end": u.get("end"),
            "text": _truncate(u.get("transcript", "")),
        })

    for u in utterances:
        if len(samples) >= limit:
            break
        if _has_speaker_switch_inside(u):
            _add("speaker_switch_inside_block", u)
    for u in utterances:
        if len(samples) >= limit:
            break
        if _looks_like_merged_qa(u):
            _add("merged_Q_and_A", u)
    for u in utterances:
        if len(samples) >= limit:
            break
        if _utterance_word_count(u) > 120:
            _add("oversize_utterance", u)

    return samples[:limit]


def _sample_good_segmentation(
    utterances: list[dict], limit: int = SAMPLE_GOOD
) -> list[dict]:
    """Pick clean examples: isolated questions, isolated short answers, isolated colloquy."""
    samples: list[dict] = []

    def _add(kind: str, u: dict) -> None:
        samples.append({
            "kind": kind,
            "speaker": u.get("speaker_label") or f"speaker {u.get('speaker', '?')}",
            "word_count": _utterance_word_count(u),
            "start": u.get("start"),
            "end": u.get("end"),
            "text": _truncate(u.get("transcript", "")),
        })

    # isolated short answer
    count = 0
    for u in utterances:
        if count >= 2:
            break
        if _is_standalone_answer(u):
            _add("isolated_short_answer", u)
            count += 1

    # isolated question — single ? at end, no standalone-answer phrase mid-text
    count = 0
    for u in utterances:
        if count >= 2:
            break
        text = (u.get("transcript") or "").strip()
        if not text.endswith("?"):
            continue
        if _looks_like_merged_qa(u):
            continue
        if _utterance_word_count(u) > 60:
            continue
        _add("isolated_question", u)
        count += 1

    # isolated colloquy — substantial single-speaker turn without ?/answer phrase
    count = 0
    for u in utterances:
        if count >= 1:
            break
        text = (u.get("transcript") or "").strip()
        wc = _utterance_word_count(u)
        if wc < 10 or wc > 50:
            continue
        if "?" in text or _SHORT_ANSWER_PATTERN.search(text):
            continue
        _add("isolated_colloquy", u)
        count += 1

    return samples[:limit]


@dataclasses.dataclass
class ThresholdResult:
    threshold: float
    folder: Path
    metrics: dict[str, Any]
    bad_samples: list[dict]
    good_samples: list[dict]
    transcript_text: str


def run_threshold(
    raw_utterances_post_transcriber_merge: list[dict],
    threshold: float,
    out_dir: Path,
    raw_deepgram_path: Path,
) -> ThresholdResult:
    """Run a single threshold and write all six artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 01_raw_deepgram.json — copy of the entire saved Deepgram payload.
    # Re-read on demand so we don't carry a 16MB blob in memory longer than needed.
    raw_text = raw_deepgram_path.read_text(encoding="utf-8")
    (out_dir / "01_raw_deepgram.json").write_text(raw_text, encoding="utf-8")

    # 02_after_transcriber_merge.json — the pre-assembler-merge utterances we feed in.
    (out_dir / "02_after_transcriber_merge.json").write_text(
        json.dumps(
            {"utterances": raw_utterances_post_transcriber_merge},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Run the assembler merge with the experimental threshold.
    # short_gap_threshold is clamped so it never exceeds the main gap (keeps
    # the "short utterances merge with at least as tight a gap" invariant).
    short_gap = min(ASSEMBLER_SHORT_GAP_DEFAULT, threshold)
    merged = assembler_merge(
        raw_utterances_post_transcriber_merge,
        gap_threshold_seconds=threshold,
        short_gap_threshold_seconds=short_gap,
        min_word_count=MIN_UTTERANCE_WORDS,
    )
    labeled = _attach_speaker_labels(merged)

    # 03_after_assembler_merge.json — the experimental merged list.
    (out_dir / "03_after_assembler_merge.json").write_text(
        json.dumps({"utterances": labeled}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 04_emitted_transcript.txt — production's build_transcript_text on the merged list.
    transcript_text = build_transcript_text(labeled)
    (out_dir / "04_emitted_transcript.txt").write_text(
        transcript_text, encoding="utf-8"
    )

    # 05_classifier_summary.txt — spec_engine block-type counts on this merge.
    classifier_counts = _compute_classifier_counts(labeled)
    summary_lines = ["Classifier type counts:"]
    for k, v in sorted(classifier_counts.items()):
        summary_lines.append(f"  {k}: {v}")
    (out_dir / "05_classifier_summary.txt").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )

    # 06_metrics.json — all counts + samples for this threshold.
    metrics = _compute_metrics(labeled, threshold)
    bad_samples = _sample_bad_merges(labeled)
    good_samples = _sample_good_segmentation(labeled)
    metrics["bad_sample_count"] = len(bad_samples)
    metrics["good_sample_count"] = len(good_samples)
    (out_dir / "06_metrics.json").write_text(
        json.dumps(
            {
                "metrics": metrics,
                "bad_samples": bad_samples,
                "good_samples": good_samples,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return ThresholdResult(
        threshold=threshold,
        folder=out_dir,
        metrics=metrics,
        bad_samples=bad_samples,
        good_samples=good_samples,
        transcript_text=transcript_text,
    )


def _format_sample_block(samples: Iterable[dict]) -> str:
    lines: list[str] = []
    for s in samples:
        start = s.get("start")
        end = s.get("end")
        ts = ""
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            ts = f"  t={start:.2f}-{end:.2f}s"
        lines.append(
            f"- **{s['kind']}** (`{s['speaker']}`, {s['word_count']} words{ts})"
        )
        lines.append(f"  > {s['text']}")
    return "\n".join(lines) if lines else "_(none found)_"


def write_summary(
    case_root: Path,
    case_name: str,
    raw_utterance_count: int,
    results: list[ThresholdResult],
    notes: dict[str, Any],
) -> Path:
    summary_path = case_root / "EXPERIMENT_SUMMARY.md"
    lines: list[str] = []
    lines.append(f"# Merge-Threshold Experiment — {case_name}")
    lines.append("")
    lines.append(
        "Cross-chunk merge threshold sweep on cached Deepgram output. "
        "**No production defaults were modified.** The assembler merge "
        "is re-run with each candidate `gap_threshold_seconds` value; "
        "everything upstream (Deepgram, per-chunk transcriber merge) is "
        "identical across runs."
    )
    lines.append("")
    lines.append("## Section 1 — Overview")
    lines.append("")
    lines.append(
        f"- Thresholds tested: {', '.join(str(r.threshold) for r in results)}"
    )
    lines.append(
        f"- Input utterance count (post per-chunk transcriber merge): "
        f"**{raw_utterance_count}**"
    )
    lines.append(f"- Production default `gap_threshold_seconds`: **1.25**")
    lines.append(
        f"- Production default `short_gap_threshold_seconds`: "
        f"**{ASSEMBLER_SHORT_GAP_DEFAULT}**"
    )
    lines.append(f"- `min_word_count`: **{MIN_UTTERANCE_WORDS}**")
    lines.append("")
    lines.append("Major observations: see Sections 2-5 below.")
    lines.append("")
    lines.append("## Section 2 — Threshold comparison table")
    lines.append("")
    lines.append(
        "| Threshold | Utterances | Avg words | Median | Max | Merged Q/A candidates | Speaker switch in block | Standalone short answers | Long turns w/ short-answer phrase mid-text | >100-word utts | Classifier Q | Classifier A | Classifier colloquy |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        m = r.metrics
        c = m.get("classifier", {})
        lines.append(
            f"| {r.threshold} | {m['utterance_count']} | {m['avg_words_per_utterance']} | "
            f"{m['median_words_per_utterance']} | {m['max_words_per_utterance']} | "
            f"{m['merged_qa_candidates']} | {m['speaker_switch_inside_count']} | "
            f"{m['standalone_short_answers']} | "
            f"{m['long_attorney_turns_with_short_answer_phrases']} | "
            f"{m['utterances_over_100_words']} | "
            f"{c.get('question', 0)} | {c.get('answer', 0)} | {c.get('colloquy', 0)} |"
        )
    lines.append("")

    lines.append("## Section 3 — Sample bad merges per threshold")
    lines.append("")
    for r in results:
        lines.append(f"### Threshold {r.threshold} — `{r.folder.name}/`")
        lines.append("")
        lines.append(_format_sample_block(r.bad_samples))
        lines.append("")

    lines.append("## Section 4 — Sample good segmentation per threshold")
    lines.append("")
    for r in results:
        lines.append(f"### Threshold {r.threshold} — `{r.folder.name}/`")
        lines.append("")
        lines.append(_format_sample_block(r.good_samples))
        lines.append("")

    lines.append("## Section 5 — Observations")
    lines.append("")
    # Find inflection points
    sorted_results = sorted(results, key=lambda r: r.threshold)
    fragmentation_obs = []
    over_merge_obs = []
    for r in sorted_results:
        m = r.metrics
        if m["merged_qa_candidates"] >= 5:
            over_merge_obs.append(
                f"At threshold **{r.threshold}**, "
                f"`merged_qa_candidates={m['merged_qa_candidates']}` and "
                f"`standalone_short_answers={m['standalone_short_answers']}` "
                f"(higher merged-Q/A → fewer isolated short answers preserved)."
            )
        if m["utterance_count"] > raw_utterance_count * 0.8:
            fragmentation_obs.append(
                f"At threshold **{r.threshold}**, "
                f"`utterance_count={m['utterance_count']}` "
                f"approaches the unmerged input "
                f"({raw_utterance_count}), suggesting very little merge "
                f"actually fires."
            )

    if fragmentation_obs:
        lines.append("**Where fragmentation begins:**")
        lines.append("")
        for o in fragmentation_obs:
            lines.append(f"- {o}")
        lines.append("")
    if over_merge_obs:
        lines.append("**Where over-merging shows up:**")
        lines.append("")
        for o in over_merge_obs:
            lines.append(f"- {o}")
        lines.append("")

    # Compute a heuristic "healthiest" score: minimize merged_qa_candidates
    # AND speaker_switch_inside_count while keeping standalone_short_answers
    # high (witness "Yes."/"No." preserved). This is a directional indicator
    # only — final judgment requires human review of the transcripts.
    def _score(r: ThresholdResult) -> tuple[int, int, int]:
        m = r.metrics
        return (
            m["merged_qa_candidates"]
            + m["speaker_switch_inside_count"]
            - m["standalone_short_answers"],
            m["merged_qa_candidates"],
            -m["standalone_short_answers"],
        )

    if results:
        best = min(sorted_results, key=_score)
        lines.append(
            f"**Lowest combined bad-merge score:** threshold "
            f"**{best.threshold}** — "
            f"`merged_qa_candidates={best.metrics['merged_qa_candidates']}`, "
            f"`speaker_switch_inside={best.metrics['speaker_switch_inside_count']}`, "
            f"`standalone_short_answers={best.metrics['standalone_short_answers']}`."
        )
        lines.append("")
        lines.append(
            "_This is a directional indicator. No production change is being "
            "recommended; human review of the per-threshold transcripts is "
            "required to confirm the trade-offs._"
        )
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    for k, v in notes.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    lines.append("## Reproducing")
    lines.append("")
    lines.append("```powershell")
    lines.append(
        ".\\.venv\\Scripts\\python.exe -m tools.experiments.run_merge_threshold_experiment "
        f"--case-dir \"<case_dir>\""
    )
    lines.append("```")
    lines.append("")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def run(
    case_dir: Path,
    thresholds: list[float],
    out_root: Path,
) -> Path:
    case_dir = case_dir.resolve()
    raw_json = case_dir / "Deepgram" / "raw_deepgram.json"
    if not raw_json.exists():
        raise FileNotFoundError(f"Missing raw_deepgram.json under: {raw_json}")

    data = json.loads(raw_json.read_text(encoding="utf-8"))
    raw_utterances = data.get("raw_utterances") or []
    if not raw_utterances:
        raise RuntimeError(
            "raw_deepgram.json has no raw_utterances; cannot run threshold sweep."
        )

    case_name = case_dir.name
    case_root = out_root / case_name
    case_root.mkdir(parents=True, exist_ok=True)

    results: list[ThresholdResult] = []
    for t in thresholds:
        sub = case_root / _threshold_key(t)
        result = run_threshold(
            raw_utterances_post_transcriber_merge=raw_utterances,
            threshold=t,
            out_dir=sub,
            raw_deepgram_path=raw_json,
        )
        results.append(result)
        print(
            f"  threshold={t} -> {sub.name}/ "
            f"utterances={result.metrics['utterance_count']} "
            f"merged_qa={result.metrics['merged_qa_candidates']} "
            f"speaker_switch={result.metrics['speaker_switch_inside_count']}"
        )

    summary_path = write_summary(
        case_root=case_root,
        case_name=case_name,
        raw_utterance_count=len(raw_utterances),
        results=results,
        notes={
            "production_default_gap_threshold_seconds": 1.25,
            "production_default_short_gap_threshold_seconds": ASSEMBLER_SHORT_GAP_DEFAULT,
            "production_default_min_word_count": MIN_UTTERANCE_WORDS,
            "input_source": str(raw_json),
            "production_code_modified": "no",
        },
    )

    print(f"Summary: {summary_path}")
    return summary_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep cross-chunk merge thresholds against cached Deepgram "
            "output. Production defaults are not modified."
        )
    )
    parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to a case folder containing Deepgram/raw_deepgram.json.",
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=DEFAULT_THRESHOLDS,
        help=f"Threshold values to test (default: {DEFAULT_THRESHOLDS}).",
    )
    parser.add_argument(
        "--out-root",
        default="docs/experiments/merge_threshold_tests",
        help=(
            "Root directory for experiment outputs "
            "(default: docs/experiments/merge_threshold_tests)."
        ),
    )
    args = parser.parse_args()

    try:
        run(
            case_dir=Path(args.case_dir),
            thresholds=args.thresholds,
            out_root=Path(args.out_root),
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
