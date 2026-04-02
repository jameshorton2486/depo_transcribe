from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg() -> JobConfig:
    return JobConfig()


def test_orphaned_comma_period_is_collapsed():
    result = clean_block("Love,.", _cfg())[0]
    assert result == "Love."


def test_orphaned_punctuation_in_phrase_is_collapsed():
    result = clean_block("Of course,.", _cfg())[0]
    assert result == "Of course."


def test_inc_comma_is_preserved():
    result = clean_block("Clean Scapes Enterprises, Inc., was retained.", _cfg())[0]
    assert "Inc.," in result


def test_ellipsis_is_preserved():
    result = clean_block("He said . . . then stopped.", _cfg())[0]
    assert ". . ." in result
