from __future__ import annotations

from docx import Document

from clean_format.docx_writer import build_deposition_document, write_deposition_docx


def _case_meta() -> dict:
    return {
        "cause_number": "DC-25-13430",
        "court": "191st District Court",
        "county": "Dallas",
        "judicial_district": "191ST",
        "deposition_date": "2026-04-09",
        "start_time": "9:00 AM",
        "end_time": "12:30 PM",
        "witness_name": "Bianca Caram",
        "witness_credentials": "M.D.",
        "plaintiff_name": "Maria Lopez",
        "defendant_names": ["Acme Medical Group"],
        "reporter_name": "Miah Bardot",
        "reporter_csr": "12129",
        "attorneys": [
            {"name": "Jane Smith", "role": "plaintiff", "city": "Dallas"},
            {"name": "Emily Johnson", "role": "defendant", "city": "Houston"},
        ],
        "videographer_name": "Alex Video",
    }


def test_build_deposition_document_has_caption_table_and_examination_header():
    document = build_deposition_document("Q.\tState your name.\n\nA.\tBianca Caram.", _case_meta())
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert document.tables
    assert "EXAMINATION" in text


def test_write_deposition_docx_sets_courier_default(tmp_path):
    output_path = tmp_path / "sample.docx"
    saved_path = write_deposition_docx("Q.\tQuestion\n\nA.\tAnswer", _case_meta(), output_path)
    document = Document(saved_path)
    assert document.styles["Normal"].font.name == "Courier New"


def test_write_deposition_docx_writes_file(tmp_path):
    output_path = tmp_path / "sample.docx"
    saved_path = write_deposition_docx("LABEL:\tToday's date is April 9, 2026.", _case_meta(), output_path)
    assert output_path.exists()
    assert saved_path.endswith("sample.docx")
