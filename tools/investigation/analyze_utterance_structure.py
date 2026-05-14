"""Analyze utterance structure from a Deepgram or merged-utterance JSON.

Computes legal-deposition-relevant structural metrics:

- utterance count
- average / median / max duration
- long utterance count (> threshold, default 30s)
- suspicious merged-Q/A indicators (utterance has a `?` and a
  trailing/embedded short-answer phrase)
- speaker-transition-inside-utterance count (utterance's word-level
  speaker labels include more than one distinct speaker)

Inputs accepted:

- A raw_deepgram.json file (will analyze the post-assembler-merge
  ``utterances`` array by default; pass ``--field raw_utterances``
  for the pre-assembler set, or ``--field chunks`` to pool every
  chunk's Deepgram-native ``results.utterances``).
- A standalone JSON file containing ``{"utterances": [...]}``
  (e.g. the per-run artifact written by
  ``tools.investigation.run_merge_experiments``).

Outputs:

- ``<out_dir>/<stem>_structure.json``
- ``<out_dir>/<stem>_structure.md``

This is investigation-only. No production code path imports it.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

DEFAULT_LONG_DURATION_SECONDS = 30.0

_QUESTION_MARK_RE = re.compile(r"\?")
_SHORT_ANSWER_RE = re.compile(
    r"\b(yes|no|correct|right|wrong)\b\.?",
    re.IGNORECASE,
)
_STANDALONE_ANSWER_RE = re.compile(
    r"^\s*(yes|no|correct)\.?\s*$",
    re.IGNORECASE,
)


def _utterance_word_count(u: dict) -> int:
    words = u.get("words") or []
    if words:
        return len(words)
    return len((u.get("transcript") or u.get("text") or "").split())


def _utterance_duration(u: dict) -> float:
    try:
        s = float(u.get("start", 0.0) or 0.0)
        e = float(u.get("end", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, e - s)


def _utterance_text(u: dict) -> str:
    return (u.get("transcript") or u.get("text") or "").strip()


def _speakers_in_words(u: dict) -> set:
    speakers = set()
    for w in u.get("words") or []:
        spk = w.get("speaker") if isinstance(w, dict) else None
        if spk is not None:
            speakers.add(spk)
    return speakers


def _looks_like_merged_qa(u: dict) -> bool:
    text = _utterance_text(u)
    if not text or not _QUESTION_MARK_RE.search(text):
        return False
    for match in _SHORT_ANSWER_RE.finditer(text):
        if match.start() < 5:
            continue
        preceding = text[max(0, match.start() - 2): match.start()].strip()
        if preceding.endswith((".", "?", "!")):
            return True
        end = match.end()
        if end < len(text) and text[end:end + 2].startswith("."):
            return True
    return False


def _is_standalone_answer(u: dict) -> bool:
    return bool(_STANDALONE_ANSWER_RE.match(_utterance_text(u)))


def load_utterances(json_path: Path, field: str) -> list[dict]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if field == "auto":
        for candidate in ("utterances", "raw_utterances"):
            if isinstance(data.get(candidate), list) and data[candidate]:
                return data[candidate]
        if isinstance(data, list):
            return data
        raise ValueError(
            f"{json_path}: no utterances/raw_utterances list found "
            f"(top-level keys: {list(data.keys())})"
        )
    if field == "chunks":
        pooled: list[dict] = []
        for chunk in data.get("chunks") or []:
            pooled.extend(
                chunk.get("results", {}).get("utterances") or []
            )
        return pooled
    value = data.get(field)
    if not isinstance(value, list):
        raise ValueError(
            f"{json_path}: field '{field}' is not a list "
            f"(got {type(value).__name__})"
        )
    return value


def analyze(
    utterances: list[dict],
    *,
    long_duration_seconds: float = DEFAULT_LONG_DURATION_SECONDS,
) -> dict[str, Any]:
    if not utterances:
        return {
            "utterance_count": 0,
            "long_duration_threshold": long_duration_seconds,
        }

    durations = [_utterance_duration(u) for u in utterances]
    word_counts = [_utterance_word_count(u) for u in utterances]

    merged_qa = sum(1 for u in utterances if _looks_like_merged_qa(u))
    speaker_switch = sum(
        1 for u in utterances if len(_speakers_in_words(u)) > 1
    )
    standalone_answers = sum(
        1 for u in utterances if _is_standalone_answer(u)
    )
    long_utterances = sum(1 for d in durations if d > long_duration_seconds)
    over_100_words = sum(1 for w in word_counts if w > 100)

    return {
        "utterance_count": len(utterances),
        "long_duration_threshold": long_duration_seconds,
        "duration_seconds": {
            "avg": round(statistics.mean(durations), 3),
            "median": round(statistics.median(durations), 3),
            "max": round(max(durations), 3),
            "min": round(min(durations), 3),
        },
        "words_per_utterance": {
            "avg": round(statistics.mean(word_counts), 2),
            "median": statistics.median(word_counts),
            "max": max(word_counts),
        },
        "long_utterance_count": long_utterances,
        "over_100_words_count": over_100_words,
        "merged_qa_candidates": merged_qa,
        "speaker_transition_inside_utterance": speaker_switch,
        "standalone_short_answers": standalone_answers,
    }


def write_outputs(
    structure: dict[str, Any],
    source_path: Path,
    out_dir: Path,
    field: str,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = source_path.stem
    json_path = out_dir / f"{stem}_structure.json"
    md_path = out_dir / f"{stem}_structure.md"

    json_path.write_text(
        json.dumps(
            {
                "source": str(source_path),
                "field": field,
                "structure": structure,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines: list[str] = []
    lines.append(f"# Utterance structure — `{source_path.name}`")
    lines.append("")
    lines.append(f"- Source: `{source_path}`")
    lines.append(f"- Field analyzed: `{field}`")
    lines.append(f"- Utterance count: **{structure.get('utterance_count', 0)}**")
    lines.append(
        f"- Long-duration threshold: "
        f"{structure.get('long_duration_threshold', '?')}s"
    )
    lines.append("")
    if structure.get("utterance_count"):
        ds = structure["duration_seconds"]
        ws = structure["words_per_utterance"]
        lines.append("## Duration (seconds)")
        lines.append("")
        lines.append(
            f"- avg: **{ds['avg']}**, median: {ds['median']}, "
            f"min: {ds['min']}, max: {ds['max']}"
        )
        lines.append("")
        lines.append("## Words per utterance")
        lines.append("")
        lines.append(
            f"- avg: **{ws['avg']}**, median: {ws['median']}, max: {ws['max']}"
        )
        lines.append("")
        lines.append("## Structural indicators")
        lines.append("")
        lines.append(
            f"- Long utterances "
            f"(> {structure['long_duration_threshold']}s): "
            f"**{structure['long_utterance_count']}**"
        )
        lines.append(
            f"- > 100-word utterances: **{structure['over_100_words_count']}**"
        )
        lines.append(
            f"- Suspicious merged Q/A "
            f"(has `?` + mid-utterance Yes/No): "
            f"**{structure['merged_qa_candidates']}**"
        )
        lines.append(
            f"- Speaker transition inside utterance "
            f"(word-level speakers > 1 in one utterance): "
            f"**{structure['speaker_transition_inside_utterance']}**"
        )
        lines.append(
            f"- Standalone short answers ('Yes.'/'No.'/'Correct.' alone): "
            f"**{structure['standalone_short_answers']}**"
        )
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze utterance structure from a Deepgram or "
            "merged-utterance JSON file."
        )
    )
    parser.add_argument("json_path", help="Path to the JSON file.")
    parser.add_argument(
        "--field",
        default="auto",
        choices=["auto", "utterances", "raw_utterances", "chunks"],
        help="Which array to analyze (default: auto).",
    )
    parser.add_argument(
        "--out-dir",
        default="output/investigation",
        help="Output directory (default: output/investigation).",
    )
    parser.add_argument(
        "--long-duration-seconds",
        type=float,
        default=DEFAULT_LONG_DURATION_SECONDS,
        help=f"Long-utterance threshold (default: {DEFAULT_LONG_DURATION_SECONDS}s).",
    )
    args = parser.parse_args()

    try:
        source_path = Path(args.json_path).resolve()
        utterances = load_utterances(source_path, args.field)
        structure = analyze(
            utterances,
            long_duration_seconds=args.long_duration_seconds,
        )
        json_out, md_out = write_outputs(
            structure=structure,
            source_path=source_path,
            out_dir=Path(args.out_dir),
            field=args.field,
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Wrote: {json_out}")
    print(f"       {md_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
