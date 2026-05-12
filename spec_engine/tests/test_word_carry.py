"""Step B.0 — word-object metadata carry through the data model.

Coverage:
  1. Backward compatibility — TranscriptBlock constructible with the
     original 5-arg signature (no `words`). This protects the 14
     existing construction sites in qa_fixer, speaker_mapper,
     corrections, emitter, and tests until B.1 lands.
  2. TranscriptWord dataclass shape.
  3. block_builder populates `words` from alt["words"] in the
     paragraph path when partitioning is unambiguous.
  4. block_builder returns words=None when source data is missing or
     ambiguous (graceful degradation).
  5. block_builder populates `words` from utterance["words"] in the
     fallback path.
  6. classifier converts raw word dicts to TranscriptWord instances.
  7. classifier returns words=None when any word dict is malformed
     (all-or-nothing degradation).
  8. apply_corrections preserves words through the corrections pass.
"""

from __future__ import annotations

from spec_engine.block_builder import build_blocks
from spec_engine.classifier import classify_blocks
from spec_engine.corrections import apply_corrections
from spec_engine.models import TranscriptBlock, TranscriptWord


# ----------------------------------------------------------------------------
# Backward compatibility
# ----------------------------------------------------------------------------


class TestBackwardCompat:
    """Existing TranscriptBlock construction patterns must not break."""

    def test_three_positional_args(self):
        block = TranscriptBlock("Q", "Did you see it?", "question")
        assert block.speaker == "Q"
        assert block.text == "Did you see it?"
        assert block.type == "question"
        assert block.source_type == ""
        assert block.examiner is None
        assert block.words is None

    def test_five_positional_args(self):
        block = TranscriptBlock(
            "Q", "Question text", "question", "paragraph", "MR. RAGAN"
        )
        assert block.examiner == "MR. RAGAN"
        assert block.words is None

    def test_keyword_args_without_words(self):
        block = TranscriptBlock(
            speaker="A",
            text="The answer.",
            type="answer",
            source_type="utterance",
        )
        assert block.words is None

    def test_keyword_args_with_explicit_none_words(self):
        block = TranscriptBlock(
            speaker="A",
            text="The answer.",
            type="answer",
            words=None,
        )
        assert block.words is None


# ----------------------------------------------------------------------------
# TranscriptWord dataclass
# ----------------------------------------------------------------------------


class TestTranscriptWordShape:
    def test_minimal_construction(self):
        word = TranscriptWord(text="hello", start=0.0, end=0.3, confidence=0.95)
        assert word.text == "hello"
        assert word.start == 0.0
        assert word.end == 0.3
        assert word.confidence == 0.95
        assert word.speaker is None
        assert word.punctuated_word is None

    def test_full_construction(self):
        word = TranscriptWord(
            text="hello",
            start=0.0,
            end=0.3,
            confidence=0.95,
            speaker=0,
            punctuated_word="Hello",
        )
        assert word.speaker == 0
        assert word.punctuated_word == "Hello"

    def test_speaker_accepts_string_label(self):
        # After B.1, speaker_mapper propagates string labels here.
        word = TranscriptWord(
            text="hello", start=0.0, end=0.3, confidence=0.95, speaker="MR. RAGAN"
        )
        assert word.speaker == "MR. RAGAN"


# ----------------------------------------------------------------------------
# block_builder — paragraph path
# ----------------------------------------------------------------------------


def _paragraph_alt() -> dict:
    """Synthetic Deepgram alt with paragraphs and word-level timing."""
    return {
        "transcript": "Yes I saw it. Did you see the car?",
        "words": [
            {"word": "yes", "start": 0.0, "end": 0.3, "confidence": 0.95,
             "speaker": 0, "punctuated_word": "Yes"},
            {"word": "i", "start": 0.4, "end": 0.5, "confidence": 0.97,
             "speaker": 0, "punctuated_word": "I"},
            {"word": "saw", "start": 0.6, "end": 0.9, "confidence": 0.92,
             "speaker": 0, "punctuated_word": "saw"},
            {"word": "it", "start": 1.0, "end": 1.3, "confidence": 0.94,
             "speaker": 0, "punctuated_word": "it."},
            {"word": "did", "start": 2.0, "end": 2.2, "confidence": 0.98,
             "speaker": 1, "punctuated_word": "Did"},
            {"word": "you", "start": 2.3, "end": 2.5, "confidence": 0.96,
             "speaker": 1, "punctuated_word": "you"},
            {"word": "see", "start": 2.6, "end": 2.9, "confidence": 0.95,
             "speaker": 1, "punctuated_word": "see"},
            {"word": "the", "start": 3.0, "end": 3.2, "confidence": 0.99,
             "speaker": 1, "punctuated_word": "the"},
            {"word": "car", "start": 3.3, "end": 3.8, "confidence": 0.93,
             "speaker": 1, "punctuated_word": "car?"},
        ],
        "paragraphs": {
            "paragraphs": [
                {"speaker": 0, "text": "Yes I saw it.",
                 "start": 0.0, "end": 1.3},
                {"speaker": 1, "text": "Did you see the car?",
                 "start": 2.0, "end": 3.8},
            ]
        },
    }


class TestParagraphPathPopulation:
    def test_words_partitioned_to_correct_paragraph(self):
        blocks = build_blocks(_paragraph_alt())
        assert len(blocks) == 2
        # First paragraph: 4 words (yes, i, saw, it)
        assert blocks[0]["words"] is not None
        assert len(blocks[0]["words"]) == 4
        assert [w["word"] for w in blocks[0]["words"]] == ["yes", "i", "saw", "it"]
        # Second paragraph: 5 words (did, you, see, the, car)
        assert blocks[1]["words"] is not None
        assert len(blocks[1]["words"]) == 5
        assert [w["word"] for w in blocks[1]["words"]] == [
            "did", "you", "see", "the", "car",
        ]

    def test_paragraph_without_time_bounds_gives_none(self):
        alt = _paragraph_alt()
        # Strip start/end from second paragraph
        alt["paragraphs"]["paragraphs"][1].pop("start")
        alt["paragraphs"]["paragraphs"][1].pop("end")
        blocks = build_blocks(alt)
        assert blocks[0]["words"] is not None
        assert blocks[1]["words"] is None

    def test_empty_words_array_gives_none(self):
        alt = _paragraph_alt()
        alt["words"] = []
        blocks = build_blocks(alt)
        assert all(b["words"] is None for b in blocks)

    def test_missing_words_key_gives_none(self):
        alt = _paragraph_alt()
        alt.pop("words")
        blocks = build_blocks(alt)
        assert all(b["words"] is None for b in blocks)


# ----------------------------------------------------------------------------
# block_builder — utterance fallback path
# ----------------------------------------------------------------------------


def _utterance_alt() -> dict:
    """Synthetic alt with utterances at alt level (per block_builder
    contract — the live code uses alt['utterances'], even though
    Deepgram puts utterances at the results level)."""
    return {
        "transcript": "Yes.",
        "words": [],
        # No paragraphs key → block_builder uses the utterance fallback.
        "utterances": [
            {
                "speaker": 0,
                "text": "Yes.",
                "words": [
                    {"word": "yes", "start": 0.0, "end": 0.3,
                     "confidence": 0.95, "speaker": 0,
                     "punctuated_word": "Yes."},
                ],
            }
        ],
    }


class TestUttFallbackPopulation:
    def test_utterance_words_copied_directly(self):
        blocks = build_blocks(_utterance_alt())
        assert len(blocks) == 1
        assert blocks[0]["words"] is not None
        assert len(blocks[0]["words"]) == 1
        assert blocks[0]["words"][0]["word"] == "yes"

    def test_utterance_without_words_gives_none(self):
        alt = _utterance_alt()
        alt["utterances"][0].pop("words")
        blocks = build_blocks(alt)
        assert blocks[0]["words"] is None


# ----------------------------------------------------------------------------
# classifier — dict-to-TranscriptWord conversion
# ----------------------------------------------------------------------------


class TestClassifierWordConversion:
    def test_blocks_get_transcript_word_instances(self):
        blocks = build_blocks(_paragraph_alt())
        classified = classify_blocks(blocks)
        assert len(classified) == 2
        assert classified[0].words is not None
        assert all(isinstance(w, TranscriptWord) for w in classified[0].words)

    def test_word_fields_propagate(self):
        blocks = build_blocks(_paragraph_alt())
        classified = classify_blocks(blocks)
        first = classified[0].words[0]
        assert first.text == "yes"
        assert first.start == 0.0
        assert first.end == 0.3
        assert first.confidence == 0.95
        assert first.speaker == 0
        assert first.punctuated_word == "Yes"

    def test_malformed_word_dict_gives_none(self):
        blocks = [
            {"speaker": 0, "text": "Yes.", "type": "paragraph",
             "words": [{"start": 0.0, "end": 0.3, "confidence": 0.9}]},
            # missing "word" key
        ]
        classified = classify_blocks(blocks)
        assert classified[0].words is None

    def test_block_with_words_none_stays_none(self):
        blocks = [
            {"speaker": 0, "text": "Yes.", "type": "paragraph", "words": None},
        ]
        classified = classify_blocks(blocks)
        assert classified[0].words is None

    def test_block_without_words_key_stays_none(self):
        # Simulates a pre-B.0 dict format (no "words" key at all).
        blocks = [{"speaker": 0, "text": "Yes.", "type": "paragraph"}]
        classified = classify_blocks(blocks)
        assert classified[0].words is None


# ----------------------------------------------------------------------------
# corrections.apply_corrections — words pass through
# ----------------------------------------------------------------------------


class TestCorrectionsPassThrough:
    def test_apply_corrections_preserves_words(self):
        words = [
            TranscriptWord(text="yes", start=0.0, end=0.3, confidence=0.95,
                           speaker=0, punctuated_word="Yes"),
            TranscriptWord(text="i", start=0.4, end=0.5, confidence=0.97,
                           speaker=0, punctuated_word="I"),
        ]
        block = TranscriptBlock(
            speaker="speaker 0",
            text="yes i went there",
            type="answer",
            words=words,
        )
        corrected = apply_corrections([block])
        assert len(corrected) == 1
        # Text may be edited by morsons rules; words array must be unchanged.
        assert corrected[0].words is not None
        assert len(corrected[0].words) == 2
        assert corrected[0].words[0].text == "yes"
        assert corrected[0].words[1].text == "i"

    def test_apply_corrections_preserves_none_words(self):
        block = TranscriptBlock(
            speaker="speaker 0",
            text="yes i went there",
            type="answer",
            words=None,
        )
        corrected = apply_corrections([block])
        assert corrected[0].words is None
