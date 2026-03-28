"""
Block-first transcription pipeline controller.
"""

from __future__ import annotations

from typing import Any, Dict

from pipeline.block_builder import build_blocks_from_deepgram
from spec_engine.processor import process_blocks


def run_pipeline(
    deepgram_json: Dict[str, Any],
    job_config: Any,
    apply_ai: bool = False,
    ai_rules: Any = None,
) -> Dict[str, Any]:
    """
    Run the block-based transcript pipeline and return both blocks and text.
    """
    blocks = build_blocks_from_deepgram(deepgram_json)
    blocks = process_blocks(blocks, job_config)
    if apply_ai:
        from ai_engine.review import run_ai_review_blocks
        blocks = run_ai_review_blocks(blocks, rules=ai_rules)
    from formatter import format_blocks
    output = format_blocks(blocks)
    return {"blocks": blocks, "text": output}
