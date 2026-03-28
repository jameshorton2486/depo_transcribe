"""
core/docx_formatter.py

Generate a formatted DOCX transcript from corrected plain text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.shared import Inches, Pt


_Q_RE = re.compile(r"^\s*Q\.\s*(.*)$")
_A_RE = re.compile(r"^\s*A\.\s*(.*)$")
_BY_RE = re.compile(r"^\s*(BY\s+.+:)\s*$", re.IGNORECASE)
_EXAM_RE = re.compile(r"^\s*([A-Z-]*EXAMINATION)\s*$", re.IGNORECASE)
_SP_RE = re.compile(r"^\s*([^:]+):\s*(.*)$")


def _set_run_font(run, bold: bool = False) -> None:
    run.font.name = "Times New Roman"
    run.font.size = Pt(12)
    run.font.bold = bold


def _make_paragraph(doc: Document, align=WD_ALIGN_PARAGRAPH.LEFT):
    para = doc.add_paragraph()
    para.alignment = align
    pf = para.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    stops = para.paragraph_format.tab_stops
    for pos in (0.25, 0.5, 0.75, 1.0):
        stops.add_tab_stop(Inches(pos))
    return para


def _normalize_speaker_label(label: str) -> str:
    label = (label or "").strip().upper()
    if re.fullmatch(r"SPEAKER\s+\d+", label):
        return "SPEAKER"
    return label


def _write_q_or_a(doc: Document, prefix: str, text: str) -> None:
    para = _make_paragraph(doc)
    run = para.add_run("\t")
    _set_run_font(run)
    run = para.add_run(prefix)
    _set_run_font(run, bold=True)
    run = para.add_run(".")
    _set_run_font(run, bold=True)
    run = para.add_run(" " + text.strip())
    _set_run_font(run)


def _write_speaker(doc: Document, label: str, text: str) -> None:
    para = _make_paragraph(doc)
    run = para.add_run("\t\t\t")
    _set_run_font(run)
    run = para.add_run(_normalize_speaker_label(label))
    _set_run_font(run, bold=True)
    run = para.add_run(":  ")
    _set_run_font(run, bold=True)
    run = para.add_run(text.strip())
    _set_run_font(run)


def _write_parenthetical(doc: Document, text: str) -> None:
    para = _make_paragraph(doc)
    run = para.add_run("\t\t\t\t" + text.strip())
    _set_run_font(run)


def _write_header(doc: Document, text: str) -> None:
    _make_paragraph(doc)
    para = _make_paragraph(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
    run = para.add_run(text.strip().upper())
    _set_run_font(run, bold=True)
    _make_paragraph(doc)


def _write_by_line(doc: Document, text: str) -> None:
    para = _make_paragraph(doc)
    run = para.add_run(text.strip().upper())
    _set_run_font(run, bold=True)


def _write_plain(doc: Document, text: str) -> None:
    para = _make_paragraph(doc)
    run = para.add_run(text.strip())
    _set_run_font(run)


def _format_line(doc: Document, line: str) -> None:
    stripped = (line or "").rstrip()
    if not stripped:
        return

    if match := _Q_RE.match(stripped):
        _write_q_or_a(doc, "Q", match.group(1))
        return

    if match := _A_RE.match(stripped):
        _write_q_or_a(doc, "A", match.group(1))
        return

    if _EXAM_RE.match(stripped):
        _write_header(doc, stripped)
        return

    if match := _BY_RE.match(stripped):
        _write_by_line(doc, match.group(1))
        return

    if stripped.startswith("(") and stripped.endswith(")"):
        _write_parenthetical(doc, stripped)
        return

    if match := _SP_RE.match(stripped):
        _write_speaker(doc, match.group(1), match.group(2))
        return

    _write_plain(doc, stripped)


def build_output_docx_path(source_path: str) -> str:
    path = Path(source_path)
    stem = path.stem
    if stem.endswith("_corrected"):
        stem = stem[:-len("_corrected")]
    return str(path.with_name(f"{stem}_formatted.docx"))


def format_transcript_to_docx(
    source_path: str,
    output_path: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Convert a corrected transcript text file into a formatted DOCX.
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

    doc = Document()
    section = doc.sections[0]
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1.0)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)

    for line in text.splitlines():
        _format_line(doc, line)

    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(target)
    log(f"Saved DOCX: {target.name}")
    return str(target)
