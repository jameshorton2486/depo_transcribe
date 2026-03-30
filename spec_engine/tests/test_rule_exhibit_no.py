"""
spec_engine/tests/test_rule_exhibit_no.py

Tests for Exhibit No. formatting rule — Morson's Rule 217.
All offline and deterministic.
Run: python -m pytest spec_engine/tests/test_rule_exhibit_no.py -v
"""
import pytest
from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg():
    cfg = JobConfig()
    cfg.confirmed_spellings = {}
    return cfg


class TestHappyPath:

    def test_bare_exhibit_number_formatted(self):
        result = clean_block("I reviewed exhibit 15.", _cfg())[0]
        assert "Exhibit No. 15" in result

    def test_exhibit_no_formatted(self):
        result = clean_block("Refer to exhibit no 3.", _cfg())[0]
        assert "Exhibit No. 3" in result

    def test_exhibit_number_word_formatted(self):
        result = clean_block("See exhibit number 7.", _cfg())[0]
        assert "Exhibit No. 7" in result

    def test_already_correct_unchanged(self):
        result = clean_block("See Exhibit No. 15.", _cfg())[0]
        assert "Exhibit No. 15" in result
        assert "Exhibit No. No." not in result

    def test_multi_digit_number_preserved(self):
        result = clean_block("I reviewed exhibit 101.", _cfg())[0]
        assert "Exhibit No. 101" in result

    def test_lowercase_exhibit_corrected(self):
        result = clean_block("exhibit 4 was admitted.", _cfg())[0]
        assert "Exhibit No. 4" in result


class TestFalsePositiveGuard:

    def test_exhibit_hall_not_changed(self):
        result = clean_block("The exhibit hall was open.", _cfg())[0]
        assert "Exhibit No." not in result

    def test_no_double_no(self):
        result = clean_block("Exhibit No. 5 was entered.", _cfg())[0]
        assert "Exhibit No. No." not in result

    def test_exhibit_number_not_converted_to_word(self):
        result = clean_block("See exhibit 3 for details.", _cfg())[0]
        assert "Exhibit No. 3" in result
        assert "three" not in result.lower()


class TestPunctuationBoundary:

    def test_exhibit_at_end_of_sentence(self):
        result = clean_block("Please refer to exhibit 2.", _cfg())[0]
        assert "Exhibit No. 2" in result

    def test_exhibit_mid_sentence(self):
        result = clean_block("Exhibit 8 shows the route taken.", _cfg())[0]
        assert "Exhibit No. 8" in result

    def test_exhibit_after_comma(self):
        result = clean_block("I marked it, exhibit 6, for the record.", _cfg())[0]
        assert "Exhibit No. 6" in result


class TestPassOrdering:

    def test_exhibit_number_not_touched_by_number_to_word(self):
        """Exhibit numbers must not be converted to words by apply_number_to_word."""
        result = clean_block("See exhibit 3 in the record.", _cfg())[0]
        assert "three" not in result.lower()
        assert "Exhibit No. 3" in result

    def test_exhibit_number_not_touched_by_sentence_start_rule(self):
        """Exhibit No. must not trigger sentence-start number spelling."""
        result = clean_block("Exhibit 5 was admitted.", _cfg())[0]
        assert "Five" not in result
        assert "Exhibit No. 5" in result


class TestInterface:

    def test_returns_string(self):
        result = clean_block("exhibit 1", _cfg())[0]
        assert isinstance(result, str)

    def test_correction_recorded(self):
        result, records, _ = clean_block("exhibit 15.", _cfg())
        assert "Exhibit No. 15" in result
        assert len(records) >= 1
