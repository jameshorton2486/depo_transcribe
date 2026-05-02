"""DOCX writer for clean-format deposition output."""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

# Windows-illegal filename characters plus ASCII control bytes. NTFS
# silently treats `:` as an alternate-data-stream separator, so a bad
# filename can succeed at write time but be unreachable to Word.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')
_WHITESPACE_RUN = re.compile(r"\s+")
_TRAILING_AT_SUFFIX = re.compile(r"\s+at\s+.*$", re.IGNORECASE)
_SENTENCE_SPACE_RE = re.compile(r"([.!?])\s+")


def sanitize_filename_component(value: str) -> str:
    """
    Strip Windows-illegal characters from a filename component.

    Removes <>:"/\\|?* and ASCII control bytes, collapses whitespace runs,
    strips leading/trailing dots and spaces. Falls back to "document" when
    the input is empty or sanitizes to nothing — bare-suffix filenames
    (e.g. ".docx") are illegal on Windows.
    """
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("", value or "")
    cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip()
    cleaned = cleaned.strip(". ")
    return cleaned or "document"


def safe_save(
    document: Document, path: Path, *, retries: int = 3, delay_seconds: float = 1.0
) -> None:
    """Retry transient Word lock failures before surfacing a clean error."""
    for attempt in range(retries):
        try:
            document.save(path)
            return
        except PermissionError:
            if attempt == retries - 1:
                break
            time.sleep(delay_seconds)

    raise PermissionError(f"File is open or locked:\n{path}")


def _set_cell_border(cell: Any) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "8")
        element.set(qn("w:color"), "000000")


def _set_document_defaults(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)

    style = document.styles["Normal"]
    style.font.name = "Courier New"
    style.font.size = Pt(12)
    paragraph_format = style.paragraph_format
    paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    paragraph_format.space_after = Pt(0)


def _center_paragraph(document: Document, text: str, *, bold: bool = False) -> Any:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.bold = bold
    return paragraph


def _left_paragraph(document: Document, text: str = "", *, bold: bool = False) -> Any:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = bold
    return paragraph


def _format_date_for_filename(raw_date: str) -> str:
    # Intake often appends a start time after the date ("April 9, 2026 at
    # 8:00 a.m."). Strip that suffix before strptime so the strict formats
    # below have a chance to match.
    candidate = _TRAILING_AT_SUFFIX.sub("", raw_date or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return (candidate or raw_date).replace("/", "-").replace(",", "")


def _double_space_sentences(text: str) -> str:
    return _SENTENCE_SPACE_RE.sub(r"\1  ", (text or "").strip())


def _parse_blocks(formatted_text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for block in (formatted_text or "").split("\n\n"):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        line = lines[0]
        if line.startswith("Q.\t"):
            blocks.append({"kind": "qa", "label": "Q.", "text": line[3:]})
        elif line.startswith("A.\t"):
            blocks.append({"kind": "qa", "label": "A.", "text": line[3:]})
        elif ":\t" in line:
            label, text = line.split(":\t", 1)
            blocks.append({"kind": "speaker", "label": label + ":", "text": text})
        elif line.endswith(":"):
            blocks.append({"kind": "header", "label": line, "text": ""})
        else:
            blocks.append({"kind": "speaker", "label": "", "text": line})
    return _merge_consecutive_speaker_blocks(blocks)


def _merge_consecutive_speaker_blocks(
    blocks: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for block in blocks:
        if (
            merged
            and block["kind"] == "speaker"
            and merged[-1]["kind"] == "speaker"
            and block["label"]
            and block["label"] == merged[-1]["label"]
        ):
            prior_text = merged[-1]["text"].rstrip()
            current_text = block["text"].lstrip()
            merged[-1]["text"] = _double_space_sentences(f"{prior_text} {current_text}")
            continue
        if block["kind"] == "speaker" and block["text"]:
            block = {**block, "text": _double_space_sentences(block["text"])}
        merged.append(block)
    return merged


def _write_caption_table(document: Document, case_meta: dict[str, Any]) -> None:
    table = document.add_table(rows=4, cols=3)
    table.columns[0].width = Inches(3)
    table.columns[1].width = Inches(0.4)
    table.columns[2].width = Inches(3)

    defendant_text = "\n".join(case_meta.get("defendant_names", []) or [])
    right_top = "IN THE DISTRICT COURT"
    district = case_meta.get("judicial_district", "")
    county = case_meta.get("county", "")
    right_bottom = f"{district} JUDICIAL DISTRICT\n{county} COUNTY, TEXAS".strip()

    rows = [
        (case_meta.get("plaintiff_name", ""), "§", right_top),
        ("Plaintiff,", "§", ""),
        ("vs.", "§", right_bottom),
        (defendant_text or "Defendant", "§", ""),
    ]
    for row_index, row_values in enumerate(rows):
        for col_index, value in enumerate(row_values):
            cell = table.cell(row_index, col_index)
            cell.text = value
            _set_cell_border(cell)
            if col_index == 1:
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER


def _write_appearances(document: Document, case_meta: dict[str, Any]) -> None:
    _center_paragraph(document, "APPEARANCES", bold=True)
    attorneys = case_meta.get("attorneys", []) or []
    plaintiffs = [entry for entry in attorneys if entry.get("role") == "plaintiff"]
    defendants = [entry for entry in attorneys if entry.get("role") == "defendant"]

    if plaintiffs:
        _left_paragraph(document, "FOR THE PLAINTIFF", bold=True)
        for entry in plaintiffs:
            _left_paragraph(document, entry.get("name", ""))
            if entry.get("city"):
                _left_paragraph(document, entry["city"])

    if defendants:
        for entry in defendants:
            _left_paragraph(
                document, f"FOR DEFENDANT {entry.get('name', '').upper()}", bold=True
            )
            _left_paragraph(document, entry.get("name", ""))
            if entry.get("city"):
                _left_paragraph(document, entry["city"])

    _left_paragraph(document, "ALSO PRESENT", bold=True)
    if case_meta.get("videographer_name"):
        _left_paragraph(document, case_meta["videographer_name"])
    if case_meta.get("reporter_name"):
        _left_paragraph(document, case_meta["reporter_name"])


def _write_proceedings(
    document: Document, formatted_text: str, case_meta: dict[str, Any]
) -> None:
    _center_paragraph(document, "PROCEEDINGS", bold=True)

    witness_name = case_meta.get("witness_name", "").upper()
    if witness_name:
        _center_paragraph(document, f"{witness_name},", bold=True)
        _left_paragraph(document, "having been first duly sworn, testified as follows:")
        _center_paragraph(document, "EXAMINATION", bold=True)

        examining = next(
            (
                entry
                for entry in case_meta.get("attorneys", []) or []
                if entry.get("role") == "defendant"
            ),
            None,
        )
        if examining:
            last_name = examining.get("name", "").split()[-1].upper()
            _left_paragraph(document, f"BY MS. {last_name}:")

    for block in _parse_blocks(formatted_text):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.left_indent = Inches(0)
        paragraph.paragraph_format.first_line_indent = Inches(0)
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(0.25))
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(0.625))
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(1.0))

        if block["kind"] == "qa":
            paragraph.add_run(f"{block['label']}\t{block['text']}")
        elif block["kind"] == "speaker":
            if block["label"]:
                paragraph.add_run(f"{block['label']}  {block['text']}")
            else:
                paragraph.add_run(_double_space_sentences(block["text"]))
        else:
            run = paragraph.add_run(block["label"])
            run.bold = True


def build_deposition_document(
    formatted_text: str, case_meta: dict[str, Any]
) -> Document:
    document = Document()
    _set_document_defaults(document)

    _center_paragraph(
        document, f"CAUSE NO. {case_meta.get('cause_number', '')}", bold=True
    )
    _write_caption_table(document, case_meta)
    _center_paragraph(document, "* * * * *")
    _center_paragraph(document, "ORAL VIDEOTAPED", bold=True)
    _center_paragraph(document, "DEPOSITION OF", bold=True)
    _center_paragraph(document, case_meta.get("witness_name", "").upper(), bold=True)
    _center_paragraph(document, case_meta.get("deposition_date", ""), bold=True)

    document.add_paragraph()
    _left_paragraph(
        document,
        (
            f"ORAL VIDEOTAPED DEPOSITION OF {case_meta.get('witness_name', '').upper()}, "
            "produced as a witness at the time and place set out below."
        ),
    )
    document.add_paragraph()
    _write_appearances(document, case_meta)
    document.add_page_break()
    _write_proceedings(document, formatted_text, case_meta)
    return document


def write_deposition_docx(
    formatted_text: str,
    case_meta: dict[str, Any],
    output_path: str | Path | None = None,
) -> str:
    witness_last = (case_meta.get("witness_name", "Witness").split() or ["Witness"])[-1]
    date_part = _format_date_for_filename(str(case_meta.get("deposition_date", "")))
    if output_path:
        path = Path(output_path)
    else:
        path = Path(f"{witness_last}_Deposition_{date_part}.docx")
    # Last-line defense: sanitize the filename stem regardless of whether
    # output_path was passed. Callers that pre-build a path (UI, CLI) miss
    # the helper above, and a `:` in the name silently writes into an ADS
    # rather than a real file Word can open.
    suffix = path.suffix or ".docx"
    sanitized_stem = sanitize_filename_component(path.stem)
    path = path.with_name(f"{sanitized_stem}{suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    document = build_deposition_document(formatted_text, case_meta)
    safe_save(document, path)
    return str(path)
