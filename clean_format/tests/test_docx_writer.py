from __future__ import annotations

from docx import Document

from clean_format.docx_writer import (
    _parse_blocks,
    build_deposition_document,
    safe_save,
    sanitize_filename_component,
    write_deposition_docx,
)


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
    document = build_deposition_document(
        "Q.\tState your name.\n\nA.\tBianca Caram.", _case_meta()
    )
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert document.tables
    assert "EXAMINATION" in text


def test_write_deposition_docx_sets_courier_default(tmp_path):
    output_path = tmp_path / "sample.docx"
    saved_path = write_deposition_docx(
        "Q.\tQuestion\n\nA.\tAnswer", _case_meta(), output_path
    )
    document = Document(saved_path)
    assert document.styles["Normal"].font.name == "Courier New"


def test_write_deposition_docx_writes_file(tmp_path):
    output_path = tmp_path / "sample.docx"
    saved_path = write_deposition_docx(
        "LABEL:\tToday's date is April 9, 2026.", _case_meta(), output_path
    )
    assert output_path.exists()
    assert saved_path.endswith("sample.docx")


def test_parse_blocks_merges_consecutive_same_speaker_into_one_paragraph():
    formatted_text = (
        "VIDEOGRAPHER:\tToday's date is 04/09/2026.\n\n"
        "VIDEOGRAPHER:\tThe time is 08:12 AM.\n\n"
        "VIDEOGRAPHER:\tThis is the beginning of the video deposition.\n\n"
        "VIDEOGRAPHER:\tWill the court reporter please swear in the witness?"
    )

    blocks = _parse_blocks(formatted_text)

    assert blocks == [
        {
            "kind": "speaker",
            "label": "VIDEOGRAPHER:",
            "text": (
                "Today's date is 04/09/2026.  The time is 08:12 AM.  "
                "This is the beginning of the video deposition.  "
                "Will the court reporter please swear in the witness?"
            ),
        }
    ]


def test_write_proceedings_uses_two_spaces_after_speaker_colon_and_sentences():
    document = build_deposition_document(
        (
            "VIDEOGRAPHER:\tToday's date is 04/09/2026.\n\n"
            "VIDEOGRAPHER:\tThe time is 08:12 AM."
        ),
        _case_meta(),
    )
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "VIDEOGRAPHER:  Today's date is 04/09/2026.  The time is 08:12 AM." in text


def test_write_proceedings_sets_qa_tab_stops_to_requested_positions():
    document = build_deposition_document("Q.\tQuestion\n\nA.\tAnswer", _case_meta())
    qa_paragraph = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.startswith("Q.\t")
    )
    tab_positions = [tab.position for tab in qa_paragraph.paragraph_format.tab_stops]
    # Canonical UFM tab stops at 0.5" / 1.0" / 1.5" (UFM Section 2.102.11),
    # mirrored from spec_engine/ufm_rules.py:25. EMU = English Metric Units;
    # 914400 EMU = 1 inch.
    assert 457200 in tab_positions   # 0.5"
    assert 914400 in tab_positions   # 1.0"
    assert 1371600 in tab_positions  # 1.5"


def test_sanitize_filename_component_replaces_spaces_and_punctuation():
    assert sanitize_filename_component(
        "CARAM Deposition April 9, 2026 at 800 a.m."
    ) == ("CARAM Deposition April 9, 2026 at 800 a.m")


def test_safe_save_retries_permission_error(monkeypatch, tmp_path):
    document = build_deposition_document("Q.\tQuestion\n\nA.\tAnswer", _case_meta())
    target_path = tmp_path / "retry.docx"
    attempts = {"count": 0}
    original_save = document.save

    def flaky_save(path):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise PermissionError("locked")
        return original_save(path)

    monkeypatch.setattr(document, "save", flaky_save)

    safe_save(document, target_path, delay_seconds=0)

    assert attempts["count"] == 3
    assert target_path.exists()
