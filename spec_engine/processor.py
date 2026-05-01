"""Coordinator for deterministic transcript structure enforcement."""

from __future__ import annotations

from .block_builder import build_blocks
from .classifier import classify_blocks
from .corrections import apply_corrections
from .emitter import emit_blocks
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
    return emit_blocks(mapped)


def process_alt(alt: dict) -> str:
    """Build transcript blocks from alt, then run deterministic enforcement."""
    return process_blocks(
        build_blocks(alt),
        confirmed_spellings=alt.get("confirmed_spellings"),
        keyterms=alt.get("keyterms") or alt.get("deepgram_keyterms"),
    )
