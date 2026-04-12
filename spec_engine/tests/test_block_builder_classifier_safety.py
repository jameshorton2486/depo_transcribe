import pytest

from spec_engine.block_builder import build_blocks_from_deepgram
from spec_engine.classifier import classify_blocks
from spec_engine.models import Block, BlockType
from spec_engine.processor import process_blocks


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


def test_build_blocks_from_deepgram_rejects_empty_utterances_even_with_transcript_blob():
    with pytest.raises(RuntimeError, match="no utterances-backed blocks"):
        build_blocks_from_deepgram(
            {
                "utterances": [],
                "transcript": "Fallback transcript text.",
            }
        )


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


def test_classify_blocks_recovers_short_attorney_mislabel_after_question():
    blocks = [
        Block(
            speaker_id=2,
            text="Did you understand the question?",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MR. DAVIS",
        ),
        Block(
            speaker_id=3,
            text="Correct.",
            raw_text="",
            speaker_role="OPPOSING_COUNSEL",
            speaker_name="MR. SICONI",
        ),
    ]

    results = classify_blocks(
        blocks,
        job_config={"examining_attorney_id": 2, "speaker_map_verified": True},
    )

    assert results[0].block_type == BlockType.QUESTION
    assert results[1].block_type == BlockType.ANSWER


def test_process_blocks_rejects_objects_without_speaker_id():
    class BrokenBlock:
        text = "Test."
        raw_text = "Test."

    with pytest.raises(RuntimeError, match="speaker_id"):
        process_blocks([BrokenBlock()], job_config={})
