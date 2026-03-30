import pytest

from pipeline.processor import run_pipeline
from spec_engine.models import BlockType


@pytest.mark.skip(reason="Output format and line wrapping not yet implemented — Phase 2 task")
def test_inline_question_answer_split():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 2,
                    "transcript": "Did you go there? Yes.",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {1: "THE WITNESS", 2: "EXAMINING ATTORNEY"},
            "witness_id": 1,
            "examining_attorney_id": 2,
            "cause_number": "TEST-QA-SPLIT",
        },
    )

    text = result["text"]
    assert "Q.\tDid you go there?" in text
    assert "A.\tYes." in text


def test_answer_without_yes_no():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 1,
                    "transcript": "I went there last week.",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {1: "THE WITNESS"},
            "witness_id": 1,
            "cause_number": "TEST-ANSWER",
        },
    )

    blocks = result["blocks"]
    assert blocks[0].block_type == BlockType.ANSWER


def test_objection_extraction_exit_form():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 2,
                    "transcript": "I don't recall. Exit form.",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {2: "THE WITNESS"},
            "witness_id": 2,
            "defense_counsel": "MR. SMITH",
            "cause_number": "TEST-OBJ",
        },
    )

    text = result["text"]
    assert "Objection. Form." in text


def test_question_detection_without_question_mark():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 2,
                    "transcript": "State your name",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {2: "MR. SMITH"},
            "cause_number": "TEST-NO-QMARK",
        },
    )

    blocks = result["blocks"]
    assert blocks[0].block_type == BlockType.QUESTION


def test_colloquy_detection():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 3,
                    "transcript": "Let's go off the record.",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {3: "THE REPORTER"},
            "cause_number": "TEST-COLLOQUY",
        },
    )

    blocks = result["blocks"]
    assert blocks[0].block_type in (BlockType.COLLOQUY, BlockType.SPEAKER)


def test_time_normalization():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 1,
                    "transcript": "The time is 10:30 AM.",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {1: "THE REPORTER"},
            "cause_number": "TEST-TIME",
        },
    )

    text = result["text"]
    assert "10:30 a.m." in text


def test_dash_normalization():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 1,
                    "transcript": "This — is a test.",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {1: "THE WITNESS"},
            "witness_id": 1,
            "cause_number": "TEST-DASH",
        },
    )

    text = result["text"]
    assert "--" in text


def test_formatter_outputs_tabs():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 2,
                    "transcript": "Did you go there?",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {2: "MR. SMITH"},
            "cause_number": "TEST-TABS",
        },
    )

    text = result["text"]
    assert "\tQ.  " in text


@pytest.mark.skip(reason="Output format and line wrapping not yet implemented — Phase 2 task")
def test_formatter_wraps_lines():
    long_text = (
        "This is a very long sentence that should exceed the wrapping width "
        "and be split into multiple lines properly."
    )

    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 1,
                    "transcript": long_text,
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {1: "THE WITNESS"},
            "witness_id": 1,
            "cause_number": "TEST-WRAP",
        },
    )

    text = result["text"]
    assert "\n" in text


def test_missing_utterances_fallback():
    result = run_pipeline(
        {
            "transcript": "Fallback transcript text."
        },
        {"speaker_map": {}, "cause_number": "TEST-FALLBACK"},
    )

    text = result["text"]
    assert "Fallback transcript text." in text


def test_empty_input_raises():
    with pytest.raises(ValueError):
        run_pipeline({}, {})
