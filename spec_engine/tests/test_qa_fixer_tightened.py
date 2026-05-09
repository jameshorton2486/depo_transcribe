"""Tests for Step 2A tightening of enforce_qa_sequence detection rules.

These tests pin down the new behavior introduced in Step 2A:
  * Pre-deposition gate (no re-typing before oath/directive)
  * Tighter question detection (fragment markers, word count, etc.)
  * Tighter answer detection (no length-only clause)

Existing tests in test_qa_fixer.py must continue to pass unchanged.
"""

from __future__ import annotations

import pytest

from spec_engine.models import TranscriptBlock
from spec_engine.qa_fixer import (
    _is_likely_answer,
    _is_likely_question,
    enforce_qa_sequence,
)


def _block(speaker: str, text: str, type_: str = "colloquy") -> TranscriptBlock:
    return TranscriptBlock(speaker=speaker, text=text, type=type_)


# ── _is_likely_question ───────────────────────────────────────────────────────


class TestIsLikelyQuestion:
    def test_ends_with_question_mark(self):
        assert _is_likely_question("Did you see the report?") is True

    def test_starts_with_question_word_with_substance(self):
        assert _is_likely_question("Did you see the report on Friday") is True

    def test_starts_with_question_word_too_short(self):
        # 3 words, no question mark — below the 4-word floor
        assert _is_likely_question("Did you see") is False

    def test_short_idiom_with_question_word(self):
        # "What a picture." — 3 words, no `?`, ends with `.`
        assert _is_likely_question("What a picture.") is False

    def test_fragment_ending_in_comma(self):
        # "Have you, uh,." — fragment marker, even though starts with `have`
        assert _is_likely_question("Have you, uh,.") is False

    def test_fragment_ending_in_comma_only(self):
        assert _is_likely_question("Have you, uh,") is False

    def test_fragment_ending_in_semicolon(self):
        assert _is_likely_question("Did you see the report on;") is False

    def test_does_not_start_with_question_word_no_question_mark(self):
        # Plain statement — must not be re-typed
        assert _is_likely_question("The report was filed Tuesday.") is False

    def test_empty_text(self):
        assert _is_likely_question("") is False

    def test_whitespace_only(self):
        assert _is_likely_question("   ") is False

    def test_exact_question_word_only(self):
        # "Why?" — exactly one word, but ends with `?`. Should be a question.
        assert _is_likely_question("Why?") is True


# ── _is_likely_answer ─────────────────────────────────────────────────────────


class TestIsLikelyAnswer:
    """The signature is now speaker-aware:
        _is_likely_answer(text, prior_type, prior_speaker,
                          current_speaker, current_classifier_type)
    """

    def test_yes_after_question_from_different_speaker(self):
        # Canonical bare answer with speaker change → answer.
        assert _is_likely_answer(
            "Yes.",
            prior_type="question",
            prior_speaker="Speaker 1",
            current_speaker="Speaker 0",
            current_classifier_type="colloquy",
        ) is True

    def test_yes_not_after_question(self):
        # Prior wasn't a question → not an answer.
        assert _is_likely_answer(
            "Yes.",
            prior_type="colloquy",
            prior_speaker="Speaker 1",
            current_speaker="Speaker 0",
            current_classifier_type="colloquy",
        ) is False

    def test_correct_after_question_from_different_speaker(self):
        assert _is_likely_answer(
            "Correct.",
            prior_type="question",
            prior_speaker="Speaker 1",
            current_speaker="Speaker 0",
            current_classifier_type="colloquy",
        ) is True

    def test_witness_substantive_answer_via_colloquy_fallback(self):
        # The Cavazos regression case: witness's name response after
        # question from a different speaker. Doesn't match the
        # bare-word set, but qualifies via colloquy + speaker-change +
        # not-a-question.
        assert _is_likely_answer(
            "Gilberto Rodriguez Cavazos.",
            prior_type="question",
            prior_speaker="Speaker 2",
            current_speaker="Speaker 4",
            current_classifier_type="colloquy",
        ) is True

    def test_same_speaker_continuation_after_own_question_not_answer(self):
        # Asker continues talking after their own question. No speaker
        # change → not an answer, even if the text is canonical.
        assert _is_likely_answer(
            "Yes.",
            prior_type="question",
            prior_speaker="Speaker 2",
            current_speaker="Speaker 2",
            current_classifier_type="colloquy",
        ) is False

    def test_question_shaped_response_after_question_typed_answer(self):
        # "Excuse me?" — colloquy ending with `?` from a different
        # speaker after a question.
        #
        # Step 2A v2 originally asserted False here based on the
        # `not _is_likely_question` guard inside the colloquy-fallback
        # branch. Step 2H removed that guard because witness substantive
        # answers (e.g. "Would clarify what you mean by large baby.")
        # were being mistyped as questions on real production transcripts.
        # The "Excuse me?" case is now in the same class as those
        # substantive answers — both are treated as answer when they
        # follow an attorney Q from a different speaker. Structurally
        # cleaner; downstream enforce_structure is satisfied.
        assert _is_likely_answer(
            "Excuse me?",
            prior_type="question",
            prior_speaker="Speaker 1",
            current_speaker="Speaker 0",
            current_classifier_type="colloquy",
        ) is True

    def test_pre_classified_answer_not_via_colloquy_fallback(self):
        # Block already typed `answer` by the classifier. The colloquy
        # fallback doesn't apply (it's gated on classifier=colloquy).
        # The bare-word check still runs, but with substantive text
        # outside the set, it returns False here.
        assert _is_likely_answer(
            "Around three days ago.",
            prior_type="question",
            prior_speaker="Speaker 1",
            current_speaker="Speaker 0",
            current_classifier_type="answer",  # not colloquy
        ) is False

    def test_no_prior_speaker_returns_false(self):
        # First block in the walk — prior_speaker is None.
        assert _is_likely_answer(
            "Yes.",
            prior_type="question",
            prior_speaker=None,
            current_speaker="Speaker 0",
            current_classifier_type="colloquy",
        ) is False


# ── Pre-deposition gate ───────────────────────────────────────────────────────


class TestPreDepositionGate:
    def test_pre_oath_question_like_block_stays_colloquy(self):
        """
        Pre-deposition pleasantries that look like questions must not be
        re-typed. Cavazos failure #1 case.
        """
        blocks = [
            _block("Speaker 1", "Good morning, Mr. Gonzalez. Can you hear us?"),
            _block("Speaker 0", "Yes. Good morning."),
            _block("Speaker 1", "Hello, Miss MALONEY. Can you hear us?"),
        ]
        result = enforce_qa_sequence(blocks)
        # No oath or directive ever appears, so nothing should be re-typed.
        assert all(b.type == "colloquy" for b in result), [
            (b.speaker, b.type, b.text) for b in result
        ]

    def test_oath_opens_the_gate(self):
        """After an oath block, normal Q/A re-typing applies."""
        blocks = [
            _block("Speaker 1", "Good morning, Mr. Gonzalez. Can you hear us?"),
            _block("Speaker 0", "Yes."),
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 1", "Did you receive any documents prior to today?"),
            _block("Speaker 0", "Yes.", type_="colloquy"),
        ]
        result = enforce_qa_sequence(blocks)
        # Pre-oath: still colloquy
        assert result[0].type == "colloquy"
        assert result[1].type == "colloquy"
        # Oath: passes through
        assert result[2].type == "oath"
        # Post-oath: re-typed
        assert result[3].type == "question"
        assert result[4].type == "answer"

    def test_directive_also_opens_the_gate(self):
        """A `directive` (BY MR. ATTORNEY:) opens the gate just like an oath."""
        blocks = [
            _block("Speaker 1", "Hello, can you hear us?"),
            _block("Speaker 1", "BY MR. SMITH:", type_="directive"),
            _block("Speaker 1", "Did you receive the documents?"),
            _block("Speaker 0", "Yes."),
        ]
        result = enforce_qa_sequence(blocks)
        assert result[0].type == "colloquy"
        assert result[1].type == "directive"
        assert result[2].type == "question"
        assert result[3].type == "answer"


# ── Cavazos / Caram regression cases ──────────────────────────────────────────


class TestProbeRegressions:
    def test_cavazos_pre_oath_logistics_no_consecutive_q_failure(self):
        """
        Cavazos failure #1: pre-oath blocks 5–13 were all being typed as
        questions. With the gate, none of them should be.
        """
        blocks = [
            _block("Speaker 1", "Good morning, Mr. Gonzalez. Can you hear us?"),
            _block("Speaker 0", "Yes. Good morning."),
            _block("Speaker 0", "Morning."),
            _block("Speaker 1", "Hello, Miss MALONEY. Can you hear us?"),
            _block("Speaker 1", "Hello, Mr. Cavazos."),
            _block("Speaker 1", "Sir, can you tell me the address that you're at today?"),
            _block("Speaker 2", "1721 Penn Road, Lot 85, San Antonio, Texas 78227."),
        ]
        result = enforce_qa_sequence(blocks)
        question_count = sum(1 for b in result if b.type == "question")
        assert question_count == 0, f"Expected 0 questions pre-oath, got {question_count}"

    def test_caram_fragment_block_does_not_become_question(self):
        """
        Caram failure #1, block 14: "Have you, uh,." — fragment ending with
        comma. Must not be re-typed as question.
        """
        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 2", "Have you, uh,."),
        ]
        result = enforce_qa_sequence(blocks)
        # Block 1 is the fragment — must stay colloquy
        assert result[1].type == "colloquy", (
            f"Fragment 'Have you, uh,.' was re-typed as {result[1].type}"
        )

    def test_what_a_picture_idiom_not_re_typed(self):
        """
        Cavazos failure #3, block 16: "What a picture." — three words,
        starts with question word, but no `?` and below word-count floor.
        """
        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 2", "What a picture."),
        ]
        result = enforce_qa_sequence(blocks)
        assert result[1].type == "colloquy"


# ── Back-merge behavior NOT covered here ─────────────────────────────────────
#
# The back-merge branch in enforce_qa_sequence (where an "answer" block
# folds into a preceding "question" when last_type != "question") is
# preserved from the original implementation, but tracing the linear
# walk shows the branch's three conditions cannot all hold at once:
#   * normalized.type == "answer"
#   * last_type != "question"
#   * fixed[-1].type == "question"
# For fixed[-1] to be "question" requires the immediately previous
# appended block to have been a question, which in turn requires
# last_type == "question" — contradicting the second condition. The
# branch is currently unreachable in any linear walk.
#
# A test was drafted for it and removed (Step 2A B1): writing
# assertions against unreachable behavior was misleading. The branch
# stays in the code with an in-source comment pointing at this
# observation; cleanup is deferred to a separate audit pass after
# Step 2A's failure-count delta is in.


# ── Step 2G: same-speaker consecutive-Q merging ──────────────────────────────


class TestSameSpeakerQMerging:
    """Step 2G: enforce_structure merges same-speaker consecutive Q blocks
    into a single Q block, while preserving the strict raise for
    different-speaker consecutive Qs."""

    def test_two_same_speaker_questions_merge_pass1(self):
        """Pass 1 (input blocks): same-speaker consecutive Qs merge."""
        from spec_engine.qa_fixer import enforce_structure

        blocks = [
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 1", "And was it after noon?", type_="question"),
            _block("Speaker 2", "Yes.", type_="answer"),
        ]
        result = enforce_structure(blocks)
        # First two merged into one Q block
        question_blocks = [b for b in result if b.type == "question"]
        assert len(question_blocks) == 1
        assert question_blocks[0].speaker == "Speaker 1"
        assert "Did you see it?" in question_blocks[0].text
        assert "And was it after noon?" in question_blocks[0].text
        # Answer preserved
        answer_blocks = [b for b in result if b.type == "answer"]
        assert len(answer_blocks) == 1

    def test_three_same_speaker_questions_merge_to_one(self):
        """N-way merges work — three same-speaker Qs collapse to one."""
        from spec_engine.qa_fixer import enforce_structure

        blocks = [
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 1", "Or hear it?", type_="question"),
            _block("Speaker 1", "Or notice it later?", type_="question"),
            _block("Speaker 2", "Yes.", type_="answer"),
        ]
        result = enforce_structure(blocks)
        question_blocks = [b for b in result if b.type == "question"]
        assert len(question_blocks) == 1
        assert "Did you see it?" in question_blocks[0].text
        assert "Or hear it?" in question_blocks[0].text
        assert "Or notice it later?" in question_blocks[0].text

    def test_different_speaker_consecutive_questions_still_raise(self):
        """Different-speaker consecutive Qs remain a hard error."""
        from spec_engine.qa_fixer import enforce_structure

        blocks = [
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 2", "And was it after noon?", type_="question"),
            _block("Speaker 3", "Yes.", type_="answer"),
        ]
        with pytest.raises(
            ValueError, match="encountered consecutive question blocks"
        ):
            enforce_structure(blocks)

    def test_legitimate_q_a_q_a_pattern_passes(self):
        """The normal Q-A-Q-A flow is unaffected."""
        from spec_engine.qa_fixer import enforce_structure

        blocks = [
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 2", "Yes.", type_="answer"),
            _block("Speaker 1", "When did you see it?", type_="question"),
            _block("Speaker 2", "Around noon.", type_="answer"),
        ]
        result = enforce_structure(blocks)
        question_blocks = [b for b in result if b.type == "question"]
        answer_blocks = [b for b in result if b.type == "answer"]
        assert len(question_blocks) == 2
        assert len(answer_blocks) == 2

    def test_merge_preserves_first_blocks_examiner(self):
        """The merged block keeps the first Q's examiner attribution."""
        from spec_engine.qa_fixer import enforce_structure

        blocks = [
            _block(
                "Speaker 1",
                "BY MR. SMITH:",
                type_="directive",
            ),
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 1", "And when?", type_="question"),
            _block("Speaker 2", "Yes, at noon.", type_="answer"),
        ]
        result = enforce_structure(blocks)
        question_blocks = [b for b in result if b.type == "question"]
        assert len(question_blocks) == 1
        # Examiner attribution from the directive flows to both Qs and the
        # merged block keeps that attribution.
        assert question_blocks[0].examiner == "MR. SMITH"


# ── Step 2H: rules-side fixes for Categories A + C ────────────────────────────


class TestCategoryAandCFixes:
    """Step 2H: witness substantive answers (Category A) and objection
    blocks (Category C) should not be typed as questions even when their
    text superficially looks question-shaped."""

    def test_witness_answer_starting_with_question_word_typed_answer(self):
        """Cavazos pair 1 / Caram pair 1: 'would clarify...' answer
        starting with 'would' after attorney Q from different speaker."""
        from spec_engine.qa_fixer import enforce_qa_sequence

        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 1", "What does large baby mean?", type_="question"),
            _block("Speaker 2", "Would clarify what you mean by large baby.",
                   type_="colloquy"),
        ]
        result = enforce_qa_sequence(blocks)
        # The witness's substantive answer must be typed answer, not question.
        assert result[2].type == "answer", (
            f"Expected witness's 'would clarify...' to be typed answer, "
            f"got {result[2].type}"
        )

    def test_witness_answer_ending_with_question_typed_answer(self):
        """Caram pair 2: substantive answer that ends with a clarifying ?."""
        from spec_engine.qa_fixer import enforce_qa_sequence

        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 1", "When did she give you the date?",
                   type_="question"),
            _block(
                "Speaker 2",
                "From what she gave us per the phone call, "
                "it was January 2. Or 22 weeks?",
                type_="colloquy",
            ),
        ]
        result = enforce_qa_sequence(blocks)
        assert result[2].type == "answer", (
            f"Expected witness's answer-with-tail-question to be typed "
            f"answer, got {result[2].type}"
        )

    def test_objection_with_trailing_question_mark_typed_colloquy(self):
        """Caram pair 8: 'Objection. Form. In regards to what?' is colloquy."""
        from spec_engine.qa_fixer import enforce_qa_sequence

        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 1", "Have we discussed your expert opinions?",
                   type_="question"),
            _block("Speaker 0", "Objection. Form. In regards to what?",
                   type_="colloquy"),
        ]
        result = enforce_qa_sequence(blocks)
        # The objection must NOT be typed question.
        assert result[2].type != "question", (
            f"Expected objection to NOT be typed question, got "
            f"{result[2].type}"
        )

    def test_normal_q_a_q_a_flow_unchanged(self):
        """The standard Q-A-Q-A pattern still works after the order swap."""
        from spec_engine.qa_fixer import enforce_qa_sequence

        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 2", "Yes.", type_="colloquy"),
            _block("Speaker 1", "When did you see it?", type_="question"),
            _block("Speaker 2", "Around noon.", type_="colloquy"),
        ]
        result = enforce_qa_sequence(blocks)
        # Find Q and A blocks (ignoring oath at index 0)
        types = [b.type for b in result[1:]]
        # Should be Q-A-Q-A
        assert types == ["question", "answer", "question", "answer"], (
            f"Expected [Q, A, Q, A], got {types}"
        )

    def test_same_speaker_continuation_q_still_typed_question(self):
        """Same-speaker compound questions are unaffected by the order swap.
        The answer-detection requires speaker change, so it can't fire here;
        the question-detection still wins."""
        from spec_engine.qa_fixer import enforce_qa_sequence

        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 1", "Did you also hear it?", type_="colloquy"),
        ]
        result = enforce_qa_sequence(blocks)
        # Both Speaker 1 blocks should remain typed question.
        assert result[1].type == "question"
        assert result[2].type == "question"

    def test_attorney_q_after_witness_a_typed_question(self):
        """Attorney's next question after witness answer is still typed Q
        (not accidentally typed A by the new order)."""
        from spec_engine.qa_fixer import enforce_qa_sequence

        blocks = [
            _block("Court Reporter", "Do you swear...", type_="oath"),
            _block("Speaker 1", "Did you see it?", type_="question"),
            _block("Speaker 2", "Yes.", type_="colloquy"),
            _block("Speaker 1", "When?", type_="colloquy"),
        ]
        result = enforce_qa_sequence(blocks)
        # The "When?" from Speaker 1 should be Q (prior was A from Speaker 2,
        # so answer-detection requires prior_type == question, doesn't fire).
        assert result[3].type == "question"
