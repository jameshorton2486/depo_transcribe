"""
pipeline/processor.py

Block-first transcription pipeline controller.

STATUS NOTE:
This module is not the authoritative runtime correction entry point for the
desktop app. The live UI flow uses core/correction_runner.py for deterministic
corrections and spec_engine/ai_corrector.py for optional AI correction.

Connects Deepgram JSON output to the spec_engine block processing pipeline.
The active correction path is:
    build_blocks_from_deepgram  →  process_blocks  →  format_blocks_to_text

The run_pipeline() function remains available for external/test callers.
The apply_ai flag is legacy and is still ignored in this module.
"""

from __future__ import annotations

from typing import Any, Dict

from spec_engine.block_builder import build_blocks_from_deepgram
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
        apply_ai:       Legacy flag — ignored in this module.
        ai_rules:       Legacy placeholder — ignored.

    Returns:
        { "blocks": List[Block], "text": str }
    """
    blocks = build_blocks_from_deepgram(deepgram_json)
    blocks = process_blocks(blocks, job_config)

    if apply_ai:
        import logging
        logging.getLogger(__name__).warning(
            "run_pipeline: apply_ai=True but this legacy module does not invoke "
            "spec_engine.ai_corrector. Continuing with deterministic corrections only."
        )

    output = format_blocks_to_text(blocks)
    return {"blocks": blocks, "text": output}
