from pathlib import Path

from docx import Document

from clean_format.docx_writer import write_deposition_docx


def test_docx_structure_and_font(tmp_path: Path):
    case_meta = {
        "cause_number": "2026-AB-123",
        "court": "DISTRICT COURT",
        "county": "BEXAR",
        "judicial_district": "408TH",
        "deposition_date": "2026-04-09",
        "witness_name": "BIANCA CARAM",
        "plaintiff_name": "PLAINTIFF NAME",
        "defendant_names": ["DEFENDANT ONE"],
        "attorneys": [{"name": "Alice Smith", "role": "plaintiff", "city": "San Antonio"}],
    }
    out = tmp_path / "out.docx"
    write_deposition_docx(case_meta, "BY MS. SMITH:\n\nQ.\tQuestion\n\nA.\tAnswer", out)
    doc = Document(out)
    assert len(doc.paragraphs) > 8
    assert len(doc.tables) == 1
    assert any("PROCEEDINGS" in p.text for p in doc.paragraphs)
    assert doc.styles["Normal"].font.name == "Courier New"
