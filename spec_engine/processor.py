"""
Block-based spec-engine controller.

This is the primary place where block intelligence is orchestrated.
"""

from __future__ import annotations

from typing import Any, List

from .classifier import classify_blocks
from .corrections import apply_corrections
from .models import Block
from .objections import extract_objections
from .qa_fixer import fix_qa_structure
from .speaker_mapper import map_speakers
from .validator import validate_blocks


def process_blocks(
    blocks: List[Block],
    job_config: Any,
    run_logger: Any = None,
) -> List[Block]:
    """
    Apply the agreed block-based processing order.
    If run_logger is provided, snapshots and validation are logged per run.
    """
    _log = run_logger

    if _log:
        _log.snapshot("01_blocks_raw", blocks)
        _log.log_step("Starting corrections", block_count=len(blocks))

    blocks = apply_corrections(blocks, job_config)

    if _log:
        _log.snapshot("02_blocks_corrected", blocks)
        _log.log_corrections_from_blocks(blocks)
        _log.log_step("Corrections complete")

    blocks = map_speakers(blocks, job_config)

    if _log:
        _log.log_step("Speaker mapping complete")

    blocks = classify_blocks(blocks, job_config)

    if _log:
        _log.snapshot("03_blocks_classified", blocks)
        q_count = sum(1 for block in blocks if getattr(block.block_type, "value", "") == "Q")
        a_count = sum(1 for block in blocks if getattr(block.block_type, "value", "") == "A")
        _log.log_step("Classification complete", q=q_count, a=a_count)

    blocks = fix_qa_structure(blocks, job_config=job_config)

    if _log:
        _log.snapshot("04_blocks_qa_fixed", blocks)
        _log.log_step("Q/A structure complete")

    blocks = extract_objections(blocks, job_config)
    blocks = classify_blocks(blocks, job_config)

    if _log:
        _log.snapshot("05_blocks_final", blocks)
        _log.log_step("Final classification complete")

    _speaker_map_verified = bool(
        getattr(job_config, "speaker_map_verified", False)
        if hasattr(job_config, "speaker_map_verified")
        else (job_config.get("speaker_map_verified", False) if isinstance(job_config, dict) else False)
    )
    validation = validate_blocks(
        blocks,
        speaker_map_verified=_speaker_map_verified,
    )

    if _log:
        _log.write_validation(validation)
        _log.log_step(
            "Validation complete",
            errors=len(validation.errors),
            warnings=len(validation.warnings),
        )

    try:
        from config import STRICT_MODE
        if STRICT_MODE and validation.errors:
            error_lines = "\n".join(f"  • {error}" for error in validation.errors[:5])
            raise RuntimeError(
                f"Validation failed ({len(validation.errors)} error(s)) — aborting in STRICT_MODE:\n{error_lines}"
            )
    except ImportError:
        pass

    for warning in validation.warnings:
        for block in blocks[:1]:
            block.meta.setdefault("validation_warnings", []).append(warning)
    if validation.errors:
        for block in blocks[:1]:
            block.meta.setdefault("validation_errors", []).extend(validation.errors)
    return blocks
