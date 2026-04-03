"""
Tests for Phase 7E date and time normalization.
Generic rules — apply to any Texas deposition.
"""

from spec_engine.corrections import (
    _spoken_year_to_int,
    fix_spoken_dates,
    fix_spoken_times,
)


def test_spoken_year_twenty_twenty_four():
    assert _spoken_year_to_int("twenty twenty four") == "2024"


def test_spoken_year_twenty_twenty_five():
    assert _spoken_year_to_int("twenty twenty five") == "2025"


def test_spoken_year_nineteen_ninety_five():
    assert _spoken_year_to_int("nineteen ninety five") == "1995"


def test_spoken_year_two_thousand_thirteen():
    assert _spoken_year_to_int("two thousand thirteen") == "2013"


def test_fix_spoken_dates_march():
    assert "03/23/2024" in fix_spoken_dates("March twenty third twenty twenty four")


def test_fix_spoken_dates_february():
    assert "02/11/2025" in fix_spoken_dates("February eleventh twenty twenty five")


def test_fix_spoken_dates_november():
    assert "11/18/1995" in fix_spoken_dates("November eighteenth nineteen ninety five")


def test_fix_spoken_dates_preserves_numeric():
    assert "03/23/2024" in fix_spoken_dates("accident on 03/23/2024")


def test_fix_spoken_times_ten_o_five_am():
    assert "10:05 a.m." in fix_spoken_times("The time is ten o five AM")


def test_fix_spoken_times_eleven_eleven_am():
    assert "11:11 a.m." in fix_spoken_times("The time is eleven eleven AM")


def test_fix_spoken_times_eleven_thirty_three():
    assert "11:33 a.m." in fix_spoken_times("time is eleven thirty three AM")


def test_fix_spoken_times_normalizes_compact():
    assert "10:05 a.m." in fix_spoken_times("The time is 10:05AM")


def test_fix_spoken_times_pm():
    assert "2:30 p.m." in fix_spoken_times("ended at two thirty PM")


def test_fix_spoken_dates_no_false_positive():
    assert fix_spoken_dates("I saw her in March") == "I saw her in March"
