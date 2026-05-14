"""Tests for money and percent normalization (defect #5)."""

import pytest

from spec_engine.models import TranscriptBlock
from spec_engine.money_and_percent import (
    _normalize_text,
    _parse_spoken_amount,
    normalize_money_and_percent,
)


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("twenty", 20),
        ("twenty-five", 25),
        ("twenty five", 25),
        ("one hundred", 100),
        ("two hundred", 200),
        ("two hundred fifty", 250),
        ("two hundred and fifty", 250),
        ("one thousand", 1000),
        ("two thousand", 2000),
        ("two thousand and fifty", 2050),
        ("two thousand five hundred", 2500),
        ("two thousand five hundred and twenty-five", 2525),
        ("100", 100),
        ("20", 20),
        ("2,500", 2500),
    ],
)
def test_parse_spoken_amount_valid(spoken, expected):
    assert _parse_spoken_amount(spoken) == expected


@pytest.mark.parametrize(
    "spoken",
    ["", "thousand", "hundred and", "garbage", "twenty hundred"],
)
def test_parse_spoken_amount_invalid(spoken):
    assert _parse_spoken_amount(spoken) is None


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("He paid twenty dollars.", "He paid $20."),
        ("That cost twenty-five dollars.", "That cost $25."),
        ("She owed one hundred dollars.", "She owed $100."),
        ("The total was two thousand dollars.", "The total was $2,000."),
        ("Two hundred fifty dollars was the agreed amount.", "$250 was the agreed amount."),
    ],
)
def test_rule_189_basic_dollars(input_text, expected):
    assert _normalize_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("She paid thirty cents.", "She paid 30 cents."),
        ("It was eighty-nine cents.", "It was 89 cents."),
        ("Only five cents in change.", "Only 5 cents in change."),
    ],
)
def test_rule_191_cents_only(input_text, expected):
    assert _normalize_text(input_text) == expected


def test_cents_idiom_on_the_dollar_suppressed():
    """'cents on the dollar' is an idiom and must not convert."""
    assert _normalize_text(
        "Settlement paid thirty cents on the dollar."
    ) == "Settlement paid thirty cents on the dollar."


def test_cents_idiom_variation_not_suppressed():
    """Exact-phrase suppression: 'on each dollar' is not caught and converts."""
    assert _normalize_text(
        "Settlement paid thirty cents on each dollar."
    ) == "Settlement paid 30 cents on each dollar."


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("Twenty dollars and fifty cents.", "$20.50."),
        ("Eighty-nine dollars and ninety-nine cents.", "$89.99."),
        ("One hundred dollars and five cents.", "$100.05."),
        ("Two thousand dollars and twenty-five cents in damages.", "$2,000.25 in damages."),
    ],
)
def test_rule_193_dollars_and_cents(input_text, expected):
    assert _normalize_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("The settlement was two million dollars.", "The settlement was $2 million."),
        ("Damages totaled fifty million dollars.", "Damages totaled $50 million."),
        ("The deal was worth three billion dollars.", "The deal was worth $3 billion."),
    ],
)
def test_rule_194_scale_definite(input_text, expected):
    assert _normalize_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text",
    [
        "He had a million dollars in the bank.",
        "Several million dollars went missing.",
        "Many billion dollars in revenue.",
        "Some million dollars were unaccounted for.",
        "An million dollars.",
    ],
)
def test_rule_195_indefinite_unchanged(input_text):
    assert _normalize_text(input_text) == input_text


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("He won by fifty percent.", "He won by 50 percent."),
        ("She owns twenty-five percent.", "She owns 25 percent."),
        ("The interest was one hundred percent.", "The interest was 100 percent."),
        ("About five percent of the witnesses.", "About 5 percent of the witnesses."),
    ],
)
def test_rule_199_percent(input_text, expected):
    assert _normalize_text(input_text) == expected


@pytest.mark.parametrize(
    "input_text",
    [
        "I have twenty apples.",
        "She is fifty-six years old.",
        "The meeting was at three p.m.",
        "Two-thirds of the witnesses agreed.",
        "The second time he visited.",
        "It was the eighteenth century.",
        "The package weighed five pounds.",
        "$20 was the price.",
        "50% was the rate.",
        "Half a million dollars.",
        "About a quarter million in damages.",
    ],
)
def test_out_of_scope_unchanged(input_text):
    assert _normalize_text(input_text) == input_text


@pytest.mark.parametrize(
    "input_text",
    [
        "He paid twenty dollars.",
        "Twenty dollars and fifty cents.",
        "Two million dollars in damages.",
        "Fifty percent of the witnesses.",
        "$20",
        "$2,000.50",
        "50 percent",
        "30 cents",
    ],
)
def test_idempotent(input_text):
    once = _normalize_text(input_text)
    twice = _normalize_text(once)
    assert once == twice


def test_multiple_money_expressions_in_one_text():
    """Multiple separate money expressions all convert."""
    assert _normalize_text(
        "He paid twenty dollars and she paid thirty dollars."
    ) == "He paid $20 and she paid $30."


def test_dollars_and_cents_takes_precedence_over_basic_dollars():
    """The dollars+cents pattern matches first."""
    assert _normalize_text(
        "He paid twenty dollars and fifty cents for the item."
    ) == "He paid $20.50 for the item."


def test_money_and_percent_in_same_text():
    """Different rule classes in one sentence both convert."""
    assert _normalize_text(
        "He paid twenty dollars at fifty percent interest."
    ) == "He paid $20 at 50 percent interest."


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
    assert normalize_money_and_percent([]) == []


def test_normalize_blocks_preserves_metadata():
    block = TranscriptBlock(
        speaker="THE WITNESS",
        text="I paid twenty dollars for it.",
        type="answer",
        source_type="diarized",
        examiner=None,
        words=[{"word": "I", "start": 1.0}],
    )
    result = normalize_money_and_percent([block])
    assert len(result) == 1
    assert result[0].text == "I paid $20 for it."
    assert result[0].speaker == "THE WITNESS"
    assert result[0].type == "answer"
    assert result[0].source_type == "diarized"
    assert result[0].examiner is None
    assert result[0].words == [{"word": "I", "start": 1.0}]


def test_normalize_blocks_passes_through_unchanged_text():
    """A block with no money/percent text returns the SAME object."""
    block = _q("Did you see the vehicle?")
    result = normalize_money_and_percent([block])
    assert len(result) == 1
    assert result[0] is block


def test_normalize_blocks_answers_also_converted():
    blocks = [
        _q("How much did the repair cost?"),
        _a("About two hundred dollars."),
    ]
    result = normalize_money_and_percent(blocks)
    assert result[1].text == "About $200."


def test_normalize_blocks_preserves_block_count_and_order():
    blocks = [
        _q("How much?"),
        _a("Twenty dollars."),
        _q("And the rate?"),
        _a("Five percent."),
    ]
    result = normalize_money_and_percent(blocks)
    assert len(result) == 4
    assert result[0].text == "How much?"
    assert result[1].text == "$20."
    assert result[2].text == "And the rate?"
    assert result[3].text == "5 percent."


def test_thomas_shaped_damages_amount():
    block = _q(
        "Mr. Thomas, were you aware that the total damages exceeded "
        "two million dollars in this matter?"
    )
    result = normalize_money_and_percent([block])
    assert result[0].text == (
        "Mr. Thomas, were you aware that the total damages exceeded "
        "$2 million in this matter?"
    )


def test_thomas_shaped_interest_rate():
    block = _a(
        "I believe the interest rate was about five percent at that time."
    )
    result = normalize_money_and_percent([block])
    assert result[0].text == (
        "I believe the interest rate was about 5 percent at that time."
    )
