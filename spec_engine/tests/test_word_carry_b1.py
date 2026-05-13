"""Step B.1 — word-object carry through qa_fixer and speaker_mapper.

Coverage:
  1. qa_fixer normalize sites preserve `words` identity (same list
     object passes through).
  2. qa_fixer merge sites concatenate words (a + b).
  3. qa_fixer merge sites return None when either side is None.
  4. speaker_mapper.smooth_speaker_sequence rebuilds words with the
     new speaker label.
  5. speaker_mapper.normalize_speakers rebuilds words with normalized
     speaker label.
  6. speaker_mapper propagation returns None when block.words is None.
  7. Helpers tested directly for the boundary cases.

Policy reference: docs/plans/_archive/step_b1_word_carry_merge_split_2026-05-12.md
"""

from __future__ import annotations

from spec_engine.models import TranscriptBlock, TranscriptWord
from spec_engine.qa_fixer import _concat_words, enforce_structure
from spec_engine.speaker_mapper import (
    _propagate_speaker_to_words,
    normalize_speakers,
    smooth_speaker_sequence,
)


def _word(text: str, start: float, end: float, speaker=0) -> TranscriptWord:
    return TranscriptWord(
        text=text,
        start=start,
        end=end,
        confidence=0.95,
        speaker=speaker,
        punctuated_word=text.capitalize(),
    )


# ----------------------------------------------------------------------------
# _concat_words helper
# ----------------------------------------------------------------------------


class TestConcatWordsHelper:
    def test_both_present_concatenates(self):
        a = [_word("hello", 0.0, 0.2), _word("there", 0.3, 0.5)]
        b = [_word("general", 0.6, 0.9), _word("kenobi", 1.0, 1.4)]
        result = _concat_words(a, b)
        assert result is not None
        assert len(result) == 4
        assert [w.text for w in result] == ["hello", "there", "general", "kenobi"]

    def test_left_none_returns_none(self):
        b = [_word("hello", 0.0, 0.2)]
        assert _concat_words(None, b) is None

    def test_right_none_returns_none(self):
        a = [_word("hello", 0.0, 0.2)]
        assert _concat_words(a, None) is None

    def test_both_none_returns_none(self):
        assert _concat_words(None, None) is None

    def test_returns_new_list_not_mutated_input(self):
        a = [_word("a", 0.0, 0.1)]
        b = [_word("b", 0.2, 0.3)]
        result = _concat_words(a, b)
        result.append(_word("c", 0.4, 0.5))
        assert len(a) == 1
        assert len(b) == 1


# ----------------------------------------------------------------------------
# qa_fixer — normalize sites preserve identity
# ----------------------------------------------------------------------------


class TestQAFixerNormalizeIdentity:
    """Normalize sites pass `words` through unchanged — same list object."""

    def test_directive_passthrough_preserves_words_identity(self):
        words = [_word("by", 0.0, 0.1), _word("mister", 0.2, 0.5)]
        block = TranscriptBlock(
            speaker="MR. RAGAN",
            text="BY MR. RAGAN:",
            type="directive",
            source_type="paragraph",
            words=words,
        )
        result = enforce_structure([block])
        assert len(result) == 1
        # Same list object — normalize must not rebuild the words list.
        assert result[0].words is words

    def test_question_passthrough_preserves_words_identity(self):
        directive = TranscriptBlock(
            speaker="MR. RAGAN", text="BY MR. RAGAN:", type="directive",
        )
        q_words = [_word("did", 0.0, 0.2), _word("you", 0.3, 0.5)]
        q = TranscriptBlock(
            speaker="MR. RAGAN",
            text="Did you go there?",
            type="question",
            words=q_words,
        )
        a = TranscriptBlock(
            speaker="WITNESS", text="Yes.", type="answer",
        )
        result = enforce_structure([directive, q, a])
        # Pull the question block out (index 1).
        assert result[1].type == "question"
        assert result[1].words is q_words

    def test_answer_passthrough_preserves_words_identity(self):
        directive = TranscriptBlock(
            speaker="MR. RAGAN", text="BY MR. RAGAN:", type="directive",
        )
        q = TranscriptBlock(
            speaker="MR. RAGAN", text="Did you go there?", type="question",
        )
        a_words = [_word("yes", 0.0, 0.2)]
        a = TranscriptBlock(
            speaker="WITNESS",
            text="Yes.",
            type="answer",
            words=a_words,
        )
        result = enforce_structure([directive, q, a])
        assert result[2].type == "answer"
        assert result[2].words is a_words


# ----------------------------------------------------------------------------
# qa_fixer — merge sites concatenate
# ----------------------------------------------------------------------------


class TestQAFixerMergeConcat:
    """Same-speaker question merge concatenates word arrays."""

    def test_same_speaker_q_merge_pass1_concatenates(self):
        directive = TranscriptBlock(
            speaker="MR. RAGAN", text="BY MR. RAGAN:", type="directive",
        )
        q1_words = [_word("did", 0.0, 0.2), _word("you", 0.3, 0.5)]
        q1 = TranscriptBlock(
            speaker="MR. RAGAN",
            text="Did you",
            type="question",
            words=q1_words,
        )
        q2_words = [_word("go", 0.6, 0.8), _word("there", 0.9, 1.2)]
        q2 = TranscriptBlock(
            speaker="MR. RAGAN",
            text="go there?",
            type="question",
            words=q2_words,
        )
        a = TranscriptBlock(
            speaker="WITNESS", text="Yes.", type="answer",
        )
        result = enforce_structure([directive, q1, q2, a])
        # Merged question at index 1 (after directive).
        merged_q = result[1]
        assert merged_q.type == "question"
        assert merged_q.text == "Did you go there?"
        assert merged_q.words is not None
        assert len(merged_q.words) == 4
        assert [w.text for w in merged_q.words] == ["did", "you", "go", "there"]

    def test_merge_with_one_side_none_yields_none(self):
        directive = TranscriptBlock(
            speaker="MR. RAGAN", text="BY MR. RAGAN:", type="directive",
        )
        q1 = TranscriptBlock(
            speaker="MR. RAGAN",
            text="Did you",
            type="question",
            words=[_word("did", 0.0, 0.2)],
        )
        q2 = TranscriptBlock(
            speaker="MR. RAGAN",
            text="go there?",
            type="question",
            words=None,
        )
        a = TranscriptBlock(
            speaker="WITNESS", text="Yes.", type="answer",
        )
        result = enforce_structure([directive, q1, q2, a])
        merged_q = result[1]
        # Symmetric None — one side missing, merged is None.
        assert merged_q.words is None

    def test_merge_with_both_none_yields_none(self):
        directive = TranscriptBlock(
            speaker="MR. RAGAN", text="BY MR. RAGAN:", type="directive",
        )
        q1 = TranscriptBlock(
            speaker="MR. RAGAN", text="Did you", type="question", words=None,
        )
        q2 = TranscriptBlock(
            speaker="MR. RAGAN", text="go there?", type="question", words=None,
        )
        a = TranscriptBlock(
            speaker="WITNESS", text="Yes.", type="answer",
        )
        result = enforce_structure([directive, q1, q2, a])
        assert result[1].words is None


# ----------------------------------------------------------------------------
# speaker_mapper — propagation helper
# ----------------------------------------------------------------------------


class TestSpeakerPropagationHelper:
    def test_propagate_rebuilds_each_word(self):
        words = [
            _word("hello", 0.0, 0.2, speaker=0),
            _word("there", 0.3, 0.5, speaker=0),
        ]
        result = _propagate_speaker_to_words(words, "MR. RAGAN:")
        assert result is not None
        assert len(result) == 2
        assert all(w.speaker == "MR. RAGAN:" for w in result)
        # Other fields preserved.
        assert result[0].text == "hello"
        assert result[0].start == 0.0
        assert result[1].text == "there"

    def test_propagate_returns_new_instances_not_mutated_input(self):
        original_word = _word("hello", 0.0, 0.2, speaker=0)
        words = [original_word]
        result = _propagate_speaker_to_words(words, "MR. RAGAN:")
        # Original word unchanged.
        assert original_word.speaker == 0
        # New instance returned.
        assert result[0] is not original_word

    def test_propagate_none_returns_none(self):
        assert _propagate_speaker_to_words(None, "MR. RAGAN:") is None


# ----------------------------------------------------------------------------
# speaker_mapper — smooth_speaker_sequence
# ----------------------------------------------------------------------------


class TestSpeakerMapperSmooth:
    def test_smooth_rebuilds_words_with_new_speaker(self):
        # A→B→A pattern where middle block is short — should be reassigned to A.
        before = TranscriptBlock(speaker="A", text="Long text here.", type="colloquy")
        middle_words = [_word("uh", 0.0, 0.1, speaker=1)]
        middle = TranscriptBlock(
            speaker="B",
            text="uh",  # < 6 words triggers smoothing
            type="colloquy",
            words=middle_words,
        )
        after = TranscriptBlock(speaker="A", text="Continuing here.", type="colloquy")

        result = smooth_speaker_sequence([before, middle, after])
        assert result[1].speaker == "A"
        assert result[1].words is not None
        assert len(result[1].words) == 1
        # The word's speaker has been propagated to "A".
        assert result[1].words[0].speaker == "A"
        # Original word unchanged.
        assert middle_words[0].speaker == 1

    def test_smooth_preserves_none_words(self):
        before = TranscriptBlock(speaker="A", text="Long text here.", type="colloquy")
        middle = TranscriptBlock(
            speaker="B", text="uh", type="colloquy", words=None,
        )
        after = TranscriptBlock(speaker="A", text="Continuing here.", type="colloquy")
        result = smooth_speaker_sequence([before, middle, after])
        assert result[1].speaker == "A"
        assert result[1].words is None

    def test_smooth_no_reassignment_preserves_identity(self):
        # No smoothing case — words list should pass through unchanged
        # (smooth_speaker_sequence builds a list copy via `list(blocks)`
        # but only reconstructs blocks where smoothing fires).
        words = [_word("hello", 0.0, 0.2)]
        block = TranscriptBlock(
            speaker="A", text="Hello there.", type="colloquy", words=words,
        )
        result = smooth_speaker_sequence([block, block, block])
        # No A→B→A pattern → no reassignment → same list reference.
        assert result[1].words is words


# ----------------------------------------------------------------------------
# speaker_mapper — normalize_speakers
# ----------------------------------------------------------------------------


class TestSpeakerMapperNormalize:
    def test_normalize_propagates_speaker_label_to_words(self):
        words = [
            _word("the", 0.0, 0.2, speaker=0),
            _word("witness", 0.3, 0.7, speaker=0),
        ]
        block = TranscriptBlock(
            speaker="mr. ragan",  # lowercase, no colon
            text="The witness.",
            type="colloquy",
            words=words,
        )
        result = normalize_speakers([block])
        # Normalized speaker label.
        assert result[0].speaker == "MR. RAGAN:"
        # Per-word speaker matches.
        assert result[0].words is not None
        assert all(w.speaker == "MR. RAGAN:" for w in result[0].words)
        # Original words list untouched.
        assert all(w.speaker == 0 for w in words)

    def test_normalize_preserves_none_words(self):
        block = TranscriptBlock(
            speaker="mr. ragan", text="Hello.", type="colloquy", words=None,
        )
        result = normalize_speakers([block])
        assert result[0].words is None
