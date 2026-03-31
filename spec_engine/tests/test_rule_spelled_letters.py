"""
spec_engine/tests/test_rule_spelled_letters.py

Tests for spelled-letter hyphenation — Morson's Rule 157.
VERBATIM RULE: letters are never changed, only spaces become hyphens.
All offline and deterministic.
Run: python -m pytest spec_engine/tests/test_rule_spelled_letters.py -v
"""
import pytest
from spec_engine.corrections import clean_block, apply_spelled_letter_hyphenation
from spec_engine.models import JobConfig


def _cfg():
    cfg = JobConfig()
    cfg.confirmed_spellings = {}
    return cfg


class TestHappyPath:

    def test_lowercase_name_hyphenated(self):
        result = clean_block(
            "My name is spelled B r e n n e n.", _cfg())[0]
        assert "B-r-e-n-n-e-n" in result

    def test_uppercase_name_hyphenated(self):
        result = clean_block(
            "That name is B A L D E R A S.", _cfg())[0]
        assert "B-A-L-D-E-R-A-S" in result

    def test_five_letter_name(self):
        result = clean_block(
            "Spelled T O V A R on the record.", _cfg())[0]
        assert "T-O-V-A-R" in result

    def test_three_letter_minimum(self):
        records = []
        result = apply_spelled_letter_hyphenation(
            "spelled A B C for the record.", records, 0)
        assert "A-B-C" in result

    def test_letters_not_changed(self):
        result = clean_block(
            "Name spelled B r e n n e n.", _cfg())[0]
        assert "B-r-e-n-n-e-n" in result
        assert "Brennen" not in result


class TestFalsePositiveGuard:

    def test_q_line_marker_not_affected(self):
        result = clean_block("Q. Did you go there?", _cfg())[0]
        assert "Q." in result
        assert "Q-" not in result

    def test_a_line_marker_not_affected(self):
        result = clean_block("A. Yes, sir.", _cfg())[0]
        assert "A." in result
        assert "A-" not in result

    def test_two_letters_not_hyphenated(self):
        records = []
        result = apply_spelled_letter_hyphenation("A B", records, 0)
        assert "A-B" not in result
        assert result == "A B"

    def test_single_letter_i_not_affected(self):
        result = clean_block("I was there.", _cfg())[0]
        assert "I" in result
        assert "I-" not in result

    def test_multiword_breaks_sequence(self):
        result = clean_block(
            "The name is not spelled out here.", _cfg())[0]
        assert "T-h-e" not in result


class TestPunctuationBoundary:

    def test_spelled_name_at_end_of_sentence(self):
        result = clean_block(
            "Please spell your last name. B A L D E R A S.", _cfg())[0]
        assert "B-A-L-D-E-R-A-S" in result

    def test_spelled_name_mid_sentence(self):
        result = clean_block(
            "The witness, B r e n n e n, testified.", _cfg())[0]
        assert "B-r-e-n-n-e-n" in result


class TestPassOrdering:

    def test_verbatim_words_preserved_alongside(self):
        result = clean_block(
            "Uh, my name is spelled T O V A R.", _cfg())[0]
        assert "uh" in result.lower()
        assert "T-O-V-A-R" in result

    def test_correction_recorded(self):
        result, records, _ = clean_block(
            "Spelled B A L D E R A S on record.", _cfg())
        assert "B-A-L-D-E-R-A-S" in result
        assert len(records) >= 1


class TestInterface:

    def test_returns_string(self):
        assert isinstance(
            clean_block("spelled B r e n.", _cfg())[0], str)

    def test_direct_function_call(self):
        records = []
        result = apply_spelled_letter_hyphenation(
            "name is T O V A R here.", records, 0)
        assert "T-O-V-A-R" in result
        assert len(records) == 1
        assert records[0].pattern == "spelled_letter_hyphenation_rule157"
