"""
emitter.py

Writes formatted paragraphs to a python-docx Document.
Spec Section 5: Page Layout and Typography
Spec Section 3.3: Five Line Types

TYPOGRAPHY (must match exactly — Spec Section 5.2):
  Font:         Courier New, 12pt
  Line spacing: Double
  Tab stops:    360 / 900 / 1440 / 2160 / 2880 twips
  Margins:      Left 1.25" / Right 1.0" / Top 1.0" / Bottom 1.0"

COLOR USAGE (Spec Section 5.4):
  Orange  #B45F06 / RGBColor(0xB4,0x5F,0x06) — Scopist flags (bold)
  Navy    #1E3A5F / RGBColor(0x1E,0x3A,0x5F) — All parenthetical lines
  Black   Default                              — All other transcript text
"""

import docx.enum.text
import textwrap
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips

from .models import LineType


# ── Color constants ────────────────────────────────────────────────────────────
COLOR_ORANGE = RGBColor(0xB4, 0x5F, 0x06)
COLOR_NAVY   = RGBColor(0x1E, 0x3A, 0x5F)
COLOR_BLACK  = RGBColor(0x00, 0x00, 0x00)

# ── Typography ─────────────────────────────────────────────────────────────────
FONT_NAME = "Courier New"
FONT_SIZE = Pt(12)
WRAP_WIDTH = 65
QA_WRAP_WIDTH = 56

# ── Tab stop positions in twips (Spec Section 5.3) ────────────────────────────
TAB_360  = 360    # 0.25" — Q./A. letter
TAB_900  = 900    # 0.625" — Q/A text start
TAB_1440 = 1440   # 1.0"  — Speaker label
TAB_2160 = 2160   # 1.5"  — Parenthetical
TAB_2880 = 2880   # 2.0"  — Reserved
_STANDARD_TABS = [TAB_360, TAB_900, TAB_1440, TAB_2160]


# ── Q/A pair safety tracker (Spec Section 5.5) ────────────────────────────────
class QAPairTracker:
    """
    Spec 5.5: Never split Q and A pairs across pages.
    """
    def __init__(self):
        self.last_was_q = False

    def record_q(self):
        self.last_was_q = True

    def record_other(self):
        self.last_was_q = False

    def safe_to_break(self) -> bool:
        return not self.last_was_q


# ── Internal helpers ──────────────────────────────────────────────────────────

def _apply_standard_tabs(para) -> None:
    """
    Apply the four standard transcript tab stops to a paragraph.
    Centralizes tab stop definition so both emitter paths stay in sync.
    """
    pPr = para._p.get_or_add_pPr()
    tabs_elem = OxmlElement("w:tabs")
    for stop_twips in _STANDARD_TABS:
        tab = OxmlElement("w:tab")
        tab.set(qn("w:val"), "left")
        tab.set(qn("w:pos"), str(stop_twips))
        tabs_elem.append(tab)
    pPr.append(tabs_elem)

def _set_paragraph_format(para, tab_stops=None):
    pf = para.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    pf.space_before = Pt(0)
    pf.space_after  = Pt(0)
    if tab_stops:
        pPr = para._p.get_or_add_pPr()
        tabs_elem = OxmlElement('w:tabs')
        for stop_twips in tab_stops:
            tab = OxmlElement('w:tab')
            tab.set(qn('w:val'), 'left')
            tab.set(qn('w:pos'), str(stop_twips))
            tabs_elem.append(tab)
        pPr.append(tabs_elem)


def _add_run(para, text, bold=False, color=COLOR_BLACK):
    run = para.add_run(text)
    run.font.name  = FONT_NAME
    run.font.size  = FONT_SIZE
    run.font.bold  = bold
    run.font.color.rgb = color
    return run


def _wrap_lines(text: str, width: int) -> list[str]:
    stripped = (text or "").strip()
    if not stripped:
        return [""]
    return textwrap.wrap(
        stripped,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [stripped]


def _split_speaker_text(text: str) -> tuple[str, str]:
    if ":  " in text:
        label, content = text.split(":  ", 1)
        return label + ":", content
    if ":" in text:
        label, content = text.split(":", 1)
        return label + ":", content.strip()
    return "", text


# ── Line type emitters (Spec Section 3.3) ────────────────────────────────────

def emit_q_line(doc: Document, text: str):
    """Spec 3.3 Type 1 — Question: [TAB] Q. [TAB] text"""
    lines = _wrap_lines(text, QA_WRAP_WIDTH)
    for idx, line in enumerate(lines):
        para = doc.add_paragraph()
        _set_paragraph_format(para, [TAB_360, TAB_900])
        prefix = '\tQ.\t' if idx == 0 else '\t'
        _add_run(para, f'{prefix}{line}')


def emit_a_line(doc: Document, text: str):
    """Spec 3.3 Type 2 — Answer: [TAB] A. [TAB] text"""
    lines = _wrap_lines(text, QA_WRAP_WIDTH)
    for idx, line in enumerate(lines):
        para = doc.add_paragraph()
        _set_paragraph_format(para, [TAB_360, TAB_900])
        prefix = '\tA.\t' if idx == 0 else '\t'
        _add_run(para, f'{prefix}{line}')


def emit_sp_line(doc: Document, text: str):
    """
    Spec 3.3 Type 3 — Speaker Label: [TAB][TAB][TAB] LABEL: [bold]  text
    Position: 1440 twips. Label is BOLD. Two literal spaces after colon.
    """
    label, content = _split_speaker_text(text)
    if not label:
        for line in _wrap_lines(text, WRAP_WIDTH):
            para = doc.add_paragraph()
            _set_paragraph_format(para, [TAB_1440])
            _add_run(para, '\t\t\t' + line)
        return

    prefix_len = len(label) + 2
    lines = _wrap_lines(content, max(10, WRAP_WIDTH - prefix_len))
    for idx, line in enumerate(lines):
        para = doc.add_paragraph()
        _set_paragraph_format(para, [TAB_1440])
        if idx == 0:
            _add_run(para, '\t\t\t', bold=False)
            _add_run(para, label, bold=True)
            _add_run(para, '  ' + line, bold=False)
        else:
            _add_run(para, '\t\t\t' + (' ' * prefix_len) + line, bold=False)


def emit_pn_line(doc: Document, text: str):
    """Spec 3.3 Type 4 — Parenthetical: 4 tabs, navy color."""
    for line in _wrap_lines(text, WRAP_WIDTH):
        para = doc.add_paragraph()
        _set_paragraph_format(para, [TAB_2160])
        _add_run(para, f'\t\t\t\t{line}', color=COLOR_NAVY)


def emit_flag_line(doc: Document, text: str):
    """Spec 3.3 Type 5 — Scopist Flag: bold orange."""
    for line in _wrap_lines(text, WRAP_WIDTH):
        para = doc.add_paragraph()
        _set_paragraph_format(para)
        _add_run(para, line, bold=True, color=COLOR_ORANGE)


def emit_header_line(doc: Document, text: str):
    """Spec 4.1 — Examination header: centered bold."""
    para = doc.add_paragraph()
    _set_paragraph_format(para)
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(para, text, bold=True)


def emit_by_line(doc: Document, text: str):
    """Spec 4.1 — BY attribution line: left-aligned."""
    for line in _wrap_lines(text, WRAP_WIDTH):
        para = doc.add_paragraph()
        _set_paragraph_format(para)
        _add_run(para, line)


def emit_line(doc: Document, line_type: LineType, text: str):
    """Master dispatch — routes to correct emitter based on LineType."""
    dispatch = {
        LineType.Q:      emit_q_line,
        LineType.A:      emit_a_line,
        LineType.SP:     emit_sp_line,
        LineType.PN:     emit_pn_line,
        LineType.FLAG:   emit_flag_line,
        LineType.HEADER: emit_header_line,
        LineType.BY:     emit_by_line,
    }
    fn = dispatch.get(line_type)
    if fn:
        fn(doc, text)


def add_page_break(doc: Document):
    """Insert a hard page break (Spec Section 5.5)."""
    para = doc.add_paragraph()
    run = para.add_run()
    run.add_break(WD_BREAK.PAGE)


def create_document() -> Document:
    """Create Document with correct page setup (Spec Section 5.1)."""
    doc = Document()
    section = doc.sections[0]
    section.page_width    = Twips(12240)  # 8.5"
    section.page_height   = Twips(15840)  # 11"
    section.left_margin   = Twips(1800)   # 1.25"
    section.right_margin  = Twips(1440)   # 1.0"
    section.top_margin    = Twips(1440)   # 1.0"
    section.bottom_margin = Twips(1440)   # 1.0"
    if doc.paragraphs:
        p = doc.paragraphs[0]._element
        p.getparent().remove(p)
    return doc


# ── Line number tracking (Spec Section 6 — UFM requirement) ──────────────────

class LineNumberTracker:
    """
    Tracks line numbers for Texas UFM transcript body pages.
    Lines restart at 1 at the start of each transcript page.
    Courier New 12pt double-spaced = approximately 25 lines per page.

    IMPORTANT: Line numbers apply to Pages 3+ (transcript body) only.
    Pages 1 (Corrections Log) and 2 (Caption) are NOT numbered.
    """
    # LINES_PER_PAGE derivation (Texas UFM compliance):
    #   Paper height:       11.0 inches
    #   Top margin:          1.0 inch
    #   Bottom margin:       1.0 inch
    #   Usable height:       9.0 inches
    #   Line height (Courier New 12pt double-spaced): 24pt = 1/3 inch
    #   Raw capacity:        9.0 / (1/3) = 27 lines
    #   Deduct 2 lines for UFM header area (page number + catch word)
    #   Result:              25 lines per body page
    LINES_PER_PAGE = 25

    def __init__(self, start_page: int = 3):
        self.current_line = 1
        self.current_page = start_page  # Transcript body starts on page 3

    def next(self) -> tuple:
        """
        Advance and return (page_number, line_number).
        Auto-increments page when line exceeds LINES_PER_PAGE.
        """
        page = self.current_page
        line = self.current_line
        self.current_line += 1
        if self.current_line > self.LINES_PER_PAGE:
            self.current_line = 1
            self.current_page += 1
        return page, line

    def reset_for_new_page(self):
        """Manually trigger a page break (e.g., for section headers)."""
        self.current_line = 1
        self.current_page += 1

    def safe_to_break_before(self) -> bool:
        """
        Returns True if inserting a section break here is safe
        (i.e., we're not immediately after a Q line).
        Works with QAPairTracker for enforcement.
        """
        return True  # LineNumberTracker delegates Q/A safety to QAPairTracker


def emit_line_numbered(
    doc: Document,
    line_type: LineType,
    text: str,
    tracker: LineNumberTracker,
    qa_tracker: QAPairTracker,
):
    """
    Emit a line with a left-margin line number.
    Format:
      [line_num right-justified in 4 chars] [TAB] [normal line content]

    Line numbers are right-justified in a 4-char field:
       1    Q.  Question text
       2    A.  Answer text
       3        MR. SALAZAR:  Objection.

    Args:
        doc: The output Document.
        line_type: LineType to emit.
        text: The line text.
        tracker: LineNumberTracker instance.
        qa_tracker: QAPairTracker for Q/A split safety.
    """
    if line_type == LineType.Q:
        visual_lines = [('\tQ.\t' if i == 0 else '\t') + line for i, line in enumerate(_wrap_lines(text, QA_WRAP_WIDTH))]
    elif line_type == LineType.A:
        visual_lines = [('\tA.\t' if i == 0 else '\t') + line for i, line in enumerate(_wrap_lines(text, QA_WRAP_WIDTH))]
    elif line_type == LineType.SP:
        label, content = _split_speaker_text(text)
        if label:
            prefix_len = len(label) + 2
            wrapped = _wrap_lines(content, max(10, WRAP_WIDTH - prefix_len))
            visual_lines = [f"\t\t\t{label}  {wrapped[0]}"] + [
                "\t\t\t" + (" " * prefix_len) + line for line in wrapped[1:]
            ]
        else:
            visual_lines = ['\t\t\t' + line for line in _wrap_lines(text, WRAP_WIDTH)]
    elif line_type == LineType.PN:
        visual_lines = ['\t\t\t\t' + line for line in _wrap_lines(text, WRAP_WIDTH)]
    else:
        visual_lines = _wrap_lines(text, WRAP_WIDTH)

    for idx, visual_line in enumerate(visual_lines):
        page, line_num = tracker.next()
        if line_type == LineType.Q and idx == 0:
            qa_tracker.record_q()
        elif idx == 0:
            qa_tracker.record_other()

        para = doc.add_paragraph()
        pf = para.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)

        line_num_str = f"{line_num:>2} "
        num_run = para.add_run(line_num_str)
        num_run.font.name = FONT_NAME
        num_run.font.size = Pt(10)
        num_run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

        if line_type in (LineType.Q, LineType.A):
            content_run = para.add_run(visual_line)
            content_run.font.color.rgb = COLOR_BLACK
        elif line_type == LineType.SP:
            if idx == 0 and ": " in visual_line:
                if ":  " in visual_line:
                    label_part, text_part = visual_line.split(":  ", 1)
                else:
                    label_part, text_part = visual_line.split(": ", 1)
                label_part += ":"
                para.add_run(label_part[:3]).font.name = FONT_NAME
                bold_run = para.add_run(label_part[3:])
                bold_run.bold = True
                bold_run.font.name = FONT_NAME
                bold_run.font.size = FONT_SIZE
                bold_run.font.color.rgb = COLOR_BLACK
                para.add_run("  " + text_part).font.name = FONT_NAME
            else:
                content_run = para.add_run(visual_line)
                content_run.font.color.rgb = COLOR_BLACK
        elif line_type == LineType.PN:
            content_run = para.add_run(visual_line)
            content_run.font.color.rgb = COLOR_NAVY
        elif line_type == LineType.FLAG:
            content_run = para.add_run(visual_line)
            content_run.bold = True
            content_run.font.color.rgb = COLOR_ORANGE
        elif line_type == LineType.HEADER:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            content_run = para.add_run(visual_line)
            content_run.bold = True
            content_run.font.color.rgb = COLOR_BLACK
        elif line_type == LineType.BY:
            content_run = para.add_run(visual_line)
            content_run.font.color.rgb = COLOR_BLACK

        for run in para.runs:
            if not run.font.name:
                run.font.name = FONT_NAME
            if not run.font.size:
                run.font.size = FONT_SIZE

        _apply_standard_tabs(para)
