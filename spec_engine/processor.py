"""Coordinator for deterministic transcript structure enforcement."""

from __future__ import annotations

from .age_and_time import normalize_ages_and_times
from .block_builder import build_blocks
from .byline_resumption import apply_byline_resumption
from .classifier import classify_blocks
from .corrections import apply_corrections
from .date_normalization import normalize_dates_and_years
from .emitter import emit_blocks
from .exhibit_markers import emit_exhibit_markers
from .money_and_percent import normalize_money_and_percent
from .objection_routing import split_misattributed_objections
from .qa_fixer import enforce_structure
from .speaker_mapper import normalize_speakers


def process_blocks(
    blocks: list[dict],
    *,
    confirmed_spellings: dict | None = None,
    keyterms: list[str] | None = None,
) -> str:
    """Apply deterministic transcript enforcement in fixed stage order."""
    classified = classify_blocks(blocks)
    corrected = apply_corrections(
        classified,
        confirmed_spellings=confirmed_spellings,
        keyterms=keyterms,
    )
    fixed = enforce_structure(corrected)
    mapped = normalize_speakers(fixed)
    annotated = emit_exhibit_markers(mapped)
    annotated = split_misattributed_objections(annotated)
    annotated = apply_byline_resumption(annotated)
    annotated = normalize_dates_and_years(annotated)
    annotated = normalize_money_and_percent(annotated)
    annotated = normalize_ages_and_times(annotated)
    return emit_blocks(annotated)


def process_alt(alt: dict) -> str:
    """Build transcript blocks from alt, then run deterministic enforcement."""
    return process_blocks(
        build_blocks(alt),
        confirmed_spellings=alt.get("confirmed_spellings"),
        keyterms=alt.get("keyterms") or alt.get("deepgram_keyterms"),
    )
