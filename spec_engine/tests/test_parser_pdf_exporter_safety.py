import os
import tempfile
from pathlib import Path

import pytest
from docx import Document


def _save_docx(lines: list[str]) -> str:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        path = tmp.name
    doc.save(path)
    return path


class TestParserSafety:
    def test_speaker_regex_accepts_spacing_and_case_variants(self):
        from spec_engine.parser import SPEAKER_INLINE_RE, SPEAKER_LABEL_RE

        assert SPEAKER_LABEL_RE.match("Speaker 1 :")
        assert SPEAKER_LABEL_RE.match("speaker 01:")
        assert SPEAKER_LABEL_RE.match("Speaker 1: ")
        inline = SPEAKER_INLINE_RE.match("speaker 1: Inline testimony.")
        assert inline is not None
        assert inline.group(1) == "1"
        assert inline.group(2) == "Inline testimony."

    def test_parse_blocks_raises_when_text_precedes_speaker_labels(self):
        from spec_engine.parser import parse_blocks

        path = _save_docx([
            "Intro text before labels.",
            "Speaker 1:",
            "Valid testimony follows.",
        ])
        try:
            with pytest.raises(ValueError, match="Text found before any speaker label"):
                parse_blocks(path)
        finally:
            os.unlink(path)

    def test_parse_blocks_preserves_raw_text_before_cleaning(self):
        from spec_engine.parser import parse_blocks

        path = _save_docx([
            "Speaker 1:",
            "One",
            "",
            "Two",
        ])
        try:
            blocks = parse_blocks(path)
        finally:
            os.unlink(path)

        assert len(blocks) == 1
        assert blocks[0].raw_text == "One  Two"
        assert blocks[0].text == "One Two"


class TestPdfExporterSafety:
    def test_export_pdf_raises_for_missing_input_docx(self, tmp_path):
        from spec_engine.pdf_exporter import export_pdf

        missing = tmp_path / "missing.docx"
        out_pdf = tmp_path / "out.pdf"

        with pytest.raises(FileNotFoundError):
            export_pdf(str(missing), str(out_pdf))

    def test_reportlab_fallback_logs_ufm_warning(self, caplog, monkeypatch, tmp_path):
        import spec_engine.pdf_exporter as pdf_exporter

        pdf_path = tmp_path / "out.pdf"
        docx_path = tmp_path / "in.docx"
        docx_path.write_text("placeholder", encoding="utf-8")

        monkeypatch.setitem(__import__("sys").modules, "reportlab", object())
        monkeypatch.setitem(__import__("sys").modules, "reportlab.lib", object())
        monkeypatch.setitem(__import__("sys").modules, "reportlab.lib.enums", type("M", (), {"TA_LEFT": 0}))
        monkeypatch.setitem(__import__("sys").modules, "reportlab.lib.pagesizes", type("M", (), {"letter": (612, 792)}))
        monkeypatch.setitem(
            __import__("sys").modules,
            "reportlab.lib.styles",
            type("M", (), {"ParagraphStyle": lambda *args, **kwargs: object()}),
        )
        monkeypatch.setitem(__import__("sys").modules, "reportlab.lib.units", type("M", (), {"inch": 72}))

        class FakeParagraph:
            def __init__(self, *args, **kwargs):
                pass

        class FakePageBreak:
            pass

        class FakeDoc:
            def __init__(self, *args, **kwargs):
                self.path = pdf_path

            def build(self, story):
                self.path.write_text("pdf", encoding="utf-8")

        monkeypatch.setitem(
            __import__("sys").modules,
            "reportlab.platypus",
            type(
                "M",
                (),
                {
                    "PageBreak": FakePageBreak,
                    "Paragraph": FakeParagraph,
                    "SimpleDocTemplate": FakeDoc,
                },
            ),
        )

        monkeypatch.setattr(pdf_exporter, "__name__", "spec_engine.pdf_exporter")
        monkeypatch.setattr("spec_engine.exporter.extract_text_from_docx", lambda path: "Line one\nLine two")
        monkeypatch.setattr("spec_engine.exporter.strip_to_ascii", lambda text: text)

        with caplog.at_level("WARNING"):
            ok = pdf_exporter._try_reportlab(str(docx_path), str(pdf_path))

        assert ok is True
        assert "does NOT preserve UFM formatting" in caplog.text
        assert pdf_path.exists()
