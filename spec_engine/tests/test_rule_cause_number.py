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

    def test_caught_number_unchanged(self):
        result = clean_block("This is caught number 2025CI19595.", _cfg())[0]
        assert "Cause Number" not in result
        assert "caught number" in result.lower()

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

    def test_caught_number_in_full_preamble_unchanged(self):
        text = "This is caught number 2025CI19595 in the District Court."
        result = clean_block(text, _cfg())[0]
        assert "Cause Number" not in result
        assert "caught number" in result.lower()
        assert "District Court" in result


class TestPassOrdering:

    def test_no_correction_recorded_for_caught_number(self):
        result, records, _ = clean_block("This is caught number 2025CI19595.", _cfg())
        assert "Cause Number" not in result
        assert not any("Cause Number" in record.corrected for record in records)


class TestInterface:

    def test_returns_string(self):
        result = clean_block("caught number 12345.", _cfg())[0]
        assert isinstance(result, str)
        assert "Cause Number" not in result


# ── Phase A — fix_cause_number_digits regex defects ──────────────────────────
# Two bugs were diagnosed in the digit-collapse regex:
#   1. The "(Cause\s+No\.?|Cause\s+Number)" prefix had no \b anchor and
#      ran with re.IGNORECASE, so it matched inside "because".
#   2. The digit-sequence terminator "(?:\s+|$)" rejected trailing
#      punctuation, so "two six seven." truncated to "2326seven.".
# Both are addressed by anchoring the prefix with \b and rebuilding the
# digit group as "first token, then zero-or-more (space + token)" with
# a \b terminator that allows any non-word boundary to end the run.

class TestFixCauseNumberDigits:

    def test_because_no_one_unchanged(self):
        text = "There was no ambulance because no one was injured."
        result = clean_block(text, _cfg())[0]
        assert "beCause" not in result
        assert "No. 1" not in result
        assert "because no one was injured" in result

    def test_because_phrase_in_middle_unchanged(self):
        text = "I missed it because no one told me."
        result = clean_block(text, _cfg())[0]
        assert "because no one told me" in result

    def test_spoken_cause_number_with_trailing_period(self):
        text = "Cause Number two zero two five C I two three two six seven."
        result = clean_block(text, _cfg())[0]
        assert "2025CI23267" in result
        assert "seven" not in result

    def test_spoken_cause_number_with_trailing_comma(self):
        text = "Cause Number two zero two five C I one nine five nine five, plaintiffs."
        result = clean_block(text, _cfg())[0]
        assert "2025CI19595" in result

    def test_already_numeric_cause_number_unchanged(self):
        text = "This is Cause No. 2025CI19595."
        result = clean_block(text, _cfg())[0]
        assert "Cause No. 2025CI19595" in result

    def test_correction_record_emitted(self):
        text = "Cause Number two zero two five C I one two three four five."
        _, records, _ = clean_block(text, _cfg())
        assert any(
            "fix_cause_number_digits" in record.pattern for record in records
        )
