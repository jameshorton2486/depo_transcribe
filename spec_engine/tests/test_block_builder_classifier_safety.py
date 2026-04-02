import pytest

from spec_engine.block_builder import build_blocks_from_deepgram
from spec_engine.classifier import classify_blocks
from spec_engine.models import Block, BlockType


def test_build_blocks_from_deepgram_requires_utterances_key():
    with pytest.raises(ValueError, match="missing 'utterances'"):
        build_blocks_from_deepgram({"transcript": "Hello there."})


def test_build_blocks_from_deepgram_preserves_missing_speaker_as_none():
    blocks = build_blocks_from_deepgram(
        {
            "utterances": [
                {
                    "speaker": None,
                    "transcript": "Yes, sir.",
                    "words": [],
                }
            ]
        }
    )

    assert blocks[0].speaker_id is None


def test_build_blocks_from_deepgram_normalizes_missing_word_timing():
    blocks = build_blocks_from_deepgram(
        {
            "utterances": [
                {
                    "speaker": 1,
                    "transcript": "Yes, sir.",
                    "words": [
                        {"word": "Yes", "start": None, "end": None, "confidence": 0.9},
                        {"word": "sir", "start": 0.21, "end": None, "confidence": 0.88},
                    ],
                }
            ]
        }
    )

    assert blocks[0].words[0].start == 0.0
    assert blocks[0].words[0].end == 0.0
    assert blocks[0].words[1].start == 0.21
    assert blocks[0].words[1].end == 0.21


def test_classify_blocks_does_not_force_attorney_colloquy_into_answer():
    blocks = [
        Block(
            speaker_id=2,
            text="Did you go there?",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MR. ALLAN",
        ),
        Block(
            speaker_id=3,
            text="Let me rephrase that.",
            raw_text="",
            speaker_role="OPPOSING_COUNSEL",
            speaker_name="MR. BOYCE",
        ),
    ]

    results = classify_blocks(blocks)

    assert results[0].block_type == BlockType.QUESTION
    assert results[1].block_type == BlockType.COLLOQUY


def test_classify_blocks_still_allows_unknown_followup_to_be_answer():
    blocks = [
        Block(
            speaker_id=2,
            text="Did you go there?",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MR. ALLAN",
        ),
        Block(
            speaker_id=None,
            text="I did.",
            raw_text="",
        ),
    ]

    results = classify_blocks(blocks)

    assert results[0].block_type == BlockType.QUESTION
    assert results[1].block_type == BlockType.ANSWER
