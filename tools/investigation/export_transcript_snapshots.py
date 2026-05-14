"""Export representative transcript snippets from a merged-utterance JSON.

Categories exported:

- **rapid_fire_qa** — sequences with 3+ consecutive short utterances
  (≤ 5 words each) alternating between two speakers. Useful to see
  whether Q/A pairs survive a given merge configuration.
- **objections** — utterances whose lowercase text contains
  ``objection`` / ``form`` / ``foundation``.
- **colloquy** — substantive single-speaker turns 10-60 words long
  without a ``?`` or short-answer phrase. Indicator of clean
  monologue rendering.
- **problematic_merges** — utterances flagged by
  ``analyze_utterance_structure``-style heuristics: contains both
  ``?`` and a mid-utterance "Yes."/"No."/"Correct.", or > 100 words.

Outputs (in the target directory):

- ``snapshots.txt`` — plain text, all categories
- ``snapshots.md``  — markdown, grouped by category

Investigation-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_QUESTION_MARK_RE = re.compile(r"\?")
_SHORT_ANSWER_RE = re.compile(
    r"\b(yes|no|correct|right|wrong)\b\.?",
    re.IGNORECASE,
)
_STANDALONE_ANSWER_RE = re.compile(
    r"^\s*(yes|no|correct)\.?\s*$",
    re.IGNORECASE,
)
_OBJECTION_RE = re.compile(r"\b(objection|foundation|privilege)\b", re.IGNORECASE)

RAPID_FIRE_MAX_WORDS = 5
RAPID_FIRE_MIN_RUN = 3
COLLOQUY_MIN_WORDS = 10
COLLOQUY_MAX_WORDS = 60
SAMPLE_LIMIT = 5
TEXT_TRUNCATE = 320


def _text(u: dict) -> str:
    return (u.get("transcript") or u.get("text") or "").strip()


def _wc(u: dict) -> int:
    words = u.get("words") or []
    if words:
        return len(words)
    return len(_text(u).split())


def _speaker_label(u: dict) -> str:
    return str(u.get("speaker_label") or f"speaker {u.get('speaker', '?')}")


def _truncate(t: str, n: int = TEXT_TRUNCATE) -> str:
    t = (t or "").strip().replace("\n", " ")
    if len(t) <= n:
        return t
    return t[:n - 1].rstrip() + "…"


def _looks_like_merged_qa(u: dict) -> bool:
    text = _text(u)
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


def _format_sample(u: dict) -> dict[str, Any]:
    return {
        "speaker": _speaker_label(u),
        "word_count": _wc(u),
        "start": u.get("start"),
        "end": u.get("end"),
        "text": _truncate(_text(u)),
    }


def collect(utterances: list[dict]) -> dict[str, list[dict]]:
    samples: dict[str, list[dict]] = {
        "rapid_fire_qa": [],
        "objections": [],
        "colloquy": [],
        "problematic_merges": [],
    }

    # Rapid-fire Q/A: find a window of >= RAPID_FIRE_MIN_RUN utterances
    # all <= RAPID_FIRE_MAX_WORDS, alternating between two speakers.
    i = 0
    while i < len(utterances) and len(samples["rapid_fire_qa"]) < SAMPLE_LIMIT:
        run: list[dict] = []
        speakers_seen: set = set()
        j = i
        while (
            j < len(utterances)
            and _wc(utterances[j]) <= RAPID_FIRE_MAX_WORDS
        ):
            run.append(utterances[j])
            speakers_seen.add(_speaker_label(utterances[j]))
            j += 1
        if len(run) >= RAPID_FIRE_MIN_RUN and len(speakers_seen) >= 2:
            samples["rapid_fire_qa"].append(
                {
                    "start": run[0].get("start"),
                    "end": run[-1].get("end"),
                    "count": len(run),
                    "speakers": sorted(speakers_seen),
                    "text": " | ".join(
                        f"{_speaker_label(u)}: {_truncate(_text(u), 60)}"
                        for u in run
                    ),
                }
            )
            i = j
        else:
            i = max(i + 1, j)

    # Objections / colloquy / problematic_merges — linear scan.
    for u in utterances:
        text = _text(u)
        if not text:
            continue
        if (
            _OBJECTION_RE.search(text)
            and len(samples["objections"]) < SAMPLE_LIMIT
        ):
            samples["objections"].append(_format_sample(u))
        wc = _wc(u)
        if (
            COLLOQUY_MIN_WORDS <= wc <= COLLOQUY_MAX_WORDS
            and "?" not in text
            and not _SHORT_ANSWER_RE.search(text)
            and len(samples["colloquy"]) < SAMPLE_LIMIT
        ):
            samples["colloquy"].append(_format_sample(u))
        if (
            (wc > 100 or _looks_like_merged_qa(u))
            and len(samples["problematic_merges"]) < SAMPLE_LIMIT
        ):
            samples["problematic_merges"].append(_format_sample(u))

    return samples


def write_outputs(
    samples: dict[str, list[dict]],
    out_dir: Path,
    source_label: str,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / "snapshots.txt"
    md_path = out_dir / "snapshots.md"

    txt_lines: list[str] = [f"=== Transcript snapshots — {source_label} ===", ""]
    md_lines: list[str] = [f"# Transcript snapshots — `{source_label}`", ""]

    for category, items in samples.items():
        title = category.replace("_", " ").title()
        txt_lines.append(f"--- {title} ({len(items)}) ---")
        md_lines.append(f"## {title} ({len(items)})")
        md_lines.append("")
        if not items:
            txt_lines.append("(none)")
            md_lines.append("_(none found)_")
            md_lines.append("")
            continue
        for s in items:
            if category == "rapid_fire_qa":
                ts = ""
                if isinstance(s.get("start"), (int, float)) and isinstance(
                    s.get("end"), (int, float)
                ):
                    ts = f" t={s['start']:.2f}-{s['end']:.2f}s"
                txt_lines.append(
                    f"[{s['count']} utts; speakers={s['speakers']};{ts}] "
                    f"{s['text']}"
                )
                md_lines.append(
                    f"- **run of {s['count']} short turns** "
                    f"(speakers={', '.join(s['speakers'])}{ts})"
                )
                md_lines.append(f"  > {s['text']}")
            else:
                ts = ""
                if isinstance(s.get("start"), (int, float)) and isinstance(
                    s.get("end"), (int, float)
                ):
                    ts = f" t={s['start']:.2f}-{s['end']:.2f}s"
                txt_lines.append(
                    f"[{s['speaker']}; {s['word_count']} words;{ts}] "
                    f"{s['text']}"
                )
                md_lines.append(
                    f"- **{s['speaker']}** ({s['word_count']} words{ts})"
                )
                md_lines.append(f"  > {s['text']}")
        txt_lines.append("")
        md_lines.append("")

    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return txt_path, md_path


def load_utterances(json_path: Path, field: str) -> list[dict]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if field == "auto":
        for candidate in ("utterances", "raw_utterances"):
            if isinstance(data.get(candidate), list) and data[candidate]:
                return data[candidate]
        raise ValueError(
            f"{json_path}: no utterances/raw_utterances list found"
        )
    value = data.get(field)
    if not isinstance(value, list):
        raise ValueError(
            f"{json_path}: field '{field}' is not a list"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export representative transcript snippets from a "
            "merged-utterance JSON file."
        )
    )
    parser.add_argument("json_path", help="Path to the JSON file.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    parser.add_argument(
        "--field",
        default="auto",
        choices=["auto", "utterances", "raw_utterances"],
        help="Which array to read (default: auto).",
    )
    parser.add_argument(
        "--source-label",
        default=None,
        help="Human-readable label for the snapshot title.",
    )
    args = parser.parse_args()

    try:
        source_path = Path(args.json_path).resolve()
        utterances = load_utterances(source_path, args.field)
        samples = collect(utterances)
        label = args.source_label or source_path.name
        txt_out, md_out = write_outputs(samples, Path(args.out_dir), label)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Wrote: {txt_out}")
    print(f"       {md_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
