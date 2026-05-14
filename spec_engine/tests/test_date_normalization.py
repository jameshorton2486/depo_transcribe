"""Tests for date and year normalization (defect #4)."""

import pytest

from spec_engine.date_normalization import (
    _normalize_text,
    _parse_day_form,
    _parse_year_form,
    normalize_dates_and_years,
)
from spec_engine.models import TranscriptBlock


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("nineteen sixty-eight", 1968),
        ("nineteen ninety-five", 1995),
        ("nineteen ninety five", 1995),
        ("nineteen hundred and ninety-seven", 1997),
        ("nineteen hundred ninety-seven", 1997),
        ("two thousand", 2000),
        ("two thousand four", 2004),
        ("two thousand and four", 2004),
        ("two thousand twenty-four", 2024),
        ("twenty twenty-four", 2024),
        ("twenty twenty", 2020),
        ("1968", 1968),
        ("2024", 2024),
    ],
)
def test_parse_year_form_valid(spoken, expected):
    assert _parse_year_form(spoken) == expected


@pytest.mark.parametrize(
    "spoken",
    ["", "nineteen", "twenty", "three thousand", "garbage words here"],
)
def test_parse_year_form_invalid(spoken):
    assert _parse_year_form(spoken) is None


@pytest.mark.parametrize(
    "spoken,expected_value,expected_was_ordinal",
    [
        ("first", 1, True),
        ("seventh", 7, True),
        ("twentieth", 20, True),
        ("twenty-first", 21, True),
        ("twenty first", 21, True),
        ("thirty-first", 31, True),
        ("one", 1, False),
        ("seven", 7, False),
        ("twenty-four", 24, False),
        ("twenty four", 24, False),
        ("thirty one", 31, False),
    ],
)
def test_parse_day_form_valid(spoken, expected_value, expected_was_ordinal):
    assert _parse_day_form(spoken) == (expected_value, expected_was_ordinal)


@pytest.mark.parametrize(
    "spoken",
    ["", "thirty-two", "thirty two", "fortieth", "zero", "garbage"],
)
def test_parse_day_form_invalid(spoken):
    assert _parse_day_form(spoken) is None


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("May seventh, nineteen sixty-eight", "May 7, 1968"),
        (
            "On May seventh, nineteen sixty-eight, did you visit?",
            "On May 7, 1968, did you visit?",
        ),
        ("January first, two thousand twenty-four was a Monday.", "January 1, 2024 was a Monday."),
        ("December thirty-first, nineteen ninety-nine", "December 31, 1999"),
        ("February twenty-ninth, two thousand twenty", "February 29, 2020"),
        ("May seven, nineteen sixty-eight", "May 7, 1968"),
        ("She arrived on May seventh.", "She arrived on May 7."),
        ("It was nineteen sixty-eight when I last saw him.", "It was 1968 when I last saw him."),
    ],
)
def test_standard_date_conversion(input_text, expected):
    assert _normalize_text(input_text) == expected


def test_standard_date_already_digit_strips_ordinal_suffix():
    assert _normalize_text("May 7th, 1968") == "May 7, 1968"
    assert _normalize_text("May 7th") == "May 7"
    assert _normalize_text("December 31st, 1999") == "December 31, 1999"


def test_standard_date_month_casing_normalized():
    assert _normalize_text("may seventh, nineteen sixty-eight") == "May 7, 1968"
    assert _normalize_text("MAY seventh") == "May 7"


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("the seventh of May, nineteen sixty-eight", "the 7th of May, 1968"),
        ("the seventh of May", "the 7th of May"),
        ("the twenty-first of June, two thousand twenty-four", "the 21st of June, 2024"),
        ("the second of November", "the 2nd of November"),
        ("the third of March, nineteen ninety-five", "the 3rd of March, 1995"),
        ("the seven of May", "the 7th of May"),
    ],
)
def test_day_of_month_conversion(input_text, expected):
    assert _normalize_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("It was nineteen sixty-eight when I last saw him.", "It was 1968 when I last saw him."),
        ("From nineteen sixty-eight to nineteen seventy-two.", "From 1968 to 1972."),
        ("In two thousand twenty-four we filed.", "In 2024 we filed."),
        ("In two thousand we celebrated.", "In 2000 we celebrated."),
        ("I started working there in nineteen hundred and ninety-seven.", "I started working there in 1997."),
    ],
)
def test_standalone_year_conversion(input_text, expected):
    assert _normalize_text(input_text) == expected


def test_twenty_nn_with_preposition_signals_year():
    assert _normalize_text("In twenty twenty-four we filed.") == "In 2024 we filed."
    assert _normalize_text("On twenty twenty we celebrated.") == "On 2020 we celebrated."
    assert _normalize_text("During twenty twenty-three.") == "During 2023."


def test_twenty_nn_with_month_signals_year():
    assert _normalize_text("It was twenty twenty-four in May.") == "It was 2024 in May."


def test_twenty_nn_without_signals_does_not_convert():
    assert _normalize_text("I bought twenty twenty-four-ounce bottles.") == (
        "I bought twenty twenty-four-ounce bottles."
    )
    assert _normalize_text("There were twenty twenty-five people there.") == (
        "There were twenty twenty-five people there."
    )
    assert _normalize_text("I think it was twenty twenty-four when I saw it last.") == (
        "I think it was twenty twenty-four when I saw it last."
    )


def test_twenty_nn_in_full_date_context_converts():
    assert _normalize_text("May seventh, twenty twenty-four") == "May 7, 2024"


@pytest.mark.parametrize(
    "input_text",
    [
        "I have twenty-four apples.",
        "She is fifty-six years old.",
        "He paid twenty dollars.",
        "We won by fifty percent.",
        "The meeting was at three p.m.",
        "Two-thirds of the witnesses agreed.",
        "The second time he visited.",
        "It was the eighteenth century.",
        "We spoke for ten minutes.",
        "The package weighed five pounds.",
    ],
)
def test_out_of_scope_unchanged(input_text):
    assert _normalize_text(input_text) == input_text


@pytest.mark.parametrize(
    "input_text",
    [
        "May seventh, nineteen sixty-eight",
        "the twenty-first of June, two thousand twenty-four",
        "In nineteen sixty-eight we moved.",
        "May 7, 1968",
        "the 7th of May, 1968",
        "It was 2024 when I saw it.",
    ],
)
def test_idempotent(input_text):
    once = _normalize_text(input_text)
    twice = _normalize_text(once)
    assert once == twice


def _q(text: str) -> TranscriptBlock:
    return TranscriptBlock(
        speaker="MR. NUNEZ",
        text=text,
        type="question",
        examiner="MR. NUNEZ",
    )


def _a(text: str) -> TranscriptBlock:
    return TranscriptBlock(speaker="THE WITNESS", text=text, type="answer")


def test_normalize_blocks_empty():
    assert normalize_dates_and_years([]) == []


def test_normalize_blocks_preserves_metadata():
    block = TranscriptBlock(
        speaker="MR. NUNEZ",
        text="On May seventh, nineteen sixty-eight, did you visit?",
        type="question",
        source_type="diarized",
        examiner="MR. NUNEZ",
        words=[{"word": "On", "start": 1.0}],
    )
    result = normalize_dates_and_years([block])
    assert len(result) == 1
    assert result[0].text == "On May 7, 1968, did you visit?"
    assert result[0].speaker == "MR. NUNEZ"
    assert result[0].type == "question"
    assert result[0].source_type == "diarized"
    assert result[0].examiner == "MR. NUNEZ"
    assert result[0].words == [{"word": "On", "start": 1.0}]


def test_normalize_blocks_passes_through_unchanged_text():
    block = _q("Did you see the vehicle?")
    result = normalize_dates_and_years([block])
    assert len(result) == 1
    assert result[0] is block


def test_normalize_blocks_answers_also_converted():
    blocks = [
        _q("When did you last visit the property?"),
        _a("I think it was in two thousand twenty-four."),
    ]
    result = normalize_dates_and_years(blocks)
    assert result[1].text == "I think it was in 2024."
    assert result[1].type == "answer"


def test_normalize_blocks_multiple_dates_per_block():
    block = _q("From nineteen sixty-eight to nineteen seventy-two, did you work there?")
    result = normalize_dates_and_years([block])
    assert result[0].text == "From 1968 to 1972, did you work there?"


def test_normalize_blocks_preserves_block_count_and_order():
    blocks = [
        _q("On May seventh, nineteen sixty-eight, did you visit?"),
        _a("Yes."),
        _q("And in two thousand twenty-four?"),
        _a("No."),
    ]
    result = normalize_dates_and_years(blocks)
    assert len(result) == 4
    assert result[0].type == "question"
    assert result[1].type == "answer"
    assert result[2].type == "question"
    assert result[3].type == "answer"
    assert result[0].text == "On May 7, 1968, did you visit?"
    assert result[2].text == "And in 2024?"


def test_thomas_shaped_examination_date():
    block = _q(
        "Mr. Thomas, on the seventh of May, two thousand twenty-four, "
        "were you operating the vehicle in question?"
    )
    result = normalize_dates_and_years([block])
    assert result[0].text == (
        "Mr. Thomas, on the 7th of May, 2024, "
        "were you operating the vehicle in question?"
    )


def test_thomas_shaped_year_range():
    block = _a("I lived at that address from nineteen ninety-five to two thousand and four.")
    result = normalize_dates_and_years([block])
    assert result[0].text == "I lived at that address from 1995 to 2004."
