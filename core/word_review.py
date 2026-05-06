"""Low-confidence word-review helpers.

Pure functions over Deepgram word-level data. The transcript pipeline
itself is not affected — this module only consumes the words that
core/job_runner.py already saves to the per-run JSON, and produces the
review queue the UI surfaces in its proofreading panel.

Phase 1 surface area:
- WordReviewItem dataclass
- build_review_items(words, threshold) -> list[WordReviewItem]

Out of scope (intentionally):
- word-click editing
- speaker-role inference
- transcript mutation
- Deepgram request changes
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WordReviewItem:
    """One word flagged for proofreading review.

    Mirrors the Deepgram word-shape we already persist in the per-run
    JSON. `index` is the position in the *flagged* list, not the source
    transcript — callers iterate this list to step Prev/Next.
    """

    index: int
    word: str
    punctuated_word: str
    start: float
    end: float
    confidence: float
    speaker: int | None = None
    reviewed: bool = False
    issue_type: str = "low_confidence"


def _coerce_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_str(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def build_review_items(
    words: list[dict],
    threshold: float = 0.75,
) -> list[WordReviewItem]:
    """Filter Deepgram word objects down to those whose confidence is
    below `threshold`, returning a list of WordReviewItem in source
    order.

    Rules (from the Phase 1 spec):
      - confidence < threshold to be included
      - prefer `punctuated_word` over `word` if available
      - preserve start / end / confidence / speaker
      - do not mutate the input dicts
      - do not infer speaker roles
      - handle missing fields safely (graceful coercion)

    Words missing a numeric `confidence` are treated as confidence 1.0
    (not flagged) — the review panel is meant to surface words Deepgram
    itself was uncertain about, and a missing confidence is more often
    a non-word artefact than a low-confidence flag.

    `index` on each returned item is the index *within the resulting
    list*, so the UI can address review items by an integer cursor
    independent of their position in the original word stream.
    """
    if not words:
        return []

    items: list[WordReviewItem] = []
    for raw in words:
        if not isinstance(raw, dict):
            continue
        # Confidence missing -> treat as 1.0 (not flagged). This avoids
        # surfacing every non-word artefact (no-confidence punctuation
        # entries, sentinel rows, etc.).
        if "confidence" not in raw:
            continue
        confidence = _coerce_float(raw.get("confidence"), default=1.0)
        if confidence >= threshold:
            continue

        word = _coerce_str(raw.get("word"))
        punctuated = _coerce_str(raw.get("punctuated_word"), default=word) or word

        speaker_raw = raw.get("speaker")
        speaker: int | None
        if speaker_raw is None:
            speaker = None
        else:
            try:
                speaker = int(speaker_raw)
            except (TypeError, ValueError):
                speaker = None

        items.append(
            WordReviewItem(
                index=len(items),
                word=word,
                punctuated_word=punctuated or word,
                start=_coerce_float(raw.get("start")),
                end=_coerce_float(raw.get("end")),
                confidence=confidence,
                speaker=speaker,
            )
        )

    return items
