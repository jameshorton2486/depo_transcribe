"""
Morson's English Guide punctuation regression tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from formatter import (
    normalize_dashes,
    normalize_sentence_spacing,
    normalize_spaced_dashes,
    normalize_uh_huh_hyphenation,
)
from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg() -> JobConfig:
    return JobConfig()


def _clean(text: str, cfg: JobConfig | None = None) -> str:
    return clean_block(text, cfg or _cfg())[0]


def _space(text: str) -> str:
    return normalize_sentence_spacing(text)


def _dash(text: str) -> str:
    return normalize_spaced_dashes(normalize_dashes(text))


def _hum(text: str) -> str:
    return normalize_uh_huh_hyphenation(text)


class TestEllipsisPreservation:
    def test_three_adjacent_periods_become_spaced(self):
        assert ". . ." in _clean("I do not recall...")

    def test_four_adjacent_periods_become_spaced(self):
        assert ". . . ." in _clean("And then....")

    def test_spaced_ellipsis_preserved(self):
        result = _clean("He said . . . and stopped.")
        assert result.count(". . .") == 1

    def test_ellipsis_not_double_spaced_before_capital(self):
        result = _space("Witness said . . . Yes, that is correct.")
        assert ". . .  " not in result

    def test_partial_ellipsis_normalized(self):
        assert ". . ." in _clean("He said. ..and left.")


class TestDashNormalization:
    def test_em_dash_to_double_hyphen(self):
        assert " -- " in _dash("He was — no, wait.")

    def test_en_dash_to_double_hyphen(self):
        assert " -- " in _dash("Pages 5–8 were marked.")

    def test_attached_double_hyphen_gets_spaces(self):
        assert " -- " in _dash("It was--no, it wasn't.")

    def test_triple_hyphen_normalized(self):
        assert " -- " in _dash("He said --- wait.")

    def test_cross_examination_header_preserved(self):
        assert "CROSS-EXAMINATION" in _dash("CROSS-EXAMINATION")


class TestSentenceStartNumbers:
    @pytest.mark.parametrize(
        "text,want",
        [
            ("1 witness saw it.", "One witness saw it."),
            ("2 witnesses saw it.", "Two witnesses saw it."),
            ("3 witnesses saw it.", "Three witnesses saw it."),
            ("4 witnesses saw it.", "Four witnesses saw it."),
            ("5 witnesses saw it.", "Five witnesses saw it."),
            ("6 witnesses saw it.", "Six witnesses saw it."),
            ("7 witnesses saw it.", "Seven witnesses saw it."),
            ("8 witnesses saw it.", "Eight witnesses saw it."),
            ("9 witnesses saw it.", "Nine witnesses saw it."),
            ("10 witnesses saw it.", "Ten witnesses saw it."),
        ],
    )
    def test_sentence_start_numbers_spelled_out(self, text, want):
        assert _clean(text) == want

    def test_sentence_start_time_not_converted(self):
        result = _clean("3:00 PM is when the meeting began.")
        assert result.startswith("3:00")

    def test_sentence_start_with_exhibit_later_still_converts(self):
        result = _clean("5 people were present. They signed Exhibit 3.")
        assert result.startswith("Five")


class TestMidSentenceNumbers:
    def test_mid_sentence_count_converts(self):
        assert "five witnesses" in _clean("There were 5 witnesses present.").lower()

    def test_mid_sentence_count_with_exhibit_elsewhere_converts(self):
        result = _clean("I signed Exhibit 3 and there were 5 witnesses present.")
        assert "Exhibit 3" in result
        assert "five witnesses" in result.lower()

    def test_ten_days_converts(self):
        assert "ten days" in _clean("He waited 10 days to report it.").lower()


class TestNumberExclusions:
    def test_exhibit_number_preserved(self):
        assert "Exhibit 3" in _clean("I refer you to Exhibit 3.")

    def test_time_preserved(self):
        assert "3:00 p.m." in _clean("The meeting started at 3:00 PM.")

    def test_dollar_amount_preserved(self):
        assert "$5" in _clean("There was a $5 fee.")

    def test_address_number_preserved(self):
        assert "123 Main Street" in _clean("They were at 123 Main Street.")

    def test_date_fraction_preserved(self):
        assert "4/17" in _clean("The incident occurred on 4/17.")

    def test_range_preserved(self):
        assert "6-8 feet" in _clean("The distance was 6-8 feet.")

    def test_room_number_preserved(self):
        assert "101" in _clean("Meet me in room 101.")

    def test_zip_like_long_number_preserved(self):
        assert "78230" in _clean("The office is in San Antonio, Texas 78230.")


class TestSlashPreservation:
    def test_and_or_normalized(self):
        assert "and/or" in _clean("You may accept and / or reject the offer.")

    def test_either_or_normalized(self):
        assert "either/or" in _clean("It must be either / or, not both.")


class TestVerbatimUhUm:
    def test_uh_preserved(self):
        assert "uh" in _clean("I, uh, think so.").lower()

    def test_um_preserved(self):
        assert "um" in _clean("Um, that is correct.").lower()

    def test_yeah_preserved(self):
        assert "yeah" in _clean("Yeah, I went there.").lower()

    def test_nope_preserved(self):
        assert "nope" in _clean("Nope, I didn't.").lower()

    def test_uh_huh_preserved(self):
        assert "uh-huh" in _clean("Uh-huh, that's right.").lower()


class TestMmHmmNormalization:
    def test_mhmm_to_mm_hmm(self):
        assert "Mm-hmm" in _clean("Mhmm, that's right.")

    def test_mmhm_to_mm_hmm(self):
        assert "Mm-hmm" in _clean("Mmhm, that's right.")

    def test_mm_hmm_spaced_normalized(self):
        assert "mm-hmm" in _hum("mm hmm, that is correct.").lower()

    def test_uppercase_mm_hmm_spaced_normalized(self):
        assert "Mm-hmm" in _hum("Mm hmm, I agree.")


class TestKayToOkay:
    def test_k_period_to_okay_end_of_block(self):
        assert _clean("K.") == "Okay."

    def test_lowercase_k_period_to_okay(self):
        assert _clean("k.") == "Okay."

    def test_k_period_mid_block(self):
        assert _clean("K. I understand.") == "Okay.  I understand."

    def test_lowercase_k_period_mid_block(self):
        assert _clean("k. that's fine.") == "Okay. that's fine."

    def test_mckay_unaffected(self):
        assert "McKay" in _clean("McKay was present.")

    def test_ok_period_unaffected(self):
        assert "OK." in _clean("OK. I understand.")

    def test_k_period_after_speaker_text(self):
        assert "Okay." in _clean("The witness answered K.")

    def test_k_period_after_question(self):
        assert "Okay." in _clean("Q. K.")


class TestObjectionVerbatim:
    def test_bare_objection_preserved(self):
        assert _clean("Objection.") == "Objection."

    def test_objection_form_preserved(self):
        assert _clean("Objection. Form.") == "Objection. Form."

    def test_objection_foundation_preserved(self):
        assert "Objection.  Foundation." == _clean("Objection. Foundation.")

    def test_speaker_labeled_objection_preserved(self):
        assert "MR. BOYCE: Objection." in _clean("MR. BOYCE: Objection.")

    def test_objection_question_mark_preserved(self):
        assert "Objection?" in _clean("Objection?")

    def test_objection_to_form_preserved_if_already_spoken(self):
        assert "Objection to form." in _clean("Objection to form.")


class TestObjectionGarbleCorrection:
    def test_exit_form_corrected(self):
        assert _clean("Exit form") == "Objection. Form."

    def test_exit_form_with_period_corrected(self):
        assert _clean("Exit form.") == "Objection. Form."

    def test_action_form_with_period_corrected(self):
        assert _clean("Action form.") == "Objection. Form."

    def test_objection_form_with_period_corrected(self):
        assert _clean("Objection form.") == "Objection. Form."


class TestBlockCapitalization:
    def test_lowercase_block_capitalized(self):
        assert _clean("yes, I did.") == "Yes, I did."

    def test_already_capitalized_unchanged(self):
        assert _clean("Yes, I did.") == "Yes, I did."

    def test_number_sentence_start_capitalized_after_conversion(self):
        assert _clean("3 people were there.") == "Three people were there."


class TestSentenceSpacing:
    def test_two_spaces_after_period(self):
        assert "answered.  The" in _space("He answered. The next question followed.")

    def test_two_spaces_after_question_mark(self):
        assert "it?  Yes" in _space("Did you see it? Yes, I did.")

    def test_two_spaces_after_exclamation(self):
        assert "Stop!  He" in _space("Stop! He ran away.")

    def test_dr_abbreviation_not_double_spaced(self):
        assert "Dr.  Smith" not in _space("Dr. Smith examined the patient.")

    def test_mr_abbreviation_not_double_spaced(self):
        assert "Mr.  Jones" not in _space("Mr. Jones objected.")

    def test_mrs_abbreviation_not_double_spaced(self):
        assert "Mrs.  Davis" not in _space("Mrs. Davis testified next.")

    def test_ms_abbreviation_not_double_spaced(self):
        assert "Ms.  Taylor" not in _space("Ms. Taylor is the plaintiff.")

    def test_jr_abbreviation_not_double_spaced(self):
        assert "Jr.  was" not in _space("John Smith Jr. was present.")

    def test_no_abbreviation_not_double_spaced(self):
        assert "No.  15" not in _space("Exhibit No. 15 was admitted.")

    def test_am_mid_sentence_not_double_spaced(self):
        assert "a.m.  on" not in _space("The meeting started at 10:00 a.m. on Tuesday.")

    def test_ellipsis_not_double_spaced(self):
        assert ". . .  " not in _space("Answer: . . . I do not recall.")
