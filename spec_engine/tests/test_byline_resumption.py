"""Tests for by-line resumption annotation (defect #2)."""

from spec_engine.byline_resumption import apply_byline_resumption
from spec_engine.models import TranscriptBlock


def _q(text: str, examiner: str | None = "MR. NUNEZ") -> TranscriptBlock:
    return TranscriptBlock(
        speaker="MR. NUNEZ", text=text, type="question", examiner=examiner
    )


def _a(text: str = "Yes.") -> TranscriptBlock:
    return TranscriptBlock(speaker="THE WITNESS", text=text, type="answer")


def _colloquy(speaker: str, text: str) -> TranscriptBlock:
    return TranscriptBlock(speaker=speaker, text=text, type="colloquy")


def _directive(text: str) -> TranscriptBlock:
    return TranscriptBlock(speaker="", text=text, type="directive")


def _oath(text: str = "(The witness was sworn)") -> TranscriptBlock:
    return TranscriptBlock(speaker="", text=text, type="oath")


def test_first_question_of_deposition_gets_byline():
    blocks = [_q("Good afternoon. State your name.")]
    result = apply_byline_resumption(blocks)
    assert result[0].text == "(BY MR. NUNEZ) Good afternoon. State your name."


def test_subsequent_questions_in_same_run_unannotated():
    blocks = [
        _q("Good afternoon. State your name."),
        _a("Heath Thomas."),
        _q("And your date of birth?"),
        _a("May 7, 1968."),
        _q("Where do you live?"),
    ]
    result = apply_byline_resumption(blocks)
    assert result[0].text.startswith("(BY MR. NUNEZ) ")
    assert result[2].text == "And your date of birth?"
    assert result[4].text == "Where do you live?"


def test_byline_after_recess_directive():
    blocks = [
        _q("Good afternoon."),
        _a("Hi."),
        _directive("(Recess from 1:34 p.m. to 1:35 p.m.)"),
        _q("All right. We just came back."),
    ]
    result = apply_byline_resumption(blocks)
    assert result[3].text == "(BY MR. NUNEZ) All right. We just came back."


def test_byline_after_exhibit_marker():
    blocks = [
        _q("Mark this as Plaintiff's Exhibit 1."),
        _directive("(Exhibit 1 marked)"),
        _q("Do you recognize this document?"),
    ]
    result = apply_byline_resumption(blocks)
    assert result[0].text.startswith("(BY MR. NUNEZ) ")
    assert result[2].text == "(BY MR. NUNEZ) Do you recognize this document?"


def test_byline_after_colloquy():
    blocks = [
        _q("Question one?"),
        _a("Yes."),
        _colloquy("MS. ZHAN", "Can we go off the record briefly?"),
        _colloquy("MR. NUNEZ", "Sure."),
        _q("Question two?"),
    ]
    result = apply_byline_resumption(blocks)
    assert result[0].text.startswith("(BY MR. NUNEZ) ")
    assert result[4].text == "(BY MR. NUNEZ) Question two?"


def test_byline_after_oath():
    blocks = [
        _oath(),
        _q("State your full name."),
    ]
    result = apply_byline_resumption(blocks)
    assert result[1].text == "(BY MR. NUNEZ) State your full name."


def test_section_header_byline_suppresses_annotation():
    """A formal BY-line directive (BY MR. NUNEZ:) is itself the
    examiner identification. The next question must NOT get a
    redundant (BY MR. NUNEZ) annotation."""
    blocks = [
        _directive("BY MR. NUNEZ:"),
        _q("Good afternoon. State your name."),
    ]
    result = apply_byline_resumption(blocks)
    assert result[1].text == "Good afternoon. State your name."


def test_section_header_then_recess_then_question():
    """A real recess after a section header DOES re-trigger the
    by-line on the question that resumes examination."""
    blocks = [
        _directive("BY MR. NUNEZ:"),
        _q("Good afternoon."),
        _a("Hi."),
        _directive("(Recess from 1:34 p.m. to 1:35 p.m.)"),
        _q("We're back. Now, where were we?"),
    ]
    result = apply_byline_resumption(blocks)
    assert result[1].text == "Good afternoon."
    assert result[4].text.startswith("(BY MR. NUNEZ) ")


def test_byline_skipped_when_examiner_missing():
    """Better to omit than to render '(BY UNKNOWN)'."""
    blocks = [_q("State your name.", examiner=None)]
    result = apply_byline_resumption(blocks)
    assert result[0].text == "State your name."


def test_byline_skipped_when_examiner_empty_string():
    blocks = [_q("State your name.", examiner="")]
    result = apply_byline_resumption(blocks)
    assert result[0].text == "State your name."


def test_byline_skipped_when_examiner_whitespace_only():
    blocks = [_q("State your name.", examiner="   ")]
    result = apply_byline_resumption(blocks)
    assert result[0].text == "State your name."


def test_answer_block_does_not_reset_state():
    """An answer between two questions does not cause the second
    question to be re-annotated. Q/A oscillation is normal flow,
    not interruption."""
    blocks = [
        _q("First question?"),
        _a("Yes."),
        _q("Second question?"),
    ]
    result = apply_byline_resumption(blocks)
    assert result[0].text.startswith("(BY MR. NUNEZ) ")
    assert result[2].text == "Second question?"


def test_examiner_change_via_new_section_header_suppresses_byline():
    """When a new BY-line section header introduces a different
    examiner mid-deposition (cross-examination begins), the next
    question has no by-line because the header identifies the new
    examiner."""
    blocks = [
        _q("Direct exam Q1?"),
        _a("A1."),
        _directive("BY MS. ZHAN:"),
        TranscriptBlock(
            speaker="MS. ZHAN",
            text="Cross-exam Q1?",
            type="question",
            examiner="MS. ZHAN",
        ),
    ]
    result = apply_byline_resumption(blocks)
    assert result[3].text == "Cross-exam Q1?"


def test_empty_input():
    assert apply_byline_resumption([]) == []


def test_objection_does_not_trigger_byline():
    """Objections are colloquy in this codebase, BUT a single
    colloquy block (a brief objection mid-examination) should not
    cause every following question to be re-annotated.

    The current implementation does treat colloquy as an
    interruption, so a colloquy-typed objection WILL trigger a
    by-line. This test documents that current behavior. If gold
    transcript review shows it produces noisy output, revisit.
    """
    blocks = [
        _q("First question?"),
        _a("Yes."),
        _colloquy("MS. ZHAN", "Objection. Form."),
        _q("Same question, different wording?"),
    ]
    result = apply_byline_resumption(blocks)
    assert result[3].text.startswith("(BY MR. NUNEZ) ")


def test_non_byline_directive_with_by_in_text():
    """A directive whose text contains 'BY' but is not a formal
    section header must still be treated as an interruption."""
    blocks = [
        _q("Question one?"),
        _a("Yes."),
        _directive("(Off the record at 1:34 p.m.)"),
        _q("Question two?"),
    ]
    result = apply_byline_resumption(blocks)
    assert result[3].text.startswith("(BY MR. NUNEZ) ")
