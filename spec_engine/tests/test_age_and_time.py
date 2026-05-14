"""Tests for age and time normalization (defect #6)."""

import pytest

from spec_engine.age_and_time import (
    _normalize_text,
    _parse_cardinal,
    _parse_minute,
    normalize_ages_and_times,
)
from spec_engine.models import TranscriptBlock


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("fifty-six", 56),
        ("fifty six", 56),
        ("forty", 40),
        ("one hundred", 100),
        ("one hundred and five", 105),
        ("one hundred and nineteen", 119),
        ("twelve", 12),
        ("one", 1),
    ],
)
def test_parse_cardinal_valid(spoken, expected):
    assert _parse_cardinal(spoken) == expected


@pytest.mark.parametrize(
    "spoken",
    ["", "garbage", "hundred", "two hundred"],
)
def test_parse_cardinal_invalid(spoken):
    assert _parse_cardinal(spoken) is None


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("thirty", 30),
        ("fifteen", 15),
        ("oh five", 5),
        ("oh-five", 5),
        ("oh nine", 9),
        ("zero", 0),
        ("fifty-nine", 59),
    ],
)
def test_parse_minute_valid(spoken, expected):
    assert _parse_minute(spoken) == expected


@pytest.mark.parametrize(
    "spoken",
    ["", "sixty", "garbage", "oh ten"],
)
def test_parse_minute_invalid(spoken):
    assert _parse_minute(spoken) is None


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("She is fifty-six years old.", "She is 56 years old."),
        ("He was forty years old at the time.", "He was 40 years old at the time."),
        ("She was forty years of age.", "She was 40 years of age."),
        ("The witness, age forty, took the stand.", "The witness, age 40, took the stand."),
        ("One hundred years old.", "100 years old."),
        ("Ninety-nine years old.", "99 years old."),
        ("She was one year old.", "She was 1 year old."),
    ],
)
def test_rule_175_ages(input_text, expected):
    assert _normalize_text(input_text) == expected


def test_age_out_of_range_unchanged():
    """Ages over 120 are not converted."""
    assert _normalize_text("She is one hundred and nineteen years old.") == (
        "She is 119 years old."
    )


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("The meeting was at three p.m.", "The meeting was at 3 p.m."),
        ("She arrived at nine a.m.", "She arrived at 9 a.m."),
        ("It was twelve p.m. when he called.", "It was 12 p.m. when he called."),
        ("The meeting was at three thirty p.m.", "The meeting was at 3:30 p.m."),
        ("She arrived at nine fifteen a.m.", "She arrived at 9:15 a.m."),
        ("It was twelve oh-five p.m. when he called.", "It was 12:05 p.m. when he called."),
        ("Around three-fifteen a.m.", "Around 3:15 a.m."),
        ("At three P.M.", "At 3 p.m."),
        ("At three PM.", "At 3 p.m.."),
    ],
)
def test_rule_184_time_with_ampm(input_text, expected):
    assert _normalize_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("We met at twelve noon.", "We met at 12 noon."),
        ("It was twelve midnight when I left.", "It was 12 midnight when I left."),
    ],
)
def test_rule_185_twelve_noon_midnight(input_text, expected):
    assert _normalize_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text",
    [
        "We met at noon.",
        "It was midnight when I left.",
    ],
)
def test_rule_185_bare_noon_midnight_unchanged(input_text):
    """Bare noon/midnight already function as time markers."""
    assert _normalize_text(input_text) == input_text


@pytest.mark.parametrize(
    "input_text",
    [
        "We met at three o'clock.",
        "It was ten o'clock when I left.",
        "Around twelve o'clock.",
    ],
)
def test_rule_187_oclock_unchanged(input_text):
    assert _normalize_text(input_text) == input_text


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("Briefing at fifteen hundred hours.", "Briefing at 1500 hours."),
        ("The call came in at oh-three hundred hours.", "The call came in at 0300 hours."),
        ("Departure was at twenty-three thirty hours.", "Departure was at 2330 hours."),
        ("At oh-three fifteen hours.", "At 0315 hours."),
    ],
)
def test_rule_188_military_time(input_text, expected):
    assert _normalize_text(input_text) == expected


def test_bare_hour_minute_without_marker_unchanged():
    """Without an anchor, the bare form passes through unchanged."""
    assert _normalize_text("Three thirty bags were stacked.") == (
        "Three thirty bags were stacked."
    )


def test_bare_hour_minute_with_ampm_anchor_converts():
    """With an a.m./p.m. anchor, conversion fires."""
    assert _normalize_text("I called at three thirty p.m.") == "I called at 3:30 p.m."


@pytest.mark.parametrize(
    "input_text",
    [
        "I have twenty apples.",
        "He paid twenty dollars.",
        "We won by fifty percent.",
        "Two-thirds of the witnesses agreed.",
        "The second time he visited.",
        "It was the eighteenth century.",
        "The package weighed five pounds.",
        "We spoke for ten minutes.",
        "3 p.m.",
        "3:30 p.m.",
        "56 years old",
        "12 noon",
        "1500 hours",
    ],
)
def test_out_of_scope_unchanged(input_text):
    assert _normalize_text(input_text) == input_text


@pytest.mark.parametrize(
    "input_text",
    [
        "She is fifty-six years old.",
        "The meeting was at three p.m.",
        "The meeting was at three thirty p.m.",
        "We met at twelve noon.",
        "We met at three o'clock.",
        "Briefing at fifteen hundred hours.",
        "56 years old",
        "3 p.m.",
        "3:30 p.m.",
        "12 noon",
        "1500 hours",
    ],
)
def test_idempotent(input_text):
    once = _normalize_text(input_text)
    twice = _normalize_text(once)
    assert once == twice


def test_age_and_time_in_same_text():
    """Different rule classes in one sentence both convert."""
    assert _normalize_text(
        "She was fifty-six years old when the call came at three p.m."
    ) == "She was 56 years old when the call came at 3 p.m."


def test_oclock_inhibits_only_its_own_phrase():
    """An o'clock phrase suppresses itself, but other times still convert."""
    assert _normalize_text(
        "Met at three o'clock, then again at nine thirty p.m."
    ) == "Met at three o'clock, then again at 9:30 p.m."


def test_multiple_ages_in_one_text():
    assert _normalize_text(
        "The plaintiff is fifty-six years old; the defendant is forty years old."
    ) == "The plaintiff is 56 years old; the defendant is 40 years old."


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
    assert normalize_ages_and_times([]) == []


def test_normalize_blocks_preserves_metadata():
    block = TranscriptBlock(
        speaker="THE WITNESS",
        text="I was fifty-six years old at the time.",
        type="answer",
        source_type="diarized",
        examiner=None,
        words=[{"word": "I", "start": 1.0}],
    )
    result = normalize_ages_and_times([block])
    assert len(result) == 1
    assert result[0].text == "I was 56 years old at the time."
    assert result[0].speaker == "THE WITNESS"
    assert result[0].type == "answer"
    assert result[0].source_type == "diarized"
    assert result[0].examiner is None
    assert result[0].words == [{"word": "I", "start": 1.0}]


def test_normalize_blocks_passes_through_unchanged_text():
    block = _q("Did you see the vehicle?")
    result = normalize_ages_and_times([block])
    assert len(result) == 1
    assert result[0] is block


def test_normalize_blocks_answers_also_converted():
    blocks = [
        _q("How old were you?"),
        _a("I was fifty-six years old at three p.m."),
    ]
    result = normalize_ages_and_times(blocks)
    assert result[1].text == "I was 56 years old at 3 p.m."


def test_normalize_blocks_preserves_block_count_and_order():
    blocks = [
        _q("How old?"),
        _a("Forty."),
        _q("And what time?"),
        _a("Three p.m."),
    ]
    result = normalize_ages_and_times(blocks)
    assert len(result) == 4
    assert result[0].text == "How old?"
    assert result[1].text == "Forty."
    assert result[2].text == "And what time?"
    assert result[3].text == "3 p.m."


def test_thomas_shaped_witness_age():
    block = _a("I was fifty-six years old at the time of the accident.")
    result = normalize_ages_and_times([block])
    assert result[0].text == "I was 56 years old at the time of the accident."


def test_thomas_shaped_accident_time():
    block = _a(
        "The accident occurred at approximately three thirty p.m. "
        "that afternoon."
    )
    result = normalize_ages_and_times([block])
    assert result[0].text == (
        "The accident occurred at approximately 3:30 p.m. that afternoon."
    )
