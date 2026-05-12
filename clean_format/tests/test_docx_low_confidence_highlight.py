"""Step D — yellow-highlight rendering for marker-bearing text.

Coverage:
  1. Marked tokens render with WD_COLOR_INDEX.YELLOW; surrounding text
     does not.
  2. Marker characters are stripped from rendered paragraph text.
  3. Q/A paragraphs preserve the canonical "\\tQ.\\t..." / "\\tA.\\t..."
     shape after marker-aware run splitting.
  4. Speaker paragraphs preserve the three-tab prefix and label-spacing.
  5. Existing layout — tab stops, hanging indent — unchanged.
  6. Multiple marked tokens in a single paragraph each get their own
     highlighted run.
  7. No-marker content renders as a single non-highlighted run (no
     spurious run splitting).
"""

from __future__ import annotations

from docx.enum.text import WD_COLOR_INDEX

from clean_format.docx_writer import build_deposition_document
from clean_format.low_confidence_markers import (
    LOW_CONF_CLOSE,
    LOW_CONF_OPEN,
)


def _case_meta() -> dict:
    return {
        "cause_number": "DC-25-13430",
        "court": "191st District Court",
        "county": "Dallas",
        "judicial_district": "191ST",
        "deposition_date": "2026-04-09",
        "witness_name": "Bianca Caram",
        "plaintiff_name": "Maria Lopez",
        "defendant_names": ["Acme Medical Group"],
        "reporter_name": "Miah Bardot",
        "attorneys": [
            {"name": "Emily Johnson", "role": "defendant", "city": "Houston"},
        ],
    }


def _marked(token: str) -> str:
    return f"{LOW_CONF_OPEN}{token}{LOW_CONF_CLOSE}"


def _find_paragraph(document, predicate):
    for paragraph in document.paragraphs:
        if predicate(paragraph):
            return paragraph
    raise AssertionError("paragraph matching predicate not found")


# ----------------------------------------------------------------------------
# Highlighted run rendering
# ----------------------------------------------------------------------------


class TestYellowHighlightRendering:
    def test_marked_token_in_qa_body_gets_yellow_run(self):
        formatted = f"A.\tI saw {_marked('Acebo')} examining the witness."
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tA.\t")
        )
        marked_runs = [
            r for r in paragraph.runs
            if r.font.highlight_color == WD_COLOR_INDEX.YELLOW
        ]
        assert len(marked_runs) == 1
        assert marked_runs[0].text == "Acebo"

    def test_unmarked_runs_in_same_qa_paragraph_not_highlighted(self):
        formatted = f"A.\tI saw {_marked('Acebo')} examining the witness."
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tA.\t")
        )
        unmarked_runs = [
            r for r in paragraph.runs
            if r.font.highlight_color != WD_COLOR_INDEX.YELLOW
        ]
        # At least one unmarked run for prefix/surrounding text.
        assert len(unmarked_runs) >= 1
        for r in unmarked_runs:
            assert r.font.highlight_color is None

    def test_marker_characters_stripped_from_paragraph_text(self):
        formatted = f"A.\tI saw {_marked('Acebo')} examining the witness."
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tA.\t")
        )
        assert LOW_CONF_OPEN not in paragraph.text
        assert LOW_CONF_CLOSE not in paragraph.text
        assert "LC:" not in paragraph.text
        # Final body text reads naturally.
        assert paragraph.text == "\tA.\tI saw Acebo examining the witness."

    def test_multiple_marked_tokens_each_get_own_yellow_run(self):
        formatted = (
            f"A.\tThe {_marked('Acebo')} witness saw {_marked('Cesar')} Plaza."
        )
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tA.\t")
        )
        marked_runs = [
            r for r in paragraph.runs
            if r.font.highlight_color == WD_COLOR_INDEX.YELLOW
        ]
        assert len(marked_runs) == 2
        assert [r.text for r in marked_runs] == ["Acebo", "Cesar"]

    def test_speaker_paragraph_with_marked_token(self):
        formatted = f"MR. SMITH:\tObjection, {_marked('Acebo')}."
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "MR. SMITH" in p.text and "Acebo" in p.text
        )
        # Marker stripped from paragraph text.
        assert LOW_CONF_OPEN not in paragraph.text
        # Yellow highlight on the marked token.
        marked_runs = [
            r for r in paragraph.runs
            if r.font.highlight_color == WD_COLOR_INDEX.YELLOW
        ]
        assert len(marked_runs) == 1
        assert marked_runs[0].text == "Acebo"
        # Three-tab prefix preserved.
        assert paragraph.text.startswith("\t\t\t")


# ----------------------------------------------------------------------------
# Non-regression — no markers
# ----------------------------------------------------------------------------


class TestNoMarkersUnchanged:
    def test_qa_without_markers_no_highlighted_runs(self):
        document = build_deposition_document("Q.\tQuestion\n\nA.\tAnswer", _case_meta())
        for paragraph in document.paragraphs:
            for r in paragraph.runs:
                assert r.font.highlight_color is None or (
                    r.font.highlight_color != WD_COLOR_INDEX.YELLOW
                )

    def test_qa_paragraph_text_unchanged_when_no_markers(self):
        # Regression: the existing test_write_proceedings_qa_run_text_preserves_leading_tab
        # asserts paragraph.text == "\tQ.\tQuestion" — this must hold
        # after the marker-aware run splitting.
        document = build_deposition_document("Q.\tQuestion", _case_meta())
        qa = _find_paragraph(document, lambda p: p.text.startswith("\tQ.\t"))
        assert qa.text == "\tQ.\tQuestion"

    def test_speaker_paragraph_text_unchanged_when_no_markers(self):
        document = build_deposition_document(
            "MR. SMITH:\tObjection. Form.", _case_meta()
        )
        speaker = _find_paragraph(
            document, lambda p: "MR. SMITH" in p.text and "Objection" in p.text
        )
        # Three-tab + label + double-space + body.
        assert speaker.text == "\t\t\tMR. SMITH:  Objection.  Form."


# ----------------------------------------------------------------------------
# Layout preservation
# ----------------------------------------------------------------------------


class TestLayoutPreserved:
    def test_qa_paragraph_with_marked_token_keeps_hanging_indent(self):
        formatted = f"Q.\tWas it {_marked('Acebo')}?"
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tQ.\t")
        )
        pf = paragraph.paragraph_format
        # 914400 EMU = 1.0", -914400 EMU = -1.0"
        assert pf.left_indent == 914400
        assert pf.first_line_indent == -914400

    def test_qa_paragraph_with_marked_token_keeps_tab_stops(self):
        formatted = f"Q.\tWas it {_marked('Acebo')}?"
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tQ.\t")
        )
        positions = [t.position for t in paragraph.paragraph_format.tab_stops]
        assert 457200 in positions   # 0.5"
        assert 914400 in positions   # 1.0"
        assert 1371600 in positions  # 1.5"

    def test_qa_paragraph_with_marker_at_start_of_body(self):
        formatted = f"A.\t{_marked('Acebo')} was here."
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tA.\t")
        )
        # First run is the "\tA.\t" prefix; second is the highlighted marker.
        assert paragraph.runs[0].text == "\tA.\t"
        assert paragraph.runs[0].font.highlight_color is None
        assert paragraph.runs[1].text == "Acebo"
        assert paragraph.runs[1].font.highlight_color == WD_COLOR_INDEX.YELLOW

    def test_qa_paragraph_with_marker_at_end_of_body(self):
        formatted = f"A.\tI saw {_marked('Acebo')}"
        document = build_deposition_document(formatted, _case_meta())
        paragraph = _find_paragraph(
            document, lambda p: "Acebo" in p.text and p.text.startswith("\tA.\t")
        )
        # Last run is the highlighted marker.
        assert paragraph.runs[-1].text == "Acebo"
        assert paragraph.runs[-1].font.highlight_color == WD_COLOR_INDEX.YELLOW
