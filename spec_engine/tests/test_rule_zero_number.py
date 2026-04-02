from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg() -> JobConfig:
    return JobConfig()


def test_zero_count_converts_to_word():
    result = clean_block("There were 0 witnesses present.", _cfg())[0]
    assert "zero witnesses" in result.lower()


def test_zero_at_sentence_start_converts_to_capitalized_word():
    result = clean_block("0 witnesses were present.", _cfg())[0]
    assert result.startswith("Zero witnesses")


def test_zero_does_not_break_exhibit_number_formatting():
    result = clean_block("I marked exhibit 0 for identification.", _cfg())[0]
    assert "Exhibit No. 0" in result


def test_zero_does_not_break_time_formatting():
    result = clean_block("The time was 10:08 AM and there were 0 witnesses.", _cfg())[0]
    assert "10:08 a.m." in result
    assert "zero witnesses" in result.lower()

