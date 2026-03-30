"""
spec_engine/tests/test_corrections_coverage.py

Tests for correction functions that had zero coverage.
All tests are offline and deterministic.
Run: python -m pytest spec_engine/tests/test_corrections_coverage.py -v
"""
import pytest
from spec_engine.corrections import (
    apply_case_corrections,
    fix_conversational_titles,
    fix_even_dollar_amounts,
    fix_uh_huh_hyphenation,
    normalize_time_and_dashes,
)
from spec_engine.models import JobConfig


def _job(spellings: dict) -> JobConfig:
    cfg = JobConfig()
    cfg.confirmed_spellings = spellings
    return cfg


# ─────────────────────────────────────────────
# apply_case_corrections
# ─────────────────────────────────────────────

class TestApplyCaseCorrections:

    def test_replaces_misspelled_name(self):
        records = []
        result = apply_case_corrections(
            "The witness is Koger.", _job({"Koger": "Coger"}), records, 0
        )
        assert "Coger" in result

    def test_case_insensitive_match(self):
        records = []
        result = apply_case_corrections(
            "koger testified.", _job({"Koger": "Coger"}), records, 0
        )
        assert "Coger" in result

    def test_records_correction(self):
        records = []
        apply_case_corrections(
            "Koger was there.", _job({"Koger": "Coger"}), records, 0
        )
        assert len(records) == 1

    def test_no_change_when_already_correct(self):
        records = []
        result = apply_case_corrections(
            "Coger was there.", _job({"Koger": "Coger"}), records, 0
        )
        assert result == "Coger was there."
        assert records == []

    def test_empty_spellings_leaves_text_unchanged(self):
        records = []
        original = "Some text here."
        result = apply_case_corrections(original, _job({}), records, 0)
        assert result == original

    def test_does_not_replace_substring(self):
        records = []
        result = apply_case_corrections(
            "The Rogerson case.", _job({"Roger": "Rogar"}), records, 0
        )
        assert "Rogerson" in result


# ─────────────────────────────────────────────
# fix_conversational_titles
# ─────────────────────────────────────────────

class TestFixConversationalTitles:

    def test_mister_to_mr(self):
        records = []
        result = fix_conversational_titles("mister Garcia testified.", records, 0)
        assert "Mr." in result

    def test_miss_to_ms(self):
        records = []
        result = fix_conversational_titles("miss Ozuna asked.", records, 0)
        assert "Ms." in result

    def test_missus_to_mrs(self):
        records = []
        result = fix_conversational_titles("missus Rodriguez signed.", records, 0)
        assert "Mrs." in result

    def test_already_correct_unchanged(self):
        records = []
        original = "Mr. Garcia testified."
        result = fix_conversational_titles(original, records, 0)
        assert result == original
        assert records == []

    def test_lowercase_context_unchanged(self):
        records = []
        result = fix_conversational_titles("the mister of ceremonies", records, 0)
        assert "Mr." not in result


# ─────────────────────────────────────────────
# fix_even_dollar_amounts
# ─────────────────────────────────────────────

class TestFixEvenDollarAmounts:

    def test_removes_trailing_zeros(self):
        records = []
        result = fix_even_dollar_amounts("paid $450.00 for services.", records, 0)
        assert "$450" in result
        assert "$450.00" not in result

    def test_large_amount_with_comma(self):
        records = []
        result = fix_even_dollar_amounts("total was $1,200.00.", records, 0)
        assert "$1,200" in result
        assert "$1,200.00" not in result

    def test_non_even_amount_unchanged(self):
        records = []
        original = "paid $450.50 for services."
        result = fix_even_dollar_amounts(original, records, 0)
        assert result == original

    def test_already_no_decimals_unchanged(self):
        records = []
        original = "paid $350 total."
        result = fix_even_dollar_amounts(original, records, 0)
        assert result == original

    def test_records_correction(self):
        records = []
        fix_even_dollar_amounts("paid $450.00.", records, 0)
        assert len(records) == 1


# ─────────────────────────────────────────────
# fix_uh_huh_hyphenation
# ─────────────────────────────────────────────

class TestFixUhHuhHyphenation:

    def test_uh_huh_space_to_hyphen(self):
        records = []
        result = fix_uh_huh_hyphenation("Uh huh, I agree.", records, 0)
        assert "uh-huh" in result.lower()

    def test_uh_uh_space_to_hyphen(self):
        records = []
        result = fix_uh_huh_hyphenation("Uh uh, I disagree.", records, 0)
        assert "uh-uh" in result.lower()

    def test_already_hyphenated_unchanged(self):
        records = []
        original = "Uh-huh, that's right."
        result = fix_uh_huh_hyphenation(original, records, 0)
        assert result == original

    def test_no_change_leaves_no_record(self):
        records = []
        fix_uh_huh_hyphenation("Yes, I agree.", records, 0)
        assert records == []


# ─────────────────────────────────────────────
# normalize_time_and_dashes
# ─────────────────────────────────────────────

class TestNormalizeTimeAndDashes:

    def test_time_am_no_space_gets_dotted(self):
        records = []
        result = normalize_time_and_dashes("at 10:08AM.", records, 0)
        assert "10:08 a.m." in result

    def test_time_pm_no_space_gets_dotted(self):
        records = []
        result = normalize_time_and_dashes("ended at 2:30PM.", records, 0)
        assert "2:30 p.m." in result

    def test_already_dotted_unchanged(self):
        records = []
        original = "at 10:08 a.m."
        result = normalize_time_and_dashes(original, records, 0)
        assert result == original

    def test_em_dash_to_double_hyphen(self):
        records = []
        result = normalize_time_and_dashes("word\u2014word", records, 0)
        assert "--" in result

    def test_no_change_leaves_no_record(self):
        records = []
        normalize_time_and_dashes("plain text here.", records, 0)
        assert records == []


# ─────────────────────────────────────────────
# fix_qa_structure (via qa_fixer)
# ─────────────────────────────────────────────

class TestFixQaStructure:

    def _make_block(self, text, speaker_id=2):
        from spec_engine.models import Block
        return Block(speaker_id=speaker_id, text=text, raw_text=text)

    def test_returns_list(self):
        from spec_engine.qa_fixer import fix_qa_structure
        blocks = [self._make_block("Did you go there?")]
        result = fix_qa_structure(blocks)
        assert isinstance(result, list)

    def test_empty_input_returns_empty(self):
        from spec_engine.qa_fixer import fix_qa_structure
        result = fix_qa_structure([])
        assert result == []

    def test_single_block_preserved(self):
        from spec_engine.qa_fixer import fix_qa_structure
        blocks = [self._make_block("Yes, I did.")]
        result = fix_qa_structure(blocks)
        assert len(result) >= 1

    def test_does_not_alter_verbatim_words(self):
        from spec_engine.qa_fixer import fix_qa_structure
        blocks = [self._make_block("Uh, did you go there? Yes, um, I did.")]
        result = fix_qa_structure(blocks)
        all_text = " ".join(b.text for b in result)
        assert "uh" in all_text.lower()
        assert "um" in all_text.lower()
