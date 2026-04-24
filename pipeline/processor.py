"""
Compatibility wrapper for block-based transcript processing.

The desktop app's live correction path runs through `core/correction_runner.py`.
This module remains for tests and external callers that need a compact
Deepgram-JSON -> blocks/text helper.

Behavior is intentionally narrow:
    build_blocks_from_deepgram -> process_blocks -> format_blocks_to_text

Legacy `apply_ai` and `ai_rules` arguments are accepted for compatibility only.
They do not change behavior in this module.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict

from spec_engine.block_builder import build_blocks_from_deepgram
from spec_engine.processor import process_blocks
from core.correction_runner import format_blocks_to_text


def _warn_if_legacy_ai_args_used(apply_ai: bool, ai_rules: Any) -> None:
    if not apply_ai and ai_rules is None:
        return

    warnings.warn(
        "pipeline.processor.run_pipeline() ignores legacy apply_ai/ai_rules "
        "arguments. AI correction is handled outside this compatibility wrapper.",
        DeprecationWarning,
        stacklevel=2,
    )


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
        apply_ai:       Legacy compatibility flag. Ignored.
        ai_rules:       Legacy compatibility placeholder. Ignored.

    Returns:
        { "blocks": List[Block], "text": str }
    """
    _warn_if_legacy_ai_args_used(apply_ai, ai_rules)

    blocks = build_blocks_from_deepgram(deepgram_json)
    blocks = process_blocks(blocks, job_config)

    output = format_blocks_to_text(blocks)
    return {"blocks": blocks, "text": output}
