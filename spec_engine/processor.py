"""
Block-based spec-engine controller.

This is the primary place where block intelligence is orchestrated.
"""

from __future__ import annotations

import copy
from typing import Any, List

from .classifier import classify_blocks
from .corrections import apply_corrections
from .deepgram_patterns import apply_deepgram_patterns
from .flag_rules import generate_scopist_flags
from .models import Block
from .nod_corrections import apply_nod_corrections
from .objections import extract_objections
from .paragraph_splitter import split_block_text
from .preamble_rules import apply_preamble_rules
from .word_speaker_splitter import split_mixed_speaker_utterances
from .qa_fixer import fix_qa_structure
from .speaker_mapper import map_speakers
from .speaker_intelligence import enforce_qa_sequence, infer_speaker_roles
from .validator import validate_blocks


def split_blocks_into_paragraphs(blocks: List[Block]) -> List[Block]:
    new_blocks: list[Block] = []
    splittable_types = {"Q", "A", "SPEAKER", "COLLOQUY", "SP"}

    for block in blocks:
        if not getattr(block, "text", ""):
            new_blocks.append(block)
            continue

        if getattr(block, "meta", {}).get("merged_reporter_preamble"):
            new_blocks.append(block)
            continue

        block_type = getattr(getattr(block, "block_type", None), "value", getattr(block, "block_type", None))
        if block_type not in splittable_types:
            new_blocks.append(block)
            continue

        segments = split_block_text(block.text)
        if len(segments) == 1:
            new_blocks.append(block)
            continue

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            new_block = copy.deepcopy(block)
            new_block.text = segment
            new_blocks.append(new_block)

    return new_blocks


def process_blocks(
    blocks: List[Block],
    job_config: Any,
    run_logger: Any = None,
) -> List[Block]:
    """
    Apply the agreed block-based processing order.
    If run_logger is provided, snapshots and validation are logged per run.
    """
    for block in blocks:
        if not hasattr(block, "speaker_id"):
            raise RuntimeError("Block missing speaker_id; utterance pipeline broken.")

    _log = run_logger

    if _log:
        _log.snapshot("01_blocks_raw", blocks)
        _log.log_step("Starting corrections", block_count=len(blocks))

    blocks = apply_corrections(blocks, job_config)
    blocks = apply_deepgram_patterns(blocks)
    blocks = apply_nod_corrections(blocks, job_config)
    blocks = apply_preamble_rules(blocks)
    blocks = generate_scopist_flags(blocks)
    blocks = split_mixed_speaker_utterances(blocks)

    if _log:
        _log.snapshot("02_blocks_corrected", blocks)
        _log.log_corrections_from_blocks(blocks)
        _log.log_step("Corrections complete")

    blocks = map_speakers(blocks, job_config)
    blocks = infer_speaker_roles(blocks, job_config)
    blocks = enforce_qa_sequence(blocks, job_config)
    if not all(
        getattr(block, "speaker_role", None) is not None
        and getattr(block, "speaker_name", None) is not None
        for block in blocks
        if getattr(block, "speaker_id", None) is not None
    ):
        raise RuntimeError("Speaker mapping incomplete")

    if _log:
        _log.snapshot("02a_blocks_speaker_mapped", blocks)
        _log.log_step("Speaker mapping complete")

    blocks = classify_blocks(blocks, job_config)
    if not all(getattr(block, "block_type", None) is not None for block in blocks):
        raise RuntimeError("Classification failed")

    if _log:
        _log.snapshot("03a_blocks_classified", blocks)
        q_count = sum(1 for block in blocks if getattr(block.block_type, "value", "") == "Q")
        a_count = sum(1 for block in blocks if getattr(block.block_type, "value", "") == "A")
        _log.log_step("Classification complete", q=q_count, a=a_count)

    blocks = fix_qa_structure(blocks, job_config=job_config)

    if _log:
        _log.snapshot("04a_blocks_qa_fixed", blocks)
        _log.log_step("Q/A structure complete")

    blocks_before_split = list(blocks)
    blocks = split_blocks_into_paragraphs(blocks)

    if _log:
        _log.snapshot("04b_blocks_paragraph_split", blocks)
        _log.log_step(
            "Paragraph split complete",
            original_blocks=len(blocks_before_split),
            new_blocks=len(blocks),
        )

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
