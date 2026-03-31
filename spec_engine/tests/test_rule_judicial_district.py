"""
spec_engine/tests/test_rule_judicial_district.py

Tests for 408th Judicial District garble correction.
All offline and deterministic.
Run: python -m pytest spec_engine/tests/test_rule_judicial_district.py -v
"""
import pytest
from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg():
    cfg = JobConfig()
    cfg.confirmed_spellings = {}
    return cfg


class TestHappyPath:

    def test_digit_by_digit(self):
        result = clean_block(
            "in the 4 0 8 Judicial District.", _cfg())[0]
        assert "408th Judicial District" in result

    def test_digit_by_digit_with_th(self):
        result = clean_block(
            "in the 4 0 8th Judicial District.", _cfg())[0]
        assert "408th Judicial District" in result

    def test_four_o_eight(self):
        result = clean_block(
            "in the four o eight Judicial District.", _cfg())[0]
        assert "408th Judicial District" in result

    def test_four_zero_eight(self):
        result = clean_block(
            "in the four zero eight Judicial District.", _cfg())[0]
        assert "408th Judicial District" in result

    def test_408_without_th(self):
        result = clean_block(
            "in the 408 Judicial District.", _cfg())[0]
        assert "408th Judicial District" in result

    def test_already_correct_unchanged(self):
        result = clean_block(
            "in the 408th Judicial District.", _cfg())[0]
        assert "408th Judicial District" in result
        assert "408th Judicial District Judicial District" not in result


class TestFalsePositiveGuard:

    def test_408_alone_unchanged(self):
        result = clean_block("The room is 408.", _cfg())[0]
        assert "408th Judicial District" not in result

    def test_four_zero_eight_no_judicial(self):
        result = clean_block("four zero eight people attended.", _cfg())[0]
        assert "408th Judicial District" not in result


class TestPunctuationBoundary:

    def test_in_full_preamble_context(self):
        text = ("Cause Number 2025CI19595, in the 4 0 8 Judicial District, "
                "Bexar County, Texas.")
        result = clean_block(text, _cfg())[0]
        assert "408th Judicial District" in result
        assert "Bexar County" in result


class TestPassOrdering:

    def test_correction_recorded(self):
        result, records, _ = clean_block(
            "in the 4 0 8 Judicial District.", _cfg())
        assert "408th Judicial District" in result
        assert len(records) >= 1


class TestInterface:

    def test_returns_string(self):
        result = clean_block("4 0 8 Judicial District.", _cfg())[0]
        assert isinstance(result, str)
