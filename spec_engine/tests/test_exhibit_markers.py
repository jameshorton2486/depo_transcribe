"""Tests for exhibit-marker emission (defect #1)."""

from spec_engine.exhibit_markers import emit_exhibit_markers
from spec_engine.models import TranscriptBlock


def _b(text: str, type_: str = "question") -> TranscriptBlock:
    return TranscriptBlock(speaker="", text=text, type=type_)


def test_plaintiffs_exhibit_digit():
    blocks = [_b("I'm going to mark this as Plaintiff's Exhibit 1.")]
    result = emit_exhibit_markers(blocks)
    assert len(result) == 2
    assert result[0] == blocks[0]
    assert result[1].type == "directive"
    assert result[1].text == "(Exhibit 1 marked)"


def test_defendants_exhibit():
    blocks = [_b("I'm introducing this as Defendant's Exhibit 5.")]
    result = emit_exhibit_markers(blocks)
    assert len(result) == 2
    assert result[1].text == "(Exhibit 5 marked)"


def test_letter_exhibit_uppercased():
    blocks = [_b("Mark this as Exhibit b please.")]
    result = emit_exhibit_markers(blocks)
    assert len(result) == 2
    assert result[1].text == "(Exhibit B marked)"


def test_reference_does_not_trigger():
    """Looking at / referring to is a reference, not an introduction."""
    blocks = [_b("Looking at Exhibit 1, can you describe what you see?")]
    result = emit_exhibit_markers(blocks)
    assert len(result) == 1


def test_last_number_wins_on_self_correction():
    blocks = [_b(
        "I'm going to introduce Plaintiff's Exhibit 8. "
        "I introduced an exhibit like this... This one is exhibit A. "
        "Actually, it's this one, sorry. This one is exhibit 8."
    )]
    result = emit_exhibit_markers(blocks)
    assert len(result) == 2
    assert result[1].text == "(Exhibit 8 marked)"


def test_idempotent():
    """Running the pass twice does not duplicate markers."""
    blocks = [_b("Mark this as Plaintiff's Exhibit 1.")]
    once = emit_exhibit_markers(blocks)
    twice = emit_exhibit_markers(once)
    assert [(b.type, b.text) for b in once] == [(b.type, b.text) for b in twice]


def test_existing_marker_not_duplicated():
    """An existing exhibit-marker block already in the input is
    recognized and no second marker is emitted."""
    blocks = [
        _b("Mark this as Plaintiff's Exhibit 1."),
        TranscriptBlock(speaker="", text="(Exhibit 1 marked)", type="directive"),
        _b("Yes.", type_="answer"),
    ]
    result = emit_exhibit_markers(blocks)
    assert len(result) == 3
    assert result[1].text == "(Exhibit 1 marked)"


def test_empty_input():
    assert emit_exhibit_markers([]) == []


def test_non_introducing_question_unchanged():
    blocks = [_b("How many exhibits did you review?")]
    result = emit_exhibit_markers(blocks)
    assert len(result) == 1


def test_marker_emitted_block_has_directive_type():
    """The emitted marker must be type='directive' so the emitter
    formats it correctly."""
    blocks = [_b("Mark this as Plaintiff's Exhibit 1.")]
    result = emit_exhibit_markers(blocks)
    assert result[1].type == "directive"
    assert result[1].speaker == ""
