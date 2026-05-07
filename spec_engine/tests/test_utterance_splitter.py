"""Tests for the merged-utterance detector."""

from __future__ import annotations

import pytest

from spec_engine.utterance_splitter import is_merged_utterance


# ── Length floor ──────────────────────────────────────────────────────────────


class TestLengthFloor:
    def test_empty_returns_false(self):
        assert is_merged_utterance("") is False

    def test_whitespace_only_returns_false(self):
        assert is_merged_utterance("   \n\t  ") is False

    def test_short_block_with_two_question_marks_returns_false(self):
        # Has 2 ?s but only 6 words — below the 15-word floor
        assert is_merged_utterance("Did you? Have you?") is False

    def test_at_floor_with_signal_returns_true(self):
        # Exactly 15 words with a clear merge signal
        text = "Did you see the report on Friday morning, sir? Yes I did. How long ago was it?"
        assert is_merged_utterance(text) is True


# ── Rule 1: separated question marks ──────────────────────────────────────────


class TestRule1SeparatedQuestionMarks:
    def test_two_separated_question_marks_returns_true(self):
        text = "Did you see the report yesterday afternoon? How long did it take you to read?"
        assert is_merged_utterance(text) is True

    def test_adjacent_question_marks_returns_false(self):
        # Like "??" — should not trigger by itself
        text = (
            "I am wondering about the timeline??  "
            "what was the situation that led to this entire investigation?"
        )
        # NOTE: this also matches rule 2 (q-word after .?) which is fine; rule 1 alone shouldn't fire
        # Verify by stripping anything that would trip rule 2:
        text_rule_1_only = "I think the issue is timing?? But not particularly noteworthy overall here"
        assert is_merged_utterance(text_rule_1_only) is False

    def test_one_question_mark_returns_false_by_rule_1(self):
        text = "I am wondering when the report from the doctor was filed in the system originally?"
        # Single ?, no other merge signals — should not fire
        assert is_merged_utterance(text) is False


# ── Rule 2: question word after sentence end ──────────────────────────────────


class TestRule2QuestionWordAfterSentenceEnd:
    def test_period_then_did_returns_true(self):
        text = "The report was filed on Tuesday morning. Did you receive a copy of it after that?"
        assert is_merged_utterance(text) is True

    def test_period_then_how_returns_true(self):
        text = "The patient arrived at the hospital around noon. How did you respond to that situation?"
        assert is_merged_utterance(text) is True

    def test_period_then_non_question_word_returns_false(self):
        text = "The report was filed on Tuesday morning. The patient arrived at the hospital around noon."
        assert is_merged_utterance(text) is False


# ── Rule 3: answer word mid-block ─────────────────────────────────────────────


class TestRule3AnswerWordMidBlock:
    def test_yes_mid_block_returns_true(self):
        text = "I asked you about the documents that were filed last week. Yes. So how did you respond to it?"
        assert is_merged_utterance(text) is True

    def test_correct_mid_block_returns_true(self):
        text = "You said you arrived at noon according to the prior testimony. Correct. And then what happened next?"
        assert is_merged_utterance(text) is True

    def test_yes_at_end_no_following_text_returns_false(self):
        text = "And so the answer to that very long and elaborate question is, of course, yes."
        assert is_merged_utterance(text) is False


# ── Rule 4: long block with sentence ends ─────────────────────────────────────


class TestRule4LongBlock:
    def test_long_block_with_two_sentence_ends_returns_true(self):
        text = " ".join(["word"] * 60) + ". Another sentence here. And one more after that."
        assert is_merged_utterance(text) is True

    def test_long_block_with_one_sentence_end_returns_false_by_rule_4(self):
        # Long but only 1 sentence-end and no other rules fire
        text = " ".join(["word"] * 65) + "."
        assert is_merged_utterance(text) is False

    def test_short_block_with_many_sentence_ends_returns_false_by_rule_4(self):
        # Several sentence-ends but under 60 words
        text = "Short. Short. Short. Short. Short. Short."
        # Also too short for the 15-word floor
        assert is_merged_utterance(text) is False


# ── Real-world cases from probe reports ───────────────────────────────────────


class TestProbeRegressions:
    def test_cavazos_merged_address_block(self):
        """Cavazos residual: short witness response actually fine, not flagged."""
        text = "1721 Penn Road, Lot 85, San Antonio, Texas 78227."
        # 9 words — below floor; legitimate single answer; should NOT flag
        assert is_merged_utterance(text) is False

    def test_cavazos_block_49_three_turns_merged(self):
        """Cavazos block 49: 'About 2 years ago. How do you know him? They are my neighbors and friends.'"""
        text = "About two years ago. How do you know him? They are my neighbors and friends."
        assert is_merged_utterance(text) is True

    def test_caram_merged_four_exchange_block(self):
        """Caram block 13: 4-exchange merge with multiple ?s and question-word starts."""
        text = (
            "Have not viewed or read the depositions of Doctor Green or Doctor Fisher? "
            "No, have not. Have you spoken with them about their depositions? I have not."
        )
        assert is_merged_utterance(text) is True

    def test_caram_witness_substantive_answer_not_flagged(self):
        """Witness's real substantive answer like 'About 33, 34 years.' should not be flagged."""
        text = "About 33, 34 years."
        assert is_merged_utterance(text) is False

    def test_normal_attorney_question_not_flagged(self):
        """Normal single-question utterance should not be flagged."""
        text = "What is your full legal name as it appears on your driver's license today?"
        assert is_merged_utterance(text) is False

    def test_normal_witness_answer_with_period_not_flagged(self):
        """Witness explanation that happens to span 2 sentences but is one turn."""
        text = (
            "I have lived there since 1995. My wife and I bought the house from my uncle "
            "after his retirement from the Army in San Antonio."
        )
        # Fails rule 1 (no ?s), rule 2 (no question word after .), rule 3 (no answer word mid-block).
        # Rule 4: 30 words — under 60. Should NOT flag.
        assert is_merged_utterance(text) is False
