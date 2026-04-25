"""
core/docx_formatter.py

Thin adapter for DOCX export using the spec_engine formatting pipeline.

-----------------------------------------------------------------------
ARCHITECTURE ROLE
-----------------------------------------------------------------------

This module is NOT responsible for formatting.

All formatting logic (tabs, spacing, paragraph structure, line types)
is owned exclusively by:

    spec_engine.emitter

This file exists only to:

    1. Accept a transcript text file (post-correction)
    2. Parse it into structured line types
    3. Delegate document construction to spec_engine
    4. Save the resulting DOCX file

-----------------------------------------------------------------------
PIPELINE FLOW
-----------------------------------------------------------------------

    Transcript Text (.txt)
        ↓
    Parse into LineTypes
        ↓
    spec_engine.document_builder
        ↓
    spec_engine.emitter (FORMATTING LAYER)
        ↓
    DOCX output

-----------------------------------------------------------------------
IMPORTANT CONSTRAINTS
-----------------------------------------------------------------------

DO NOT:
- Add formatting logic here
- Define tab stops
- Insert spaces/tabs manually
- Modify paragraph styling

DO:
- Keep this as a minimal wrapper
- Delegate ALL layout decisions to spec_engine

-----------------------------------------------------------------------
WHY THIS MATTERS
-----------------------------------------------------------------------

Maintaining a single formatting authority prevents:

- alignment drift in Word
- inconsistent transcript rendering
- duplication of formatting logic
- difficult-to-debug visual issues

This ensures deterministic, production-grade output.

-----------------------------------------------------------------------
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable

from docx import Document

from spec_engine.emitter import create_document, emit_line
from spec_engine.models import LineType


_Q_RE = re.compile(r"^\s*Q\.\s*(.*)$")
_A_RE = re.compile(r"^\s*A\.\s*(.*)$")
_BY_RE = re.compile(r"^\s*(BY\s+.+:)\s*$", re.IGNORECASE)
_EXAM_RE = re.compile(r"^\s*([A-Z-]*EXAMINATION)\s*$", re.IGNORECASE)
_SP_RE = re.compile(r"^\s*([^:]+):\s*(.*)$")
# Label content must be uppercase letters / digits / limited punctuation.
# Used to reject internal colons (e.g. "At 4:30 PM ...") from being parsed
# as speaker-label lines.
_SP_LABEL_OK_RE = re.compile(r"^[A-Z][A-Z0-9 .'\-]*$")
_SP_CONT_PREFIX = "\t\t\t"


def _iter_formatted_lines(text: str) -> Iterable[tuple[LineType, str]]:
    for raw_line in text.splitlines():
        stripped = (raw_line or "").rstrip()
        if not stripped:
            continue

        if match := _Q_RE.match(stripped):
            yield LineType.Q, match.group(1)
            continue

        if match := _A_RE.match(stripped):
            yield LineType.A, match.group(1)
            continue

        if _EXAM_RE.match(stripped):
            yield LineType.HEADER, stripped.upper()
            continue

        if match := _BY_RE.match(stripped):
            yield LineType.BY, match.group(1).upper()
            continue

        if stripped.startswith("(") and stripped.endswith(")"):
            yield LineType.PN, stripped
            continue

        if stripped.startswith("[SCOPIST:"):
            yield LineType.FLAG, stripped
            continue

        if match := _SP_RE.match(stripped):
            label_candidate = match.group(1).strip()
            # Only treat as a labeled speaker line if the pre-colon text
            # actually looks like an uppercase speaker label. This keeps a
            # continuation line like "\t\t\tAt 4:30 PM we started." from
            # being misparsed as label "At 4", content "30 PM we started."
            if _SP_LABEL_OK_RE.fullmatch(label_candidate):
                yield LineType.SP, f"{label_candidate}:  {match.group(2).strip()}"
                continue

        # SP continuation: emit_blocks writes "\t\t\t{text}" (three tabs, no
        # label, no colon) when consecutive blocks share a speaker. Route
        # those to emit_sp_line so the three-tab indent is preserved in the
        # DOCX output rather than being stripped by the PLAIN path.
        if raw_line.startswith(_SP_CONT_PREFIX):
            yield LineType.SP, raw_line[len(_SP_CONT_PREFIX):].rstrip()
            continue

        yield LineType.PLAIN, stripped


def build_docx_from_transcript_text(text: str) -> Document:
    doc = create_document()
    for line_type, line_text in _iter_formatted_lines(text):
        emit_line(doc, line_type, line_text)
    return doc


def save_document(doc: Document, output_path: str | Path) -> str:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(target)
    return str(target)


def build_output_docx_path(source_path: str) -> str:
    path = Path(source_path)
    stem = path.stem
    if stem.endswith("_corrected"):
        stem = stem[:-len("_corrected")]
    return str(path.with_name(f"{stem}_formatted.docx"))


def build_full_output_docx_path(source_path: str) -> str:
    path = Path(source_path)
    stem = path.stem
    if stem.endswith("_corrected"):
        stem = stem[:-len("_corrected")]
    return str(path.with_name(f"{stem}_full.docx"))


def build_full_docx_from_text(
    text: str,
    job_config,
) -> Document:
    """
    Compose a full deposition Document with title page, caption,
    witness-intro lines, transcript body, and certificate of reporter.

    This is the "Full DOCX" path. The shallow build_docx_from_transcript_text
    path renders just the body and is what the existing Generate DOCX button
    produces. The full path here matches what spec_engine.document_builder.
    process_transcript produces, but starts from corrected.txt + job_config
    instead of a Deepgram-output DOCX, so it can be invoked from the
    Corrections tab without an upstream DOCX intermediate.

    Page writers (write_title_page, write_caption, write_certificate) are
    the same functions process_transcript calls — same output for the
    formal pages.
    """
    # Imports are local so this module doesn't pull spec_engine.pages
    # transitively when only the shallow path is used.
    from spec_engine.document_builder import _build_witness_intro_lines
    from spec_engine.emitter import add_page_break, create_document, emit_line
    from spec_engine.pages.caption import write_caption
    from spec_engine.pages.certificate import write_certificate
    from spec_engine.pages.title_page import write_title_page

    doc = create_document()

    # Page 1: Title page (caption + cause + parties + court block)
    write_title_page(doc, job_config)
    add_page_break(doc)

    # Page 2: Appearances / caption
    write_caption(doc, job_config)
    add_page_break(doc)

    # Witness intro: "{WITNESS}, having been first duly sworn, …"
    # plus the EXAMINATION header and BY MR./MS. line. Skipped only when
    # the body already contains an EXAMINATION header (audio-driven path).
    body_lines = list(_iter_formatted_lines(text))
    intro = _build_witness_intro_lines(job_config, body_lines)
    for line_type, line_text in intro:
        emit_line(doc, line_type, line_text)

    # Body
    for line_type, line_text in body_lines:
        emit_line(doc, line_type, line_text)

    # Final page: Reporter's Certificate
    add_page_break(doc)
    write_certificate(doc, job_config)

    return doc


def format_full_transcript_to_docx(
    source_path: str,
    job_config,
    output_path: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Convert a corrected transcript (.txt) plus its JobConfig into a
    deposition-ready DOCX with title page, caption, witness intro,
    body, and reporter's certificate.

    Counterpart to format_transcript_to_docx. The shallow function
    renders the body only; this function renders the full document.
    """

    def log(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Transcript not found: {source_path}")

    target = Path(output_path or build_full_output_docx_path(source_path))
    log(f"Reading transcript: {source.name}")
    text = source.read_text(encoding="utf-8")

    log("Building full DOCX (title page → body → certificate)…")
    doc = build_full_docx_from_text(text, job_config)
    saved_path = save_document(doc, target)
    log(f"Saved full DOCX: {Path(saved_path).name}")
    return saved_path


def format_transcript_to_docx(
    source_path: str,
    output_path: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Convert a corrected transcript text file into a DOCX document.

    This function acts as a thin adapter over the spec_engine formatting
    pipeline. It does NOT apply any formatting directly.

    Formatting responsibilities are handled entirely by:

        spec_engine.emitter

    Parameters
    ----------
    source_path : str
        Path to the corrected transcript (.txt)

    output_path : str | None
        Optional target path for DOCX output

    progress_callback : Callable[[str], None] | None
        Optional callback for UI progress updates

    Returns
    -------
    str
        Path to the saved DOCX file

    Raises
    ------
    FileNotFoundError
        If the source transcript does not exist

    Notes
    -----
    - Output formatting strictly follows spec_engine rules
    - No manual formatting is applied in this module
    """

    def log(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Transcript not found: {source_path}")

    target = Path(output_path or build_output_docx_path(source_path))
    log(f"Reading transcript: {source.name}")
    text = source.read_text(encoding="utf-8")

    doc = build_docx_from_transcript_text(text)
    saved_path = save_document(doc, target)
    log(f"Saved DOCX: {Path(saved_path).name}")
    return saved_path
