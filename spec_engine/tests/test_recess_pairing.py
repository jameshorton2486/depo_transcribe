"""Tests for recess pair collapsing (defect #8)."""

from __future__ import annotations

import pytest

from spec_engine.models import TranscriptBlock
from spec_engine.recess_pairing import (
    _format_clock_time,
    _parse_deposition_start_seconds,
    pair_recess_directives,
)


@pytest.mark.parametrize(
    "start_str,expected_seconds",
    [
        ("8:00 a.m.", 8 * 3600),
        ("10:30 a.m.", 10 * 3600 + 30 * 60),
        ("12:00 p.m.", 12 * 3600),
        ("1:00 p.m.", 13 * 3600),
        ("12:00 a.m.", 0),
        ("11:59 p.m.", 23 * 3600 + 59 * 60),
    ],
)
def test_parse_deposition_start_valid(start_str, expected_seconds):
    assert _parse_deposition_start_seconds(start_str) == expected_seconds


@pytest.mark.parametrize(
    "start_str",
    ["", "garbage", "13:00 p.m.", "8:60 a.m.", "8 a.m."],
)
def test_parse_deposition_start_invalid(start_str):
    assert _parse_deposition_start_seconds(start_str) is None


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (8 * 3600, "8:00 a.m."),
        (10 * 3600 + 30 * 60, "10:30 a.m."),
        (11 * 3600 + 16 * 60, "11:16 a.m."),
        (12 * 3600 + 2 * 60, "12:02 p.m."),
        (13 * 3600 + 21 * 60, "1:21 p.m."),
        (14 * 3600 + 35 * 60, "2:35 p.m."),
        (0, "12:00 a.m."),
    ],
)
def test_format_clock_time(seconds, expected):
    assert _format_clock_time(seconds) == expected


def _q(text: str, words: list[dict] | None = None) -> TranscriptBlock:
    return TranscriptBlock(
        speaker="MR. NUNEZ",
        text=text,
        type="question",
        examiner="MR. NUNEZ",
        words=words,
    )


def _a(text: str, words: list[dict] | None = None) -> TranscriptBlock:
    return TranscriptBlock(
        speaker="THE WITNESS",
        text=text,
        type="answer",
        words=words,
    )


def _directive(text: str, words: list[dict] | None = None) -> TranscriptBlock:
    return TranscriptBlock(
        speaker="",
        text=text,
        type="directive",
        words=words,
    )


def _meta(start_time: str = "8:00 a.m.") -> dict:
    return {"deposition_start_time": start_time}


def test_recess_taken_back_on_record_merges():
    """The canonical pair becomes (Recess from <start> to <end>)."""
    blocks = [
        _directive("(Recess taken.)", words=[{"start": 11760, "end": 11762}]),
        _directive("(Back on the record.)", words=[{"start": 12060, "end": 12062}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 1
    assert result[0].text == "(Recess from 11:16 a.m. to 11:21 a.m.)"
    assert result[0].type == "directive"


def test_off_the_record_merges_to_discussion_form():
    """(Off the record.) -> 'Discussion off the record from...'"""
    blocks = [
        _directive("(Off the record.)", words=[{"start": 19260, "end": 19262}]),
        _directive("(Back on the record.)", words=[{"start": 20100, "end": 20102}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 1
    assert result[0].text == "(Discussion off the record from 1:21 p.m. to 1:35 p.m.)"


def test_discussion_held_off_the_record_merges_to_discussion_form():
    blocks = [
        _directive(
            "(Discussion held off the record.)",
            words=[{"start": 19260, "end": 19262}],
        ),
        _directive(
            "(Back on the record.)",
            words=[{"start": 20100, "end": 20102}],
        ),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 1
    assert result[0].text == (
        "(Discussion off the record from 1:21 p.m. to 1:35 p.m.)"
    )


def test_merge_preserves_surrounding_qa_blocks():
    """Q/A before and after the pair survive in the right order."""
    blocks = [
        _q("First question."),
        _a("Answer."),
        _directive("(Recess taken.)", words=[{"start": 11760, "end": 11762}]),
        _directive("(Back on the record.)", words=[{"start": 12060, "end": 12062}]),
        _q("Next question."),
        _a("Next answer."),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 5
    assert result[0].text == "First question."
    assert result[1].text == "Answer."
    assert result[2].text == "(Recess from 11:16 a.m. to 11:21 a.m.)"
    assert result[3].text == "Next question."
    assert result[4].text == "Next answer."


def test_orphan_opening_without_close_unchanged():
    """An opening with no closing within scope is left alone."""
    blocks = [
        _directive("(Recess taken.)", words=[{"start": 11760}]),
        _q("Some question afterward."),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 2
    assert result[0].text == "(Recess taken.)"
    assert result[1].text == "Some question afterward."


def test_orphan_closing_without_open_unchanged():
    """A closing with no opening before it is left alone."""
    blocks = [
        _directive("(Back on the record.)", words=[{"start": 12060}]),
        _q("Question."),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 2
    assert result[0].text == "(Back on the record.)"


def test_nested_openings_both_left_alone():
    """An opening followed by another opening before any close is ambiguous."""
    blocks = [
        _directive("(Recess taken.)", words=[{"start": 11760}]),
        _directive("(Off the record.)", words=[{"start": 11820}]),
        _directive("(Back on the record.)", words=[{"start": 12060}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert result[0].text == "(Recess taken.)"
    assert "Discussion off the record" in result[1].text


def test_max_pairing_distance_orphans_distant_close():
    """A closing directive more than 40 blocks after the opening is too far."""
    blocks: list[TranscriptBlock] = [
        _directive("(Recess taken.)", words=[{"start": 11760}]),
    ]
    for i in range(41):
        blocks.append(_q(f"Question {i}.", words=[{"start": 11770 + i}]))
    blocks.append(_directive("(Back on the record.)", words=[{"start": 12060}]))
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert result[0].text == "(Recess taken.)"
    assert result[-1].text == "(Back on the record.)"


def test_intervening_blocks_within_pair_preserved():
    """Blocks between a valid pair are preserved, not deleted."""
    blocks = [
        _directive("(Off the record.)", words=[{"start": 19260}]),
        _q("Some off-record speech that got transcribed."),
        _a("And a response."),
        _directive("(Back on the record.)", words=[{"start": 20100}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 3
    assert "Discussion off the record" in result[0].text
    assert result[1].text == "Some off-record speech that got transcribed."
    assert result[2].text == "And a response."


def test_neighbor_fallback_when_directive_words_missing():
    """If directives have no words, immediate neighbors are used."""
    blocks = [
        _q("Last question before break.", words=[{"start": 11700, "end": 11760}]),
        _directive("(Recess taken.)"),
        _directive("(Back on the record.)"),
        _q("Next question.", words=[{"start": 12060, "end": 12065}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 3
    assert result[1].text == "(Recess from 11:16 a.m. to 11:21 a.m.)"


def test_no_words_anywhere_leaves_pair_alone():
    """If neither directives nor neighbors have words, pair stays unmerged."""
    blocks = [
        _q("No timestamps here."),
        _directive("(Recess taken.)"),
        _directive("(Back on the record.)"),
        _q("Also no timestamps."),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 4
    assert result[1].text == "(Recess taken.)"
    assert result[2].text == "(Back on the record.)"


def test_missing_deposition_start_time_leaves_pair_alone():
    """Without a parseable deposition start time, pair stays unmerged."""
    blocks = [
        _directive("(Recess taken.)", words=[{"start": 11760}]),
        _directive("(Back on the record.)", words=[{"start": 12060}]),
    ]
    result = pair_recess_directives(blocks, _meta(""))
    assert len(result) == 2
    assert result[0].text == "(Recess taken.)"


def test_inverted_timestamp_range_leaves_pair_alone():
    """If closing precedes opening, pair is malformed and left alone."""
    blocks = [
        _directive("(Recess taken.)", words=[{"start": 12060}]),
        _directive("(Back on the record.)", words=[{"start": 11760}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 2


def test_already_merged_directive_unchanged():
    """A merged directive doesn't match any trigger and passes through."""
    blocks = [
        _directive("(Recess from 11:16 a.m. to 11:21 a.m.)"),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 1
    assert result[0].text == "(Recess from 11:16 a.m. to 11:21 a.m.)"


def test_idempotent_full_pipeline_run():
    """Running the pass twice produces identical output."""
    blocks = [
        _q("Question before.", words=[{"start": 11700, "end": 11760}]),
        _directive("(Recess taken.)", words=[{"start": 11760, "end": 11762}]),
        _directive("(Back on the record.)", words=[{"start": 12060, "end": 12062}]),
        _q("Question after.", words=[{"start": 12060, "end": 12065}]),
    ]
    first = pair_recess_directives(blocks, _meta("8:00 a.m."))
    second = pair_recess_directives(first, _meta("8:00 a.m."))
    assert [b.text for b in first] == [b.text for b in second]
    assert [b.type for b in first] == [b.type for b in second]


@pytest.mark.parametrize(
    "phrase",
    [
        "(Recess for lunch.)",
        "(Brief recess.)",
        "(We will take a short break.)",
        "(Off record.)",
        "(Discussion off-the-record.)",
        "(Back on record.)",
    ],
)
def test_out_of_scope_phrases_left_alone(phrase):
    """Phrases outside the strict trigger list are not matched."""
    blocks = [
        _directive(phrase, words=[{"start": 11760}]),
        _directive("(Back on the record.)", words=[{"start": 12060}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 2
    assert result[0].text == phrase
    assert result[1].text == "(Back on the record.)"


def test_empty_input():
    assert pair_recess_directives([], _meta("8:00 a.m.")) == []


def test_no_directive_blocks():
    blocks = [_q("Hello."), _a("Hi.")]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert len(result) == 2
    assert result[0].text == "Hello."


def test_none_case_meta():
    """A None case_meta is treated as empty -- no merging."""
    blocks = [
        _directive("(Recess taken.)", words=[{"start": 11760}]),
        _directive("(Back on the record.)", words=[{"start": 12060}]),
    ]
    result = pair_recess_directives(blocks, None)
    assert len(result) == 2
    assert result[0].text == "(Recess taken.)"


def test_shaw_recess_at_11_16():
    """Mirrors the Shaw deposition: Recess from 11:16 a.m. to 11:21 a.m."""
    blocks = [
        _directive("(Recess taken.)", words=[{"start": 11760}]),
        _directive("(Back on the record.)", words=[{"start": 12060}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert result[0].text == "(Recess from 11:16 a.m. to 11:21 a.m.)"


def test_shaw_off_record_at_1_21():
    """Mirrors the Shaw deposition: Discussion off the record from 1:21 p.m. to 1:35 p.m."""
    blocks = [
        _directive("(Off the record.)", words=[{"start": 19260}]),
        _directive("(Back on the record.)", words=[{"start": 20100}]),
    ]
    result = pair_recess_directives(blocks, _meta("8:00 a.m."))
    assert result[0].text == (
        "(Discussion off the record from 1:21 p.m. to 1:35 p.m.)"
    )
