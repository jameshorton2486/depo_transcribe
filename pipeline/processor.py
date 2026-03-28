"""
pipeline/processor.py

Block-first transcription pipeline controller.

Connects Deepgram JSON output to the spec_engine block processing pipeline.
The active correction path is:
    build_blocks_from_deepgram  →  process_blocks  →  format_blocks_to_text

The run_pipeline() function is the public API for external callers.
AI-assisted correction is reserved for a future phase; the apply_ai flag
is accepted but silently ignored until that module is built.
"""

from __future__ import annotations

from typing import Any, Dict

from pipeline.block_builder import build_blocks_from_deepgram
from spec_engine.processor import process_blocks
from core.correction_runner import format_blocks_to_text


def run_pipeline(
    deepgram_json: Dict[str, Any],
    job_config: Any,
    apply_ai: bool = False,
    ai_rules: Any = None,
) -> Dict[str, Any]:
    """
    Run the block-based transcript pipeline and return both blocks and text.

    Args:
        deepgram_json:  Assembled Deepgram result dict with 'utterances' key.
        job_config:     JobConfig instance or dict with confirmed_spellings etc.
        apply_ai:       Reserved for future AI correction pass — ignored for now.
        ai_rules:       Reserved for future use — ignored for now.

    Returns:
        { "blocks": List[Block], "text": str }
    """
    blocks = build_blocks_from_deepgram(deepgram_json)
    blocks = process_blocks(blocks, job_config)

    # apply_ai is reserved for Phase 2 — AI-assisted proper noun correction.
    # When that module is built, it will be wired here.
    if apply_ai:
        import logging
        logging.getLogger(__name__).warning(
            "run_pipeline: apply_ai=True but AI correction module is not "
            "yet implemented. Continuing with deterministic corrections only."
        )

    output = format_blocks_to_text(blocks)
    return {"blocks": blocks, "text": output}
