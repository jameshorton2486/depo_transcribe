"""Tests for the deterministic speaker-turn repair stage.

False-positive prevention is the load-bearing test category. The
rules are deliberately conservative: it is acceptable to miss bad
merges, but it is NOT acceptable to split valid testimony.
"""
from __future__ import annotations

import pytest

from clean_format.speaker_turn_repair import (
    RULE_A,
    RULE_B,
    RULE_C,
    RULE_D,
    SpeakerTurnRepairResult,
    TranscriptRepairSummary,
    repair_block_body,
    repair_transcript_blocks,
)


# ---------------------------------------------------------------------------
# RULE A — Embedded short-answer split
# ---------------------------------------------------------------------------


class TestRuleAEmbeddedShortAnswer:
    def test_fires_on_terminal_yes(self):
        body = "Do you understand that? Yes."
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_A
        assert result.repaired_segments == ["Do you understand that?", "Yes."]

    def test_fires_on_terminal_no(self):
        body = "Are you a board-certified surgeon? No."
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_A
        assert result.repaired_segments[1] == "No."

    def test_fires_on_terminal_correct(self):
        body = "And that was on the day in question, correct? Correct."
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_A

    def test_fires_on_terminal_i_do(self):
        body = "Do you solemnly swear to tell the truth, the whole truth and nothing but the truth, so help you God? I do."
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_A
        assert result.repaired_segments[1] == "I do."

    def test_canonicalizes_lowercase_answer(self):
        body = "Do you understand that? yes"
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repaired_segments[1] == "Yes."

    def test_preserves_original_text_field(self):
        body = "Do you understand? Yes."
        result = repair_block_body(body)
        assert result.original_text == body

    # --- false-positive guards ---

    def test_does_not_fire_when_short_answer_is_in_middle(self):
        # The answer is not at the end of the body, so this should be
        # left to Rule B (which has its own preconditions).
        body = "Do you understand that? Yes. And do you also understand what I just said?"
        result = repair_block_body(body)
        # Rule B may fire here; just verify Rule A specifically did not
        # claim it.
        if result.repair_applied:
            assert result.repair_reason != RULE_A

    def test_does_not_fire_when_question_is_tiny(self):
        # Two-word "question" is below _MIN_QUESTION_WORDS=3.
        body = "Right? Yes."
        result = repair_block_body(body)
        assert result.repair_applied is False

    def test_does_not_fire_without_question_mark(self):
        body = "You said that earlier. Yes."
        result = repair_block_body(body)
        assert result.repair_applied is False

    def test_does_not_fire_on_pure_attorney_question(self):
        # No witness short-answer token at the end.
        body = "Doctor, where is your practice located?"
        result = repair_block_body(body)
        assert result.repair_applied is False

    def test_does_not_fire_on_pure_witness_yes(self):
        body = "Yes."
        result = repair_block_body(body)
        assert result.repair_applied is False


# ---------------------------------------------------------------------------
# RULE B — Rapid Q/A cascade split
# ---------------------------------------------------------------------------


class TestRuleBRapidQACascade:
    def test_three_way_split(self):
        body = "Do you treat patients in your private practice? Yes. What kind of doctor are you?"
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_B
        assert len(result.repaired_segments) == 3
        assert result.repaired_segments[0].endswith("?")
        assert result.repaired_segments[1] == "Yes."
        assert result.repaired_segments[2].endswith("?")

    def test_second_question_starts_with_question_starter(self):
        body = "Are you licensed in Texas? Yes. Where did you go to medical school?"
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_B

    # --- false-positive guards ---

    def test_does_not_fire_when_rest_is_not_a_question(self):
        # "Yes." followed by a non-interrogative continuation should
        # be left to Rule A (which only fires on terminal-only).
        body = "Do you understand that? Yes. Thank you very much, sir."
        result = repair_block_body(body)
        # Either no repair or rule A — must NOT be rule B.
        if result.repair_applied:
            assert result.repair_reason != RULE_B

    def test_does_not_fire_when_second_question_too_short(self):
        body = "Do you treat patients here? Yes. Why?"
        result = repair_block_body(body)
        # Either no repair or some other rule; Rule B specifically should not fire.
        if result.repair_applied:
            assert result.repair_reason != RULE_B


# ---------------------------------------------------------------------------
# RULE C — Question -> first-person witness opener
# ---------------------------------------------------------------------------


class TestRuleCQuestionToAnswerShift:
    def test_fires_on_im_opener(self):
        body = "Where is your practice located, Doctor? I'm in Houston, Texas."
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_C
        assert result.repaired_segments[0].endswith("?")
        assert result.repaired_segments[1].startswith("I'm ")

    def test_fires_on_my_practice_opener(self):
        body = "Tell me about your office locations? My practice has two offices, one in Houston and one in San Antonio."
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_C
        assert result.repaired_segments[1].startswith("My practice")

    def test_fires_on_we_do_opener(self):
        body = "What kinds of procedures are performed there? We do spine surgeries and joint replacements."
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_C

    # --- false-positive guards ---

    def test_does_not_fire_on_im_sorry_apology(self):
        # Attorney apologizing for interrupting is a conversational
        # filler, not a witness answer.
        body = "Did you mean to say 2023? I'm sorry, I misspoke earlier."
        result = repair_block_body(body)
        # Rule C should NOT fire because of the i'm-sorry guard.
        if result.repair_applied:
            assert result.repair_reason != RULE_C

    def test_does_not_fire_when_post_question_is_another_question(self):
        body = "Is that what you meant? Did you also see the report?"
        result = repair_block_body(body)
        # Either no repair or Rule D (multi-question), never Rule C.
        if result.repair_applied:
            assert result.repair_reason != RULE_C

    def test_does_not_fire_on_too_short_witness_opener(self):
        # Single-word "I'm" after the question is too short to be a
        # confident answer.
        body = "Was that you in the room? I'm"
        result = repair_block_body(body)
        if result.repair_applied:
            assert result.repair_reason != RULE_C

    def test_does_not_fire_when_question_is_tiny(self):
        body = "Right? I'm a doctor."
        result = repair_block_body(body)
        # Question is 1 word, below threshold.
        assert not (
            result.repair_applied and result.repair_reason == RULE_C
        )


# ---------------------------------------------------------------------------
# RULE D — Multi-question absorption
# ---------------------------------------------------------------------------


class TestRuleDMultiQuestion:
    def test_two_attorney_questions(self):
        body = "Do you perform shoulder surgery? Are you offering any opinions about shoulder injuries?"
        result = repair_block_body(body)
        assert result.repair_applied is True
        assert result.repair_reason == RULE_D
        assert len(result.repaired_segments) == 2
        assert all(seg.endswith("?") for seg in result.repaired_segments)

    # --- false-positive guards ---

    def test_does_not_fire_when_second_part_does_not_start_with_question_starter(self):
        # "Maybe" is not a question starter even though the sentence
        # ends in ?
        body = "Did you see the report? Maybe you saw a different one?"
        result = repair_block_body(body)
        if result.repair_applied:
            assert result.repair_reason != RULE_D

    def test_does_not_fire_on_single_question(self):
        body = "Do you perform shoulder surgery in your private practice?"
        result = repair_block_body(body)
        assert result.repair_applied is False


# ---------------------------------------------------------------------------
# Cross-rule and orchestrator-level tests
# ---------------------------------------------------------------------------


class TestRuleOrchestration:
    def test_no_repair_on_clean_witness_monologue(self):
        body = (
            "I went to medical school at UT Health Houston. I completed my "
            "orthopedic surgery residency at Baylor College of Medicine. "
            "I am board-certified in orthopedic spine surgery."
        )
        result = repair_block_body(body)
        assert result.repair_applied is False
        assert result.repaired_segments == [body]

    def test_no_repair_on_clean_attorney_monologue(self):
        body = (
            "Doctor, my name is Dennis Bentley. I represent the plaintiff "
            "in this civil action filed in Hidalgo County, Texas to recover "
            "for damages sustained in a motor vehicle crash on 09/15/2023."
        )
        result = repair_block_body(body)
        # Even though attorney says "I represent", there is no preceding
        # question, so Rule C should not fire.
        assert result.repair_applied is False

    def test_no_repair_on_colloquy_with_yes_inside(self):
        # "yes" appearing inside an utterance without a preceding question
        # mark must not trigger a split.
        body = (
            "Counsel, will you please state your agreement for this form of "
            "deposition and remote swearing of this witness by saying yes "
            "if you agree."
        )
        result = repair_block_body(body)
        assert result.repair_applied is False

    def test_no_repair_on_oath_block(self):
        body = (
            "Do you solemnly swear to tell the truth, the whole truth and "
            "nothing but the truth so help you God?"
        )
        result = repair_block_body(body)
        # Lone question, no merged answer.
        assert result.repair_applied is False

    def test_idempotent_on_already_repaired(self):
        body = "Do you understand that? Yes."
        first = repair_block_body(body)
        assert first.repair_applied is True
        # The two segments from the first repair should each be no-ops
        # when re-fed through the repair.
        for seg in first.repaired_segments:
            second = repair_block_body(seg)
            assert second.repair_applied is False

    def test_empty_input(self):
        result = repair_block_body("")
        assert result.repair_applied is False
        assert result.repaired_segments == []

    def test_whitespace_only_input(self):
        result = repair_block_body("   \n  ")
        assert result.repair_applied is False
        assert result.repaired_segments == []


# ---------------------------------------------------------------------------
# Transcript-level driver
# ---------------------------------------------------------------------------


class TestRepairTranscriptBlocks:
    def test_passes_through_clean_transcript(self):
        raw = (
            "Speaker 0: Good afternoon. We are on the record.\n\n"
            "Speaker 1: Counsel, please state your appearances.\n\n"
            "Speaker 2: Dennis Bentley for the plaintiff."
        )
        repaired, summary = repair_transcript_blocks(raw)
        assert summary.block_count == 3
        assert summary.blocks_repaired == 0
        assert summary.splits_emitted == 0
        # Output should be identical (modulo whitespace normalization).
        assert "Good afternoon" in repaired
        assert "Dennis Bentley" in repaired

    def test_splits_merged_q_and_short_answer(self):
        raw = (
            "Speaker 2: And Doctor Etminan, my name is Dennis Bentley.\n\n"
            "Speaker 2: Do you understand that? Yes.\n\n"
            "Speaker 2: Thank you."
        )
        repaired, summary = repair_transcript_blocks(raw)
        assert summary.block_count == 3
        assert summary.blocks_repaired == 1
        assert summary.splits_emitted == 1
        assert summary.rule_counts.get(RULE_A) == 1
        # The repaired output should now have 4 blocks (one was split into 2).
        assert repaired.count("\n\n") == 3
        assert "Yes." in repaired
        # The original utterance text should appear in the audit records.
        repaired_records = [r for r in summary.records if r.repair_applied]
        assert repaired_records[0].original_text == "Do you understand that? Yes."

    def test_speaker_label_is_preserved_on_split(self):
        raw = "Speaker 3: Are you licensed in Texas? Yes."
        repaired, summary = repair_transcript_blocks(raw)
        assert summary.blocks_repaired == 1
        # Both resulting blocks must carry the same speaker label.
        for block in repaired.split("\n\n"):
            assert block.startswith("Speaker 3:")

    def test_multi_block_with_mixed_rules(self):
        raw = (
            "Speaker 2: Where is your practice located, Doctor? I'm in Houston.\n\n"
            "Speaker 2: Do you understand that? Yes.\n\n"
            "Speaker 2: Do you perform shoulder surgery? Are you offering "
            "any opinions regarding shoulder injuries here today?"
        )
        repaired, summary = repair_transcript_blocks(raw)
        assert summary.blocks_repaired == 3
        assert summary.rule_counts.get(RULE_A) == 1
        assert summary.rule_counts.get(RULE_C) == 1
        assert summary.rule_counts.get(RULE_D) == 1

    def test_handles_no_speaker_label(self):
        # If a block has no "Speaker X:" prefix, the body is still
        # parsed and repaired; the output simply has no label.
        raw = "Do you understand that? Yes."
        repaired, summary = repair_transcript_blocks(raw)
        assert summary.blocks_repaired == 1
        # Output should contain both segments.
        assert "Yes." in repaired

    def test_empty_transcript(self):
        repaired, summary = repair_transcript_blocks("")
        assert repaired == ""
        assert summary.block_count == 0
        assert summary.blocks_repaired == 0

    def test_idempotent_at_transcript_level(self):
        raw = (
            "Speaker 2: Where is your practice, Doctor? I'm in Houston.\n\n"
            "Speaker 2: Do you understand that? Yes."
        )
        first_pass, first_summary = repair_transcript_blocks(raw)
        second_pass, second_summary = repair_transcript_blocks(first_pass)
        # Second pass must not repair anything further.
        assert second_summary.blocks_repaired == 0
        assert second_pass == first_pass

    def test_summary_log_line_includes_rule_counts(self):
        from clean_format.speaker_turn_repair import format_summary_log_line

        raw = (
            "Speaker 2: Do you understand that? Yes.\n\n"
            "Speaker 2: Do you perform shoulder surgery? Are you offering opinions here?"
        )
        _, summary = repair_transcript_blocks(raw)
        line = format_summary_log_line(summary)
        assert "[SPEAKER_REPAIR]" in line
        assert "repairs=2" in line


# ---------------------------------------------------------------------------
# Provenance contract — every Deepgram block must remain reconstructable
# ---------------------------------------------------------------------------


class TestProvenanceContract:
    def test_original_text_preserved_in_record(self):
        body = "Do you understand that? Yes."
        result = repair_block_body(body)
        assert result.original_text == body

    def test_summary_records_preserve_originals(self):
        raw = "Speaker 2: Do you understand that? Yes."
        _, summary = repair_transcript_blocks(raw)
        assert len(summary.records) == 1
        assert summary.records[0].original_text == "Do you understand that? Yes."
