from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt

from core.docx_formatter import (
    _iter_formatted_lines,
    build_docx_from_transcript_text,
    build_output_docx_path,
    format_transcript_to_docx,
)
from spec_engine.models import LineType


def test_iter_formatted_lines_classifies_supported_line_types():
    text = (
        "\tQ.  Did you see that?\n"
        "\tA.  Yes.\n"
        "\t\t\tTHE REPORTER:  Please raise your right hand.\n"
        "(Whereupon, the witness was sworn.)\n"
        "[SCOPIST: FLAG 1: Verify amount]\n"
        "EXAMINATION\n"
        "BY MR. SMITH:\n"
        "Loose text"
    )

    result = list(_iter_formatted_lines(text))

    assert result == [
        (LineType.Q, "Did you see that?"),
        (LineType.A, "Yes."),
        (LineType.SP, "THE REPORTER:  Please raise your right hand."),
        (LineType.PN, "(Whereupon, the witness was sworn.)"),
        (LineType.FLAG, "[SCOPIST: FLAG 1: Verify amount]"),
        (LineType.HEADER, "EXAMINATION"),
        (LineType.BY, "BY MR. SMITH:"),
        (LineType.PLAIN, "Loose text"),
    ]


def test_build_docx_from_transcript_text_uses_spec_engine_document_defaults():
    text = (
        "\tQ.  Did you see that?\n"
        "\tA.  Yes.\n"
        "\t\t\tTHE REPORTER:  Please raise your right hand."
    )

    doc = build_docx_from_transcript_text(text)

    assert len(doc.paragraphs) == 3
    section = doc.sections[0]
    assert section.left_margin == Inches(1.25)
    assert section.right_margin == Inches(1.0)
    assert section.top_margin == Inches(1.0)
    assert section.bottom_margin == Inches(1.0)
    first_run = doc.paragraphs[0].runs[0]
    assert first_run.font.name == "Courier New"
    assert first_run.font.size == Pt(12)


def test_build_output_docx_path_strips_corrected_suffix():
    output = build_output_docx_path(r"C:\tmp\sample_corrected.txt")

    assert output.endswith("sample_formatted.docx")


def test_format_transcript_to_docx_creates_file_and_reports_progress(tmp_path):
    source = tmp_path / "sample_corrected.txt"
    source.write_text(
        "\tQ.  Did you see that?\n"
        "\tA.  Yes.\n"
        "\t\t\tTHE REPORTER:  Please raise your right hand.\n",
        encoding="utf-8",
    )
    output = tmp_path / "formatted.docx"
    progress = []

    saved_path = format_transcript_to_docx(
        str(source),
        output_path=str(output),
        progress_callback=progress.append,
    )

    assert saved_path == str(output)
    assert output.exists()
    assert progress == [
        "Reading transcript: sample_corrected.txt",
        "Saved DOCX: formatted.docx",
    ]

    doc = Document(saved_path)
    assert len(doc.paragraphs) == 3
    assert "\tQ.  Did you see that?" in doc.paragraphs[0].text
    assert "\tA.  Yes." in doc.paragraphs[1].text


def test_format_transcript_to_docx_raises_for_missing_source(tmp_path):
    missing = tmp_path / "missing.txt"

    try:
        format_transcript_to_docx(str(missing))
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
