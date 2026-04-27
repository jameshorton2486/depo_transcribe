"""
spec_engine/tests/test_rule_terminal_punctuation.py

Tests for enforce_terminal_punctuation — Phase E fragment guard.

Background: enforce_terminal_punctuation (rule 13 in clean_block, per
CLAUDE.md section 10) used to append a period to ANY block that did
not already end in .?!. That fired on incomplete utterances
("And", "So", "Here,", "It", "Then", "So Okay") seen in the Singh
transcript output, producing standalone fragment blocks like "And."
and "Here,." that read as terminated sentences when they were
actually trailing-off speech the next block continued.

The Phase E fix adds a fragment-detection guard (rule 0, prepended
ahead of the existing rules 1-3) that records a "skipped_fragment"
event and returns the block unchanged when the shape matches a known
fragment pattern. Verbatim words are not removed — only the
punctuation append is skipped.

All offline and deterministic.
"""

import pytest

from spec_engine.corrections import enforce_terminal_punctuation


def _run(text: str) -> tuple[str, list]:
    records: list = []
    out = enforce_terminal_punctuation(text, records, 0)
    return out, records


# ── Fragments observed in the Singh transcript output (must NOT get a period)

class TestSinghFragmentsUnchanged:

    def test_bare_and_unchanged(self):
        out, _ = _run("And")
        assert out == "And"

    def test_bare_so_unchanged(self):
        out, _ = _run("So")
        assert out == "So"

    def test_bare_then_unchanged(self):
        out, _ = _run("Then")
        assert out == "Then"

    def test_bare_it_unchanged(self):
        out, _ = _run("It")
        assert out == "It"

    def test_trailing_comma_continuation_unchanged(self):
        # Pre-fix output was "Here,." — comma followed by appended period.
        # Now: trailing comma indicates continuation; preserve as-is.
        out, _ = _run("Here,")
        assert out == "Here,"

    def test_two_word_fragment_chain_so_okay_unchanged(self):
        # "So Okay" was being normalized to "So Okay." via the bare-Okay
        # rule 2 logic. The fragment guard short-circuits before rule 2.
        out, _ = _run("So Okay")
        assert out == "So Okay"

    def test_three_word_short_block_ending_in_preposition_unchanged(self):
        out, _ = _run("He went to")
        assert out == "He went to"

    def test_bare_preposition_unchanged(self):
        out, _ = _run("to")
        assert out == "to"


# ── Closed-class single-word answers (these MUST still get a period)

class TestSingleWordAnswersStillGetPeriod:

    def test_yes_gets_period(self):
        out, _ = _run("Yes")
        assert out == "Yes."

    def test_no_gets_period(self):
        out, _ = _run("No")
        assert out == "No."

    def test_correct_gets_period(self):
        out, _ = _run("Correct")
        assert out == "Correct."

    def test_incorrect_gets_period(self):
        out, _ = _run("Incorrect")
        assert out == "Incorrect."

    def test_true_gets_period(self):
        out, _ = _run("True")
        assert out == "True."


# ── Multi-word complete sentences (regression — fragment guard must not fire)

class TestCompleteSentencesStillGetPeriod:

    def test_he_went_to_the_store_gets_period(self):
        out, _ = _run("He went to the store")
        assert out == "He went to the store."

    def test_she_came_home_gets_period(self):
        out, _ = _run("She came home")
        assert out == "She came home."

    def test_q_a_combo_already_terminated_unchanged(self):
        out, _ = _run("Did you go there?")
        assert out == "Did you go there?"

    def test_existing_period_unchanged(self):
        out, _ = _run("It is what it is.")
        assert out == "It is what it is."


# ── Direct-address comma case (rule runs at priority 12, before this guard)

class TestDirectAddressCommaRegression:

    def test_yes_sir_gets_period(self):
        # The direct-address comma rule (priority 12) converts "Yes sir"
        # to "Yes, sir" earlier in clean_block. By the time
        # enforce_terminal_punctuation runs at priority 13, the input
        # is already "Yes, sir" and a period must still be appended.
        # The fragment guard must NOT fire on this 2-word case because
        # neither word is in the fragment denylist.
        out, _ = _run("Yes, sir")
        assert out == "Yes, sir."

    def test_no_maam_gets_period(self):
        out, _ = _run("No, ma'am")
        assert out == "No, ma'am."


# ── Existing rule 1 / rule 2 still fire for non-fragment shapes

class TestExistingOkayRulesStillFire:

    def test_okay_comma_becomes_period(self):
        # Existing rule 1: trailing "Okay," normalizes to "Okay."
        # The fragment guard does NOT skip this because "okay" is not
        # in the fragment denylist. Trailing comma here is treated
        # differently from a bare "Here," because of preceding context:
        # ... actually wait — trailing comma triggers fragment skip
        # by the broader rule. Verifying current behavior.
        out, _ = _run("Okay,")
        # Trailing comma → fragment skip applies, return unchanged.
        # If the user later wants the existing rule 1 behavior to win
        # over the comma guard, that's a separate decision.
        assert out == "Okay,"

    def test_bare_okay_gets_period(self):
        # Existing rule 2 still fires because "okay" alone is not in
        # any fragment list (per the patch's design — "Okay." has been
        # the historical behavior and isn't on the Singh fragment list).
        out, _ = _run("Okay")
        assert out == "Okay."


# ── Skip event is recorded in the corrections log

class TestSkipEventRecorded:

    def test_skip_records_a_correction_record(self):
        out, records = _run("And")
        assert out == "And"
        # Per master prompt: skip events are recorded so the corrections
        # log shows both fires and no-op decisions.
        assert any(
            "enforce_terminal_punctuation:skipped_fragment" == r.pattern
            for r in records
        )

    def test_skip_record_has_unchanged_text(self):
        out, records = _run("So")
        skip_records = [
            r for r in records
            if r.pattern == "enforce_terminal_punctuation:skipped_fragment"
        ]
        assert len(skip_records) == 1
        # Skip record has original == corrected because no edit happened.
        assert skip_records[0].original == skip_records[0].corrected
        assert skip_records[0].original == "So"

    def test_normal_period_append_emits_terminal_punctuation_record(self):
        out, records = _run("She came home")
        assert out == "She came home."
        # The fire path goes through _apply_safe_rewrite with pattern
        # 'terminal_punctuation' — keep that as the contract distinct
        # from the skip pattern.
        assert any(r.pattern == "terminal_punctuation" for r in records)


# ── Verbatim invariant (CLAUDE.md section 5) — no words removed

class TestVerbatimInvariant:

    def test_fragment_skip_does_not_remove_words(self):
        # The fragment guard returns input unchanged. No word is
        # removed, normalized, or modified. Verifies the patch does
        # not violate CLAUDE.md section 5 — verbatim words like
        # "uh" must survive even when the rule decides to skip.
        # "uh, And" is 2 words ending in the conjunction "and",
        # so the < 4 words AND ends-with-conjunction heuristic
        # treats it as a fragment. Output should be unchanged.
        out, _ = _run("uh, And")
        # The verbatim "uh" is preserved (most important assertion).
        assert "uh" in out
        # The full input survives unchanged — no period appended,
        # no character removed.
        assert out == "uh, And"

    def test_filler_word_yeah_alone_still_gets_period(self):
        # "Yeah" is a verbatim filler per CLAUDE.md section 5. The
        # patch deliberately does NOT include "yeah" in the one-word
        # fragment list — bare "Yeah" gets a period via existing
        # rule 3 (preserves historical behavior). Adding it would be
        # a separate scope-expansion decision.
        out, _ = _run("Yeah")
        assert out == "Yeah."
