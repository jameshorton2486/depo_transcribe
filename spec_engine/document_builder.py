"""
document_builder.py

Full pipeline orchestrator (Spec Section 9.2).
Runs all 8 steps: parse → load_config → clean → classify → emit →
corrections_log → caption → certificate.

Also handles:
  - Speaker verification guard (Spec 9.5)
  - pickle block caching for re-processing (Spec 9.1)
  - Post-record retroactive spelling corrections (Spec Section 8)
  - Q/A pair page-break safety (Spec 5.5)
"""

import pickle
from pathlib import Path
from typing import Any, Callable, List, Optional

import re

from app_logging import get_logger

from .classifier import ClassifierState, classify_block, fix_trailing_okay_in_answer
from .corrections import clean_block
from .emitter import (
    QAPairTracker, LineNumberTracker,
    add_page_break, create_document, emit_line, emit_line_numbered,
)
from .models import (
    Block, CorrectionRecord, JobConfig, LineType, ScopistFlag,
    SpeakerMapUnverifiedError,
)
from .pages.caption import write_caption
from .pages.cert_exhibits import write_cert_exhibits
from .pages.certificate import write_certificate
from .pages.changes_signature import write_changes_signature
# corrections_log is intentionally excluded from DOCX output (Miah preference)
# Corrections summary is printed to the run logger only — not included in cert output
# from .pages.corrections_log import write_corrections_log
from .pages.exhibit_index import write_exhibit_index
from .pages.post_record import apply_retroactive_corrections, write_post_record_section
from .pages.title_page import write_title_page
from .pages.witness_index import write_witness_index
from .parser import parse_blocks, show_speaker_preview
from .speaker_mapper import map_speakers
from .speaker_resolver import normalize_speaker_id
from .validator import ValidationResult

LOGGER = get_logger(__name__)


def _cache_path(job_config: JobConfig) -> str:
    """Return cache file path for parsed blocks (Spec 9.1 — pickle caching)."""
    safe = job_config.cause_number.replace("/", "-").replace("\\", "-") or "unnamed"
    return str(Path("jobs") / f"{safe}_blocks.pkl")


def cache_blocks(blocks: List[Block], job_config: JobConfig) -> str:
    """Save parsed blocks to disk. Returns cache path."""
    path = _cache_path(job_config)
    Path("jobs").mkdir(exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(blocks, f)
    return path


def load_cached_blocks(job_config: JobConfig) -> Optional[List[Block]]:
    """Load previously cached blocks. Returns None if not found or stale."""
    path = _cache_path(job_config)
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return None
    except pickle.UnpicklingError as exc:
        LOGGER.warning("Cached blocks corrupted, re-processing: %s", exc)
        return None
    except Exception as exc:
        LOGGER.error(
            "Unexpected error loading cached blocks path=%s error=%s",
            path, exc, exc_info=True,
        )
        return None


def _get_examiner_label(job_config: JobConfig) -> str:
    speaker_map = getattr(job_config, "speaker_map", {}) or {}
    label = speaker_map.get(job_config.examining_attorney_id, "COUNSEL")
    return (label or "COUNSEL").strip().upper().rstrip(":")


def _build_witness_intro_lines(
    job_config: JobConfig,
    existing_lines: Optional[List[tuple[LineType, str]]] = None,
) -> List[tuple[LineType, str]]:
    """
    Build the fixed witness introduction block from case metadata.

    Guard against duplicating the EXAMINATION/BY header pair if the body
    already contains them from the audio-driven oath sequence.
    """
    existing_lines = existing_lines or []
    if any(
        line_type == LineType.HEADER and "EXAMINATION" in (text or "").upper()
        for line_type, text in existing_lines
    ):
        return []

    witness_name = (job_config.witness_name or "WITNESS").strip().upper()
    examiner_label = _get_examiner_label(job_config)
    return [
        (LineType.HEADER, f"{witness_name},"),
        (LineType.PLAIN, "having been first duly sworn, testified as follows:"),
        (LineType.HEADER, "EXAMINATION"),
        (LineType.BY, f"BY {examiner_label}:"),
    ]


def process_transcript(
    input_docx_path: str,
    output_docx_path: str,
    job_config: Optional[JobConfig] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    use_cache: bool = False,
    dry_run: bool = False,
    clean_delivery: bool = False,
    run_logger: Any = None,
) -> dict:
    """
    Full 8-step pipeline: Deepgram DOCX → formatted Texas UFM legal transcript DOCX.

    Args:
        input_docx_path:   Path to Deepgram output .docx
        output_docx_path:  Path for formatted output .docx
        job_config:        Per-job config. Uses defaults if None.
        progress_callback: Optional callable(str) for status messages.
        use_cache:         If True, load cached blocks instead of re-parsing.
        dry_run:           If True, return stats dict without saving any file.

    Returns:
        dict with: output_path, block_count, correction_count, flag_count,
                   post_record_count, speaker_preview (str)

    Raises:
        SpeakerMapUnverifiedError: If speaker_map is empty and not verified.
    """
    def log(msg: str):
        if progress_callback:
            progress_callback(msg)

    if job_config is None:
        job_config = JobConfig()

    # ── Guard: speaker map must be verified (Spec 9.5) ───────────────────────
    if not job_config.speaker_map_verified:
        raise SpeakerMapUnverifiedError(
            "Speaker map has not been verified.\n"
            "Use the Speaker Verification dialog to assign roles before processing."
        )

    # ── Step 1: Parse blocks ──────────────────────────────────────────────────
    log("Step 1: Parsing Deepgram output...")
    if use_cache:
        blocks = load_cached_blocks(job_config)
        if blocks:
            log(f"  Loaded {len(blocks)} blocks from cache")
        else:
            log("  Cache miss — parsing from DOCX")
            blocks = parse_blocks(input_docx_path)
    else:
        blocks = parse_blocks(input_docx_path)

    original_block_text = "\n".join((block.text or "") for block in blocks)

    if run_logger:
        run_logger.snapshot("01_docbuilder_blocks_raw", blocks)
        run_logger.log_step("Deepgram parse complete", block_count=len(blocks))

    for block in blocks:
        try:
            block.speaker_id = normalize_speaker_id(block.speaker_id)
        except ValueError:
            pass

    log(f"  Parsed {len(blocks)} speaker blocks")
    preview = show_speaker_preview(blocks)
    log(preview)

    if not dry_run:
        cache_blocks(blocks, job_config)
        log(f"  Blocks cached to {_cache_path(job_config)}")

    # ── Steps 3-5: Clean, classify, emit ─────────────────────────────────────
    blocks = map_speakers(blocks, job_config)
    log(f"  Speaker roles mapped ({len(blocks)} blocks)")
    if run_logger:
        run_logger.snapshot("02_docbuilder_blocks_mapped", blocks)
        run_logger.log_step("Speaker mapping complete", block_count=len(blocks))
    log("Step 2: Cleaning, classifying, and emitting...")

    all_corrections: List[CorrectionRecord] = []
    state = ClassifierState()
    flag_counter = [0]  # Mutable for passing into clean_block
    qa_tracker = QAPairTracker()
    line_tracker = LineNumberTracker(start_page=6)
    use_line_numbers = True   # Set False to disable line numbering

    # Build transcript body in a single Document (Bug 2 fix — no cross-doc XML)
    doc = create_document()

    # Page 1 placeholder — write corrections log AFTER processing (need all corrections)
    # Page 2 placeholder — write caption AFTER processing
    # We build the full body, then prepend pages 1 and 2 using a second Document trick:
    # Actually: write to doc in order. Use a temporary body_paragraphs list approach.
    # Build body in doc first, then insert page 1 + 2 at the front via XML manipulation.

    # Simpler correct approach: build pages in order using ONE doc.
    # Step 1-5 output goes to a list of (line_type, text) tuples first,
    # then we write the whole doc in one pass.

    body_lines: List[tuple] = []   # (LineType, text)

    for i, block in enumerate(blocks):
        # Step 3: Clean
        result = clean_block(
            block.text,
            job_config,
            block_index=i,
            flags=state.flags,
            flag_counter=flag_counter,
        )
        cleaned_text = result[0]
        corrections = result[1]
        block.text = cleaned_text
        all_corrections.extend(corrections)
        if run_logger:
            for record in corrections:
                run_logger.log_correction(
                    block_index=getattr(record, "block_index", i),
                    original=getattr(record, "original", ""),
                    corrected=getattr(record, "corrected", ""),
                    rule=getattr(record, "pattern", ""),
                )

        # Step 4: Classify
        line_results = classify_block(block, job_config, state, block_index=i)

        # Collect body lines
        for line_type, text in line_results:
            body_lines.append((line_type, text))

        # Emit inline flags once per block — after all lines from this block
        for flag in state.flags:
            if flag.block_index == i and flag.inline_text:
                # Check not already emitted (prevent duplicate on re-entry)
                flag_line = (LineType.FLAG, flag.inline_text)
                if flag_line not in body_lines[-3:]:  # simple recency check
                    body_lines.append(flag_line)

    body_lines = fix_trailing_okay_in_answer(body_lines)

    if run_logger:
        emitted_text = "\n".join(text for _, text in body_lines)
        run_logger.write_diff(original_block_text, emitted_text)
        run_logger.write_validation(ValidationResult())
        run_logger.log_step(
            "Body generation complete",
            corrections=len(all_corrections),
            flags=len(state.flags),
            post_record=len(state.post_record_spellings),
        )

    # Update job_config with post-record spellings found during classification
    job_config.post_record_spellings = state.post_record_spellings

    log(f"  Applied {len(all_corrections)} corrections")
    log(f"  Generated {len(state.flags)} scopist flags")
    log(f"  Found {len(state.post_record_spellings)} post-record spellings")

    if dry_run:
        return {
            "output_path": None,
            "block_count": len(blocks),
            "correction_count": len(all_corrections),
            "flag_count": len(state.flags),
            "flags": list(state.flags),
            "post_record_count": len(state.post_record_spellings),
            "speaker_preview": preview,
        }

    # ── Build final document in correct page order ────────────────────────────
    log("Step 3: Building final document...")

    # Merge confirmed post-record spellings into confirmed_spellings
    # so Page 1 corrections log reflects them
    for prs in state.post_record_spellings:
        if prs.correct_spelling and prs.correct_spelling != prs.name:
            job_config.confirmed_spellings[prs.name] = prs.correct_spelling
    job_config.spec_flags = list(state.flags)

    # Log corrections summary to console (not written to DOCX)
    log(f"  Corrections applied: {len(all_corrections)}")
    log(f"  Scopist flags:       {len(state.flags)}")
    if all_corrections:
        from collections import Counter
        pattern_counts = Counter(r.pattern for r in all_corrections if hasattr(r, 'pattern'))
        for pattern, count in pattern_counts.most_common(5):
            log(f"    {pattern}: {count}×")

    # Page 1: Title Page (UFM Fig03)
    write_title_page(doc, job_config)
    add_page_break(doc)

    # Corrections Log: intentionally excluded from DOCX (Miah preference).
    # Corrections summary is available in the run logger and _corrections.json.
    # Transcript body begins immediately after the title page.

    # Caption / Appearances (UFM Fig04)
    write_caption(doc, job_config)
    add_page_break(doc)

    # Page 4: Witness + Exhibit Index (UFM Section 11)
    write_witness_index(doc, job_config)
    add_page_break(doc)
    write_exhibit_index(doc, job_config)
    add_page_break(doc)

    # Pages 3+: Transcript body
    transcript_lines = _build_witness_intro_lines(job_config, body_lines) + body_lines
    for line_type, text in transcript_lines:
        if use_line_numbers:
            emit_line_numbered(doc, line_type, text, line_tracker, qa_tracker)
        else:
            emit_line(doc, line_type, text)

    # Post-record spellings section (Spec Section 8)
    if state.post_record_spellings:
        write_post_record_section(doc, state.post_record_spellings, job_config)

    # Changes & Signature page (UFM Fig07 / Fig07A)
    add_page_break(doc)
    write_changes_signature(doc, job_config)

    # Final page: Reporter's Certificate (UFM Fig05)
    add_page_break(doc)
    write_certificate(doc, job_config)

    # Exhibit Certification (UFM Fig06) — only if exhibits exist
    if job_config.exhibits:
        add_page_break(doc)
        write_cert_exhibits(doc, job_config)

    if clean_delivery:
        scopist_re = re.compile(r'\[SCOPIST:.*?\]', re.DOTALL)
        for para in doc.paragraphs:
            if '[SCOPIST:' in para.text:
                for run in para.runs:
                    run.text = scopist_re.sub('', run.text)

    # ── Save ──────────────────────────────────────────────────────────────────
    Path(output_docx_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_docx_path)
    log(f"  Saved: {output_docx_path}")

    # ── Post-record retroactive corrections (Spec Section 8) ──────────────────
    if state.post_record_spellings:
        log("Step 4: Applying retroactive post-record spelling corrections...")
        retro_corrections = apply_retroactive_corrections(
            output_docx_path, state.post_record_spellings, job_config
        )
        log(f"  Retroactive corrections applied: {len(retro_corrections)}")

    # ── Save job config for reuse ─────────────────────────────────────────────
    saved_job_path = job_config.save()
    log(f"  Job config saved: {saved_job_path}")

    log("Processing complete.")

    return {
        "output_path": output_docx_path,
        "block_count": len(blocks),
        "correction_count": len(all_corrections),
        "flag_count": len(state.flags),
        "flags": list(state.flags),
        "post_record_count": len(state.post_record_spellings),
        "speaker_preview": preview,
    }
