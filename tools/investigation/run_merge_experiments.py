"""Run the 4-config merge-threshold experiment matrix on a case.

For each ``MergeConfig`` in ``merge_threshold_matrix.ALL_CONFIGS``,
this driver:

1. Loads the Deepgram-native pre-per-chunk-merge utterances from
   ``raw_deepgram.json["chunks"][i]["results"]["utterances"]`` (the
   most upstream data point still available on disk).
2. Applies ``pipeline.transcriber.smooth_speakers`` and
   ``pipeline.transcriber.merge_utterances`` per chunk with the
   experimental ``in_chunk_gap``.
3. Applies ``pipeline.assembler.merge_utterances`` across chunks
   with the experimental ``cross_chunk_gap``.
4. Saves per-run artifacts under
   ``docs/investigations/merge_threshold_testing/runs/<TEST_NAME>/``:

   - ``utterances.json`` — final merged list
   - ``transcript.txt`` — text via ``build_transcript_text``
   - ``metrics.json``    — structural + classifier metrics
   - ``snapshots.txt`` and ``snapshots.md``

Production behavior is untouched. The runner does NOT activate
``pipeline.merge_debug_config`` overrides — it calls the merge
functions directly with explicit threshold arguments. The override
module exists for future opt-in use (e.g. running a full Start
Transcription end-to-end with a tighter gap, where the overrides do
reach the active path).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline.assembler import (
    SHORT_GAP_THRESHOLD_SECONDS as ASSEMBLER_SHORT_GAP_DEFAULT,
    MIN_UTTERANCE_WORDS,
    _attach_speaker_labels,
    build_transcript_text,
    merge_utterances as assembler_merge,
)
from pipeline.transcriber import (
    MERGE_MIN_WORD_COUNT,
    merge_utterances as transcriber_merge,
    smooth_speakers,
    _annotate_confidence,
)
from spec_engine.block_builder import build_blocks
from spec_engine.classifier import classify_blocks

from tools.investigation.merge_threshold_matrix import (
    ALL_CONFIGS,
    MergeConfig,
)
from tools.investigation.analyze_utterance_structure import (
    analyze as analyze_structure,
)
from tools.investigation.export_transcript_snapshots import (
    collect as collect_snapshots,
    write_outputs as write_snapshot_outputs,
)


def _load_chunked_native_utterances(raw_json: dict) -> list[list[dict]]:
    """Return per-chunk Deepgram-native utterance arrays.

    Source: ``raw_deepgram.json["chunks"][i]["results"]["utterances"]``.
    These are the deepest pre-merge utterances still saved on disk.
    """
    chunks = raw_json.get("chunks") or []
    out: list[list[dict]] = []
    for chunk in chunks:
        utts = (chunk.get("results") or {}).get("utterances") or []
        out.append(list(utts))
    return out


def _shape_for_transcriber_merge(utt: dict) -> dict:
    """Bring a Deepgram-native utterance dict into the shape the per-chunk
    merge_utterances + _annotate_confidence helpers expect.

    Production wiring (see ``pipeline.transcriber._transcribe_direct``):

    - keys ``start``, ``end``, ``transcript`` are required
    - ``speaker`` is the integer speaker id
    - ``words`` is the per-word list with ``start``, ``end``,
      ``speaker``, ``word``, ``punctuated_word``, ``confidence``

    The Deepgram-native utterances already carry these keys.
    """
    out = {
        "start": utt.get("start", 0.0),
        "end": utt.get("end", 0.0),
        "transcript": utt.get("transcript", ""),
        "speaker": utt.get("speaker"),
        "confidence": utt.get("confidence", 1.0),
        "words": [
            {
                "word": w.get("word", ""),
                "start": w.get("start", 0.0),
                "end": w.get("end", 0.0),
                "speaker": w.get("speaker"),
                "confidence": w.get("confidence", 1.0),
                "punctuated_word": w.get("punctuated_word", w.get("word", "")),
                "type": w.get("type", "word"),
            }
            for w in (utt.get("words") or [])
        ],
    }
    return out


def _classifier_counts(utterances: list[dict]) -> dict[str, int]:
    """Spec_engine block-type counts on the merged utterances."""
    adapted: list[dict] = []
    for u in utterances or []:
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
        adapted.append({"speaker": str(speaker), "text": text, "type": "utterance"})
    if not adapted:
        return {"total_blocks": 0}
    blocks = build_blocks({"utterances": adapted})
    classified = classify_blocks(blocks)
    counts: dict[str, int] = {"total_blocks": len(classified)}
    for b in classified:
        counts[b.type] = counts.get(b.type, 0) + 1
    return counts


def run_one(
    config: MergeConfig,
    per_chunk_utterances: list[list[dict]],
    chunk_offsets: list[float],
    out_root: Path,
) -> dict[str, Any]:
    """Run a single MergeConfig end-to-end and write artifacts."""
    out_dir = out_root / config.name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1 — apply per-chunk merge with experimental in_chunk_gap.
    per_chunk_merged: list[list[dict]] = []
    for utts in per_chunk_utterances:
        shaped = [_shape_for_transcriber_merge(u) for u in utts]
        shaped = [_annotate_confidence(u) for u in shaped]
        shaped = smooth_speakers(shaped)
        merged = transcriber_merge(
            shaped,
            gap_threshold_seconds=config.in_chunk_gap,
            min_word_count=MERGE_MIN_WORD_COUNT,
        )
        merged = [_annotate_confidence(u) for u in merged]
        per_chunk_merged.append(merged)

    # Stage 2 — apply cross-chunk timestamp offset, then assembler merge
    # with experimental cross_chunk_gap.
    pooled: list[dict] = []
    for i, merged in enumerate(per_chunk_merged):
        offset = float(chunk_offsets[i]) if i < len(chunk_offsets) else 0.0
        for u in merged:
            adjusted = dict(u)
            adjusted["start"] = round(float(u.get("start", 0.0) or 0.0) + offset, 3)
            adjusted["end"] = round(float(u.get("end", 0.0) or 0.0) + offset, 3)
            pooled.append(adjusted)
    pooled.sort(key=lambda u: float(u.get("start", 0.0) or 0.0))

    # Honor the per-config gap on both the main and short-utterance gates.
    short_gap = min(ASSEMBLER_SHORT_GAP_DEFAULT, config.cross_chunk_gap)
    assembled = assembler_merge(
        pooled,
        gap_threshold_seconds=config.cross_chunk_gap,
        short_gap_threshold_seconds=short_gap,
        min_word_count=MIN_UTTERANCE_WORDS,
    )
    labeled = _attach_speaker_labels(assembled)

    # Persist artifacts.
    (out_dir / "utterances.json").write_text(
        json.dumps({"utterances": labeled}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    transcript = build_transcript_text(labeled)
    (out_dir / "transcript.txt").write_text(transcript, encoding="utf-8")

    structure = analyze_structure(labeled)
    classifier = _classifier_counts(labeled)
    metrics = {
        "config": {
            "name": config.name,
            "in_chunk_gap": config.in_chunk_gap,
            "cross_chunk_gap": config.cross_chunk_gap,
            "description": config.description,
        },
        "input_utterance_count_pre_per_chunk_merge": sum(
            len(c) for c in per_chunk_utterances
        ),
        "post_per_chunk_merge_count": sum(len(c) for c in per_chunk_merged),
        "structure": structure,
        "classifier": classifier,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    snaps = collect_snapshots(labeled)
    write_snapshot_outputs(snaps, out_dir, source_label=config.name)

    return metrics


def _derive_chunk_offsets(raw_json: dict) -> list[float]:
    """Recover per-chunk start offsets from chunk_summaries metadata."""
    chunk_summaries = raw_json.get("chunk_summaries") or []
    offsets: list[float] = []
    for summary in chunk_summaries:
        # chunk_summaries entries carry "start_seconds" (per
        # core/job_runner.py::_build_chunk_summaries).
        offset = summary.get("start_seconds")
        if offset is None:
            # Fallback to derive from cumulative duration if start missing.
            offset = sum(s.get("duration_seconds", 0.0) for s in offsets)
        offsets.append(float(offset))
    return offsets


def run(case_dir: Path, out_root: Path) -> Path:
    case_dir = case_dir.resolve()
    raw_json_path = case_dir / "Deepgram" / "raw_deepgram.json"
    if not raw_json_path.exists():
        raise FileNotFoundError(f"Missing: {raw_json_path}")

    raw_json = json.loads(raw_json_path.read_text(encoding="utf-8"))
    per_chunk = _load_chunked_native_utterances(raw_json)
    if not per_chunk or not any(per_chunk):
        raise RuntimeError(
            "raw_deepgram.json has no chunks[*].results.utterances data."
        )
    chunk_offsets = _derive_chunk_offsets(raw_json)
    if len(chunk_offsets) < len(per_chunk):
        # Pad with zero — better than aborting; cross-chunk merge will
        # still work because timestamps stay self-consistent within
        # each chunk's range.
        chunk_offsets = chunk_offsets + [0.0] * (
            len(per_chunk) - len(chunk_offsets)
        )

    case_name = case_dir.name
    case_root = out_root / case_name
    case_root.mkdir(parents=True, exist_ok=True)

    all_metrics: list[dict[str, Any]] = []
    for cfg in ALL_CONFIGS:
        metrics = run_one(cfg, per_chunk, chunk_offsets, case_root)
        all_metrics.append(metrics)
        s = metrics["structure"]
        c = metrics["classifier"]
        print(
            f"  {cfg.name}: utts={s.get('utterance_count', 0)} "
            f"merged_qa={s.get('merged_qa_candidates', 0)} "
            f"spk_switch={s.get('speaker_transition_inside_utterance', 0)} "
            f"short_ans={s.get('standalone_short_answers', 0)} "
            f"colloquy={c.get('colloquy', 0)}"
        )

    (case_root / "all_metrics.json").write_text(
        json.dumps({"runs": all_metrics}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return case_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the 4-config merge-threshold experiment matrix on a case."
        )
    )
    parser.add_argument(
        "--case-dir",
        required=True,
        help="Case folder containing Deepgram/raw_deepgram.json.",
    )
    parser.add_argument(
        "--out-root",
        default="docs/investigations/merge_threshold_testing/runs",
        help=(
            "Root directory for run outputs (default: "
            "docs/investigations/merge_threshold_testing/runs)."
        ),
    )
    args = parser.parse_args()

    try:
        case_root = run(Path(args.case_dir), Path(args.out_root))
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Outputs: {case_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
