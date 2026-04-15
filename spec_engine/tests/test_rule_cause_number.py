"""
spec_engine/tests/test_rule_cause_number.py

Tests for Cause Number garble correction.
All offline and deterministic.
Run: python -m pytest spec_engine/tests/test_rule_cause_number.py -v
"""
import pytest
from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg():
    cfg = JobConfig()
    cfg.confirmed_spellings = {}
    return cfg


class TestHappyPath:

    def test_caught_number_corrected(self):
        result = clean_block("This is caught number 2025CI19595.", _cfg())[0]
        assert "Cause Number" in result

    def test_cause_numbers_singular(self):
        result = clean_block("cause numbers 2025CI19595.", _cfg())[0]
        assert "Cause Number" in result
        assert "cause numbers" not in result.lower()

    def test_already_correct_unchanged(self):
        result = clean_block("This is Cause Number 2025CI19595.", _cfg())[0]
        assert "Cause Number" in result
        assert "Cause Number Number" not in result


class TestFalsePositiveGuard:

    def test_cop_alone_unchanged(self):
        result = clean_block("The cop arrived at the scene.", _cfg())[0]
        assert "Cause Number" not in result

    def test_cop_number_phrase_unchanged(self):
        result = clean_block("The cop number on the badge was 217.", _cfg())[0]
        assert "Cause Number" not in result
        assert "cop number" in result.lower()

    def test_number_alone_unchanged(self):
        result = clean_block("The number was three.", _cfg())[0]
        assert "Cause Number" not in result

    def test_cost_number_phrase_unchanged(self):
        result = clean_block("The cost number was on the invoice.", _cfg())[0]
        assert "Cause Number" not in result
        assert "cost number" in result.lower()


class TestPunctuationBoundary:

    def test_caught_number_in_full_preamble(self):
        text = "This is caught number 2025CI19595 in the District Court."
        result = clean_block(text, _cfg())[0]
        assert "Cause Number" in result
        assert "District Court" in result


class TestPassOrdering:

    def test_correction_recorded(self):
        result, records, _ = clean_block("This is caught number 2025CI19595.", _cfg())
        assert "Cause Number" in result
        assert len(records) >= 1


class TestInterface:

    def test_returns_string(self):
        assert isinstance(clean_block("caught number 12345.", _cfg())[0], str)
