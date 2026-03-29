"""
core/docx_formatter.py

Generate a formatted DOCX transcript from corrected plain text.

UFM compliance:
  - Font:         Courier New 12pt (monospaced — required for line count)
  - Q. / A.:      Plain text — NEVER bold (UFM body text rule)
  - Q/A structure: [TAB]Q.[TAB]text — two tabs, no spaces
  - Headers:      No blank lines before or after (UFM prohibits in body)
  - Parentheticals: Navy blue #1E3A5F — not bold
  - Margins:      Left 1.25", Right/Top/Bottom 1.0"
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips


# ── Constants ─────────────────────────────────────────────────────────────────

_FONT = "Courier New"
_SIZE_PT = 12
_NAVY_BLUE = (0x1E, 0x3A, 0x5F)   # parenthetical color per Depo-Pro spec

# Line-type detection patterns
_Q_RE = re.compile(r"^\s*Q\.\s*(.*)$")
_A_RE = re.compile(r"^\s*A\.\s*(.*)$")
_BY_RE = re.compile(r"^\s*(BY\s+.+:)\s*$", re.IGNORECASE)
_EXAM_RE = re.compile(r"^\s*([A-Z-]*EXAMINATION)\s*$", re.IGNORECASE)
_SP_RE = re.compile(r"^\s*([^:]+):\s*(.*)$")


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _add_run(para, text: str, bold: bool = False,
             color_rgb: tuple | None = None) -> None:
    """Add a Courier New 12pt run. Optionally bold or colored."""
    run = para.add_run(text)
    run.bold = bold
    run.font.name = _FONT
    run.font.size = Pt(_SIZE_PT)
    if color_rgb:
        run.font.color.rgb = RGBColor(*color_rgb)
    # Ensure all font slots are set for Word/Google Docs compatibility
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), _FONT)
    rFonts.set(qn("w:hAnsi"), _FONT)
    rFonts.set(qn("w:cs"), _FONT)


def _add_tab_run(para) -> None:
    """Add a tab character as its own Courier New 12pt run."""
    run = para.add_run()
    run.font.name = _FONT
    run.font.size = Pt(_SIZE_PT)
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), _FONT)
    rFonts.set(qn("w:hAnsi"), _FONT)
    rFonts.set(qn("w:cs"), _FONT)
    tab = OxmlElement("w:tab")
    run._r.append(tab)


def _make_paragraph(doc: Document,
                    align=WD_ALIGN_PARAGRAPH.LEFT) -> object:
    """Create a double-spaced, zero-margin paragraph."""
    para = doc.add_paragraph()
    para.alignment = align
    stops = para.paragraph_format.tab_stops
    for twips in (360, 900, 1440, 2160):
        stops.add_tab_stop(Twips(twips))
    pPr = para._p.get_or_add_pPr()
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), "480")
    spacing.set(qn("w:lineRule"), "auto")
    pPr.append(spacing)
    return para


def _normalize_speaker_label(label: str) -> str:
    label = (label or "").strip().upper()
    if re.fullmatch(r"SPEAKER\s+\d+", label):
        return "SPEAKER"
    return label


# ── Paragraph emitters ────────────────────────────────────────────────────────

def _write_q_or_a(doc: Document, prefix: str, text: str) -> None:
    """
    Q/A line — UFM two-tab structure:
      [TAB → 0.25"] Q. [TAB → 0.625"] testimony text

    Q. and A. are PLAIN text — never bold.
    Body text is PLAIN text — never bold.
    """
    para = _make_paragraph(doc)
    _add_tab_run(para)               # tab 1 → Q./A. position
    _add_run(para, f"{prefix}.", bold=False)
    _add_tab_run(para)               # tab 2 → text start
    _add_run(para, "  " + text.strip(), bold=False)


def _write_speaker(doc: Document, label: str, text: str) -> None:
    """
    SP/colloquy line:
      [TAB][TAB][TAB] BOLD_LABEL:  plain text
    """
    para = _make_paragraph(doc)
    _add_tab_run(para)
    _add_tab_run(para)
    _add_tab_run(para)
    _add_run(para, _normalize_speaker_label(label), bold=True)
    _add_run(para, ":  ", bold=True)
    _add_run(para, text.strip(), bold=False)


def _write_parenthetical(doc: Document, text: str) -> None:
    """
    Parenthetical line — navy blue, not bold:
      [TAB][TAB][TAB][TAB] (text)
    """
    para = _make_paragraph(doc)
    _add_tab_run(para)
    _add_tab_run(para)
    _add_tab_run(para)
    _add_tab_run(para)
    _add_run(para, text.strip(), bold=False, color_rgb=_NAVY_BLUE)


def _write_header(doc: Document, text: str) -> None:
    """
    EXAMINATION / CROSS-EXAMINATION header — centered, bold.
    NO blank lines before or after (UFM prohibits blank lines in body).
    """
    para = _make_paragraph(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_run(para, text.strip().upper(), bold=True)


def _write_by_line(doc: Document, text: str) -> None:
    """BY MR. NAME: line — bold, flush left."""
    para = _make_paragraph(doc)
    _add_run(para, text.strip().upper(), bold=True)


def _write_plain(doc: Document, text: str) -> None:
    para = _make_paragraph(doc)
    _add_run(para, text.strip(), bold=False)


# ── Line router ───────────────────────────────────────────────────────────────

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


# ── Public API ────────────────────────────────────────────────────────────────

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
    Convert a corrected transcript text file into a UFM-compliant DOCX.

    Returns the path of the generated file.
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

    # Page geometry — UFM mandated margins
    section = doc.sections[0]
    section.page_width = int(8.5 * 1440)
    section.page_height = int(11.0 * 1440)
    section.left_margin = int(1.25 * 1440)
    section.right_margin = int(1.0 * 1440)
    section.top_margin = int(1.0 * 1440)
    section.bottom_margin = int(1.0 * 1440)

    # Default tab stop: 720 twips (0.5") — Word default
    settings = doc.settings.element
    existing_tab = settings.find(qn("w:defaultTabStop"))
    if existing_tab is not None:
        settings.remove(existing_tab)
    dtab = OxmlElement("w:defaultTabStop")
    dtab.set(qn("w:val"), "720")
    settings.append(dtab)

    # Normal style — Courier New 12pt
    normal = doc.styles["Normal"]
    normal.font.name = _FONT
    normal.font.size = Pt(_SIZE_PT)

    # Remove the default empty paragraph Word always inserts
    for para in list(doc.paragraphs):
        para._p.getparent().remove(para._p)

    for line in text.splitlines():
        _format_line(doc, line)

    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(target)
    log(f"Saved DOCX: {target.name}")
    return str(target)
