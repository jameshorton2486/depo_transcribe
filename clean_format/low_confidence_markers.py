"""Low-confidence Deepgram token marking for the clean_format pipeline.

Step C of the verbatim-punctuation plan
(docs/plans/verbatim_punctuation_plan_2026-05-12.md). Wraps Deepgram
tokens whose confidence falls below `LOW_CONFIDENCE_THRESHOLD` in
inline markers that survive an Anthropic cleanup round-trip. Step D
consumes the marker-bearing text in the DOCX writer to render those
tokens with a yellow highlight.

Marker form: ``‹LC:word›``
  - Open  = U+2039 (single left-pointing angle quotation mark) + ``LC:``
  - Close = U+203A (single right-pointing angle quotation mark)

Chosen for:
  - Single Unicode-char boundaries (low token cost in the API call).
  - The ``LC:`` namespace prefix makes the directive intent obvious to
    the Anthropic model and to any human reviewing the cleaned text.
  - U+2039/U+203A are essentially absent from English-language Texas
    deposition transcripts, minimising false-positive collision.

The marker is a closed format: nothing inside the marker but the
literal token text. Spaces, punctuation, and surrounding whitespace
stay OUTSIDE the marker. This keeps Step D's run-splitting trivial.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from config import LOW_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

LOW_CONF_OPEN = "‹LC:"
LOW_CONF_CLOSE = "›"

# Capturing group 1 = the wrapped token text (no markers, no surrounding
# whitespace). Body excludes the close character itself, so nested or
# malformed markers are rejected.
LOW_CONF_MARKER_RE = re.compile(
    rf"{re.escape(LOW_CONF_OPEN)}([^{re.escape(LOW_CONF_CLOSE)}]*){re.escape(LOW_CONF_CLOSE)}"
)


def _word_match_pattern(word_text: str) -> re.Pattern[str]:
    """Build a case-insensitive whole-word pattern for a Deepgram token.

    Word boundaries (``\\b``) keep the match aligned with surrounding
    punctuation without consuming it — the token "said" matches inside
    "said," or "said.", but not inside "unsaid". Apostrophes and hyphens
    inside the token (``don't``, ``first-time``) are escaped and matched
    literally.
    """
    return re.compile(rf"\b{re.escape(word_text)}\b", re.IGNORECASE)


def inject_markers(
    raw_text: str,
    words: Iterable[dict[str, Any]] | None,
    *,
    threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> str:
    """Wrap low-confidence Deepgram tokens in ``raw_text`` with markers.

    Walks ``words`` in order, locating each in ``raw_text`` past the
    current cursor. When a word's confidence falls below ``threshold``,
    the matched span is wrapped with ``‹LC:...›``.

    Tolerant of:
      - Case differences between Deepgram token and rendered text.
      - Trailing punctuation in the rendered text (kept outside marker).
      - Tokens that don't appear in ``raw_text`` because upstream
        post-processing rewrote them (those words are skipped silently;
        marker alignment is preserved for the remainder).

    When ``words`` is None or empty, ``raw_text`` is returned unchanged.
    The function never raises on malformed input — degraded behavior
    (some markers missing) is preferred to a crashed pipeline.
    """
    if not words or not raw_text:
        return raw_text

    pieces: list[str] = []
    cursor = 0

    for word in words:
        if not isinstance(word, dict):
            continue
        word_text = str(word.get("word", "") or "").strip()
        if not word_text:
            continue

        try:
            confidence = float(word.get("confidence", 1.0))
        except (TypeError, ValueError):
            continue

        pattern = _word_match_pattern(word_text)
        match = pattern.search(raw_text, cursor)
        if match is None:
            # Token couldn't be located past the cursor — skip silently.
            # Alignment for remaining tokens is preserved because we did
            # not advance the cursor.
            continue

        pieces.append(raw_text[cursor:match.start()])
        if confidence < threshold:
            pieces.append(f"{LOW_CONF_OPEN}{match.group(0)}{LOW_CONF_CLOSE}")
        else:
            pieces.append(match.group(0))
        cursor = match.end()

    pieces.append(raw_text[cursor:])
    return "".join(pieces)


def count_markers(text: str) -> int:
    """Return the number of ``‹LC:...›`` marker pairs in ``text``."""
    if not text:
        return 0
    return len(LOW_CONF_MARKER_RE.findall(text))


def strip_markers(text: str) -> str:
    """Return ``text`` with all ``‹LC:...›`` markers removed (content kept).

    Useful for debugging, fallback rendering, and emergency comparison.
    Step D's DOCX renderer does not call this — it uses ``split_into_runs``
    so the marker boundary informs the highlight.
    """
    return LOW_CONF_MARKER_RE.sub(lambda m: m.group(1), text or "")


def split_into_runs(text: str) -> list[tuple[str, bool]]:
    """Split ``text`` into ``(chunk, is_low_confidence)`` tuples.

    Used by Step D's DOCX renderer to emit a separate ``Run`` per chunk
    so the low-confidence chunks can be highlighted yellow while the
    surrounding text stays default-styled.

    The returned list reconstructs ``text`` exactly when concatenated
    after stripping markers — i.e., ``"".join(c for c, _ in result)``
    equals ``strip_markers(text)``.

    An empty input yields an empty list, not ``[("", False)]``.
    """
    if not text:
        return []

    parts: list[tuple[str, bool]] = []
    cursor = 0
    for match in LOW_CONF_MARKER_RE.finditer(text):
        if match.start() > cursor:
            parts.append((text[cursor:match.start()], False))
        body = match.group(1)
        if body:
            parts.append((body, True))
        cursor = match.end()
    if cursor < len(text):
        parts.append((text[cursor:], False))
    return parts


# Drift tolerance for marker round-trip validation. Originally 5.0%
# but raised to 10.0% after empirical observation across 7 runs on the
# Cavazos case (0/0/0/0/0/6.5/85.1 percent across iterations spanning
# Phase 2A wiring and Phase 2A.1 prompt fix). The 10% threshold catches
# catastrophic regressions (>10% indicates systematic prompt failure)
# while accepting normal stochastic interpretation variance from the
# cleanup model. See docs/architecture/PHASE_2A_KNOWN_LIMITATIONS.md
# for the long-term direction (structured provenance metadata
# replacing inline markers).
SYSTEMATIC_DRIFT_PCT = 10.0
SYSTEMATIC_DRIFT_FLOOR = 5


class MarkerDriftError(RuntimeError):
    """Raised when an Anthropic chunk response shows systematic marker drift.

    Per Step E follow-up: a marker drop above the systematic-drift
    threshold means the model is not honoring the marker preservation
    rule for the chunk. Failing the run loudly is preferable to
    shipping a transcript with widespread silent un-highlighting; the
    scopist's review surface is the load-bearing feature.

    "Systematic" means the input had at least ``SYSTEMATIC_DRIFT_FLOOR``
    markers AND more than ``SYSTEMATIC_DRIFT_PCT`` percent were dropped.
    Below either condition, drift is logged as a quality signal and
    the pipeline continues — the small-sample stats are too noisy to
    fail on.

    Carries the per-chunk stats dict on the exception for logging.
    """

    def __init__(self, message: str, *, stats: dict[str, int]) -> None:
        super().__init__(message)
        self.stats = stats


def validate_marker_round_trip(
    input_text: str,
    output_text: str,
    *,
    raise_threshold_pct: float = SYSTEMATIC_DRIFT_PCT,
    raise_floor: int = SYSTEMATIC_DRIFT_FLOOR,
) -> dict[str, int]:
    """Compare marker counts before and after the Anthropic round-trip.

    Returns a stats dict with:
      - ``input_count``: markers in the text sent to the model.
      - ``output_count``: markers in the model's response.
      - ``dropped``: input_count - output_count (clamped at zero).

    Drift handling:
      - When ``input_count >= raise_floor`` AND ``dropped / input_count``
        exceeds ``raise_threshold_pct``, raise ``MarkerDriftError``.
        This catches systematic prompt-instruction failure (the model
        ignoring the marker preservation rule).
      - Otherwise, drift is logged as a warning and the function
        returns normally. Yellow highlights for the dropped tokens
        will be missing; the transcript text itself is still valid.

    The floor (small-sample exemption) tolerates "Claude dropped one
    marker out of two" while still failing on "Claude dropped all
    twenty markers." Per the Step E follow-up policy decision.
    """
    input_count = count_markers(input_text)
    output_count = count_markers(output_text)
    dropped = max(0, input_count - output_count)
    stats = {
        "input_count": input_count,
        "output_count": output_count,
        "dropped": dropped,
    }
    if not dropped:
        return stats

    drop_pct = (dropped / input_count) * 100 if input_count else 0.0
    is_systematic = (
        input_count >= raise_floor and drop_pct > raise_threshold_pct
    )
    if is_systematic:
        raise MarkerDriftError(
            f"Systematic marker drift in Anthropic response: dropped "
            f"{dropped} of {input_count} markers ({drop_pct:.1f}%). "
            f"Threshold is >{raise_threshold_pct}% drop when input has "
            f">= {raise_floor} markers. Cleanup pass is not honoring "
            f"the marker preservation rule for this chunk.",
            stats=stats,
        )
    logger.warning(
        "[low_confidence_markers] Anthropic dropped %d of %d markers "
        "in cleanup round-trip (kept %d, %.1f%% drop). Yellow highlights "
        "will be missing for the dropped tokens. Below systematic-drift "
        "threshold (>%.1f%% with input >= %d).",
        dropped,
        input_count,
        output_count,
        drop_pct,
        raise_threshold_pct,
        raise_floor,
    )
    return stats
