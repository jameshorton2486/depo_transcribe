"""Render a confidence-annotated copy of an existing deposition DOCX.

Reads ``<case_dir>/_walkthrough/02_after_ai_cleanup.txt`` (the
formatter output that already carries ``‹LC:word›`` markers around
the surviving low-confidence tokens) and rewrites each marker to
``‹LC:word (0.NN)›`` by matching tokens against the low-confidence
entries in ``<case_dir>/Deepgram/raw_deepgram.json``.

The annotated text is then handed to the standard
``clean_format.docx_writer.write_deposition_docx``, which highlights
every marker body in yellow. Result: a DOCX visually identical to
``<Witness>_Deposition_<date>.docx`` except that every yellow chunk
now contains the score alongside the original word.

Output: ``<Witness>_Deposition_<date>_confidence.docx`` in the same
case folder.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any

from clean_format.docx_writer import write_deposition_docx
from clean_format.low_confidence_markers import (
    LOW_CONF_CLOSE,
    LOW_CONF_OPEN,
)
from config import LOW_CONFIDENCE_THRESHOLD


# Capture the wrapped token (group 1) so we can rebuild the marker
# with a confidence suffix while leaving surrounding punctuation alone.
_MARKER_RE = re.compile(
    rf"{re.escape(LOW_CONF_OPEN)}([^{re.escape(LOW_CONF_CLOSE)}]*){re.escape(LOW_CONF_CLOSE)}"
)


def _strip_trailing_punct(token: str) -> str:
    """Strip trailing punctuation so 'said.' matches Deepgram's 'said'."""
    return re.sub(r"[^\w'’\-]+$", "", token or "")


def _normalize_for_match(token: str) -> str:
    """Case-fold + trailing-punct strip for the lookup key."""
    return _strip_trailing_punct(token or "").lower()


def _build_lc_queue(
    words: list[dict[str, Any]],
    threshold: float,
) -> dict[str, collections.deque]:
    """Per-text FIFO queues of confidences for tokens below threshold.

    The same word may appear many times with different confidences,
    each occurrence below threshold. We pop them in order each time a
    marker with matching text is encountered in the cleaned transcript.
    """
    queue: dict[str, collections.deque] = collections.defaultdict(
        collections.deque
    )
    for w in words or []:
        if not isinstance(w, dict):
            continue
        try:
            conf = float(w.get("confidence", 1.0))
        except (TypeError, ValueError):
            continue
        if conf >= threshold:
            continue
        word_text = _normalize_for_match(str(w.get("word", "")))
        if not word_text:
            continue
        queue[word_text].append(conf)
    return queue


def annotate_text(
    cleaned_text: str,
    deepgram_words: list[dict[str, Any]],
    *,
    threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> tuple[str, dict[str, int]]:
    """Rewrite ``‹LC:word›`` to ``‹LC:word (0.NN)›`` in ``cleaned_text``.

    Returns ``(annotated_text, stats)``. Stats reports how many
    markers were matched vs. left unannotated.
    """
    lc_queue = _build_lc_queue(deepgram_words, threshold)
    stats = {"markers": 0, "matched": 0, "unmatched": 0}

    def _replace(match: re.Match[str]) -> str:
        stats["markers"] += 1
        body = match.group(1)
        key = _normalize_for_match(body)
        queue = lc_queue.get(key)
        if queue:
            conf = queue.popleft()
            stats["matched"] += 1
            return f"{LOW_CONF_OPEN}{body} ({conf:.2f}){LOW_CONF_CLOSE}"
        stats["unmatched"] += 1
        return f"{LOW_CONF_OPEN}{body} (?){LOW_CONF_CLOSE}"

    annotated = _MARKER_RE.sub(_replace, cleaned_text)
    return annotated, stats


def run(case_dir: Path) -> tuple[Path, dict[str, int]]:
    case_dir = case_dir.resolve()
    cleaned_path = case_dir / "_walkthrough" / "02_after_ai_cleanup.txt"
    raw_json_path = case_dir / "Deepgram" / "raw_deepgram.json"
    case_meta_path = case_dir / "case_meta.json"

    for required in (cleaned_path, raw_json_path, case_meta_path):
        if not required.exists():
            raise FileNotFoundError(f"Required file missing: {required}")

    cleaned_text = cleaned_path.read_text(encoding="utf-8")
    case_meta = json.loads(case_meta_path.read_text(encoding="utf-8"))

    with raw_json_path.open("r", encoding="utf-8") as handle:
        deepgram_data = json.load(handle)
    deepgram_words = deepgram_data.get("words") or []

    annotated_text, stats = annotate_text(
        cleaned_text,
        deepgram_words,
        threshold=LOW_CONFIDENCE_THRESHOLD,
    )

    witness_last = (
        case_meta.get("witness_name", "Witness").split() or ["Witness"]
    )[-1]
    date_part = (
        str(case_meta.get("deposition_date", ""))
        .replace("/", "-")
        .replace(",", "")
    )
    output_path = case_dir / f"{witness_last}_Deposition_{date_part}_confidence.docx"
    saved = write_deposition_docx(annotated_text, case_meta, output_path)
    return Path(saved), stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render a copy of the deposition DOCX with Deepgram "
            "confidence scores shown inside each yellow-highlighted run."
        )
    )
    parser.add_argument(
        "case_dir",
        help=(
            "Case folder (must contain "
            "_walkthrough/02_after_ai_cleanup.txt and "
            "Deepgram/raw_deepgram.json)."
        ),
    )
    args = parser.parse_args()

    try:
        saved, stats = run(Path(args.case_dir))
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Wrote: {saved}")
    print(
        f"Markers: {stats['markers']}  "
        f"matched: {stats['matched']}  "
        f"unmatched: {stats['unmatched']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
