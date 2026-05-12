"""Positive-coverage tests for Step A behavioral changes.

These tests pin the four behaviors introduced in Step A:
  1. Trailing fillers are preserved (no strip).
  2. Missing terminal punctuation defaults to `.`, never `?`.
  3. Em-dash interruption markers are preserved and normalized to ` -- `.
  4. Sentence-initial digits 11 and 12 are NOT spelled out (Morson's 1-10).

Existing tests in test_corrections.py and test_morsons_rules.py that
encode the now-reversed behaviors must be reviewed in Step A.1. This
file does not modify them.
"""

from __future__ import annotations

from spec_engine.corrections import (
    _normalize_em_dashes,
    apply_morsons_rules,
)


# Rule 1 - filler preservation -------------------------------------------------


class TestFillerPreservation:
    def test_trailing_uh_is_kept(self):
        assert apply_morsons_rules("I think it was, uh") == "I think it was, uh."

    def test_trailing_um_is_kept(self):
        assert apply_morsons_rules("Maybe, um") == "Maybe, um."

    def test_trailing_you_know_is_kept(self):
        assert apply_morsons_rules("It was like that, you know") == "It was like that, you know."

    def test_inline_fillers_are_kept(self):
        assert (
            apply_morsons_rules("I, uh, went to the store, you know, on Tuesday")
            == "I, uh, went to the store, you know, on Tuesday."
        )

    def test_standalone_uh_block_is_kept(self):
        assert apply_morsons_rules("Uh") == "Uh."


# Rule 2 - period-only terminal default ---------------------------------------


class TestPeriodOnlyDefault:
    def test_did_you_does_not_get_question_mark(self):
        assert apply_morsons_rules("did you go there") == "Did you go there."

    def test_who_was_there_does_not_get_question_mark(self):
        assert apply_morsons_rules("who was there") == "Who was there."

    def test_explicit_question_mark_is_kept(self):
        assert apply_morsons_rules("Did you go there?") == "Did you go there?"

    def test_explicit_exclamation_is_kept(self):
        assert apply_morsons_rules("Stop!") == "Stop!"

    def test_explicit_period_is_kept(self):
        assert apply_morsons_rules("I went there.") == "I went there."


# Rule 3 - em-dash preservation and normalization -----------------------------


class TestEmDashHandling:
    def test_spaced_double_hyphen_is_preserved(self):
        assert apply_morsons_rules("I was walking -- no, running") == "I was walking -- no, running."

    def test_unicode_em_dash_is_normalized(self):
        assert apply_morsons_rules("I was walking — no, running") == "I was walking -- no, running."

    def test_unicode_en_dash_is_normalized(self):
        assert apply_morsons_rules("I was walking – no, running") == "I was walking -- no, running."

    def test_double_hyphen_without_spaces_is_normalized(self):
        assert apply_morsons_rules("I was walking--no, running") == "I was walking -- no, running."

    def test_trailing_interruption_marker_is_preserved(self):
        # Trailing -- with no terminal punctuation. After Step A:
        # _normalize_em_dashes leaves the -- in place; _fix_ending_punctuation
        # appends `.` since there is no terminal `.!?`. Note: the dash is
        # NOT stripped or collapsed.
        result = apply_morsons_rules("I was about to say --")
        assert " -- " in result or result.endswith(" --.")

    def test_normalize_em_dashes_is_idempotent(self):
        once = _normalize_em_dashes("a -- b")
        twice = _normalize_em_dashes(once)
        assert once == twice
        assert once == "a -- b"

    def test_em_dash_is_never_collapsed_to_spaces(self):
        # Hard guarantee: regardless of source form, output contains ` -- `.
        for src in (
            "A -- B",
            "A — B",
            "A – B",
            "A--B",
            "A  --  B",
        ):
            result = _normalize_em_dashes(src)
            assert " -- " in result, f"Em-dash collapsed for input: {src!r}"


# Rule 4 - Morson's 1-10 number range -----------------------------------------


class TestNumberRange:
    def test_one_through_ten_still_spell_out(self):
        assert apply_morsons_rules("1 person was there").startswith("One ")
        assert apply_morsons_rules("5 people were there").startswith("Five ")
        assert apply_morsons_rules("10 people were there").startswith("Ten ")

    def test_eleven_is_not_spelled_out(self):
        assert apply_morsons_rules("11 people were there").startswith("11 ")

    def test_twelve_is_not_spelled_out(self):
        assert apply_morsons_rules("12 people were there").startswith("12 ")

    def test_thirteen_is_not_spelled_out(self):
        assert apply_morsons_rules("13 people were there").startswith("13 ")
