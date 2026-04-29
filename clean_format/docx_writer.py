from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt


def _set_page_layout(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1.0)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)


def _set_default_font(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Courier New"
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set(qn("w:ascii"), "Courier New")


def _apply_table_borders(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        elem = OxmlElement(f"w:{edge}")
        elem.set(qn("w:val"), "single")
        elem.set(qn("w:sz"), "4")
        elem.set(qn("w:space"), "0")
        elem.set(qn("w:color"), "000000")
        borders.append(elem)
    tbl_pr.append(borders)


def write_deposition_docx(case_meta: dict[str, Any], formatted_text: str, output_path: str | Path) -> Path:
    output = Path(output_path)
    doc = Document()
    _set_page_layout(doc)
    _set_default_font(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"CAUSE NO. {case_meta['cause_number']}")
    r.bold = True

    table = doc.add_table(rows=3, cols=3)
    table.columns[0].width = Inches(3.0)
    table.columns[1].width = Inches(0.4)
    table.columns[2].width = Inches(3.0)
    _apply_table_borders(table)

    table.cell(0, 0).text = case_meta["plaintiff_name"]
    table.cell(0, 1).text = "§"
    table.cell(0, 2).text = f"IN THE {case_meta['court']}"
    table.cell(1, 0).text = "v."
    table.cell(1, 1).text = "§"
    table.cell(1, 2).text = f"{case_meta['judicial_district']} JUDICIAL DISTRICT"
    table.cell(2, 0).text = ", ".join(case_meta["defendant_names"])
    table.cell(2, 1).text = "§"
    table.cell(2, 2).text = f"{case_meta['county']} COUNTY, TEXAS"

    for text in ("* * *", "ORAL VIDEOTAPED DEPOSITION OF", case_meta["witness_name"], case_meta["deposition_date"]):
        cp = doc.add_paragraph(text)
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.runs[0].bold = True

    doc.add_paragraph(
        f"ORAL VIDEOTAPED DEPOSITION OF {case_meta['witness_name']}, produced as a witness in the above-styled and numbered cause."
    )
    doc.add_paragraph("APPEARANCES")
    doc.add_paragraph("FOR THE PLAINTIFF")
    for atty in [a for a in case_meta["attorneys"] if a["role"] == "plaintiff"]:
        doc.add_paragraph(f"{atty['name']} ({atty['city']})")
    for defendant in case_meta["defendant_names"]:
        doc.add_paragraph(f"FOR DEFENDANT {defendant}")
    for atty in [a for a in case_meta["attorneys"] if a["role"] == "defendant"]:
        doc.add_paragraph(f"{atty['name']} ({atty['city']})")
    doc.add_paragraph("ALSO PRESENT")
    doc.add_page_break()

    doc.add_paragraph("PROCEEDINGS").runs[0].bold = True
    for block in [b for b in formatted_text.split("\n\n") if b.strip()]:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 2.0
        p.paragraph_format.left_indent = Inches(0)
        text = block.strip()
        if text.startswith(("Q.\t", "A.\t")):
            label, body = text.split("\t", 1)
            p.add_run(label)
            p.add_run("\t" + body)
        else:
            p.add_run(text)

    doc.save(output)
    return output
