from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import assembler


def test_merge_with_overlap_removes_exact_duplicate_boundary():
    merged = assembler.merge_with_overlap(
        "this is a test of the system",
        "test of the system and more",
    )

    assert merged == "this is a test of the system and more"


def test_merge_with_overlap_keeps_non_overlapping_text():
    merged = assembler.merge_with_overlap("hello world", "completely different")

    assert merged == "hello world completely different"


def test_merge_with_overlap_handles_partial_boundary_phrase():
    merged = assembler.merge_with_overlap("beginning of the", "beginning of the edition")

    assert merged == "beginning of the edition"


def test_reassemble_chunks_normalizes_speaker_ids_across_overlap():
    chunk_results = [
        {
            "raw": {"chunk": 0},
            "transcript": "Speaker 0: hello there\n\nSpeaker 1: yes",
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.4, "speaker": 0},
                {"word": "there", "start": 0.4, "end": 0.8, "speaker": 0},
                {"word": "yes", "start": 0.9, "end": 1.2, "speaker": 1},
            ],
            "utterances": [
                {"speaker": 0, "transcript": "hello there", "start": 0.0, "end": 0.8},
                {"speaker": 1, "transcript": "yes", "start": 0.9, "end": 1.2},
            ],
        },
        {
            "raw": {"chunk": 1},
            "transcript": "Speaker 0: yes\n\nSpeaker 1: next answer",
            "words": [
                {"word": "yes", "start": 0.0, "end": 0.3, "speaker": 0},
                {"word": "next", "start": 0.4, "end": 0.8, "speaker": 1},
                {"word": "answer", "start": 0.8, "end": 1.2, "speaker": 1},
            ],
            "utterances": [
                {"speaker": 0, "transcript": "yes", "start": 0.0, "end": 0.3},
                {"speaker": 1, "transcript": "next answer", "start": 0.4, "end": 1.2},
            ],
        },
    ]

    merged = assembler.reassemble_chunks(chunk_results, chunk_start_offsets=[0.0, 0.9])

    assert [u["speaker"] for u in merged["utterances"]] == [0, 1, 1]
    assert [u["speaker_label"] for u in merged["utterances"]] == [
        "Speaker 0",
        "Speaker 1",
        "Speaker 1",
    ]
    assert [w["speaker"] for w in merged["words"]] == [0, 0, 1, 1, 1]
    assert [u["transcript"] for u in merged["utterances"]] == [
        "hello there",
        "yes",
        "next answer",
    ]


def test_reassemble_chunks_merges_same_speaker_overlap_text():
    chunk_results = [
        {
            "raw": {"chunk": 0},
            "transcript": "Speaker 0: beginning of the",
            "words": [
                {"word": "beginning", "start": 0.0, "end": 0.2, "speaker": 0},
                {"word": "of", "start": 0.2, "end": 0.3, "speaker": 0},
                {"word": "the", "start": 0.3, "end": 0.4, "speaker": 0},
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "transcript": "beginning of the",
                    "start": 0.0,
                    "end": 0.4,
                    "words": [
                        {"word": "beginning", "start": 0.0, "end": 0.2, "speaker": 0},
                        {"word": "of", "start": 0.2, "end": 0.3, "speaker": 0},
                        {"word": "the", "start": 0.3, "end": 0.4, "speaker": 0},
                    ],
                },
            ],
        },
        {
            "raw": {"chunk": 1},
            "transcript": "Speaker 0: beginning of the edition",
            "words": [
                {"word": "beginning", "start": 0.0, "end": 0.2, "speaker": 0},
                {"word": "of", "start": 0.2, "end": 0.3, "speaker": 0},
                {"word": "the", "start": 0.3, "end": 0.4, "speaker": 0},
                {"word": "edition", "start": 0.4, "end": 0.7, "speaker": 0},
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "transcript": "beginning of the edition",
                    "start": 0.0,
                    "end": 0.7,
                    "words": [
                        {"word": "beginning", "start": 0.0, "end": 0.2, "speaker": 0},
                        {"word": "of", "start": 0.2, "end": 0.3, "speaker": 0},
                        {"word": "the", "start": 0.3, "end": 0.4, "speaker": 0},
                        {"word": "edition", "start": 0.4, "end": 0.7, "speaker": 0},
                    ],
                },
            ],
        },
    ]

    merged = assembler.reassemble_chunks(chunk_results, chunk_start_offsets=[0.0, 0.2])

    assert [u["transcript"] for u in merged["utterances"]] == ["beginning of the edition"]
    assert merged["transcript"] == "Speaker 0: beginning of the edition"


def test_reassemble_chunks_merges_same_speaker_sentence_continuation_across_boundary():
    chunk_results = [
        {
            "raw": {"chunk": 0},
            "transcript": "Speaker 0: Good afternoon,",
            "words": [
                {"word": "Good", "start": 0.0, "end": 0.2, "speaker": 0},
                {"word": "afternoon", "start": 0.2, "end": 0.5, "speaker": 0},
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "transcript": "Good afternoon,",
                    "start": 0.0,
                    "end": 0.5,
                    "words": [
                        {"word": "Good", "start": 0.0, "end": 0.2, "speaker": 0},
                        {"word": "afternoon", "start": 0.2, "end": 0.5, "speaker": 0},
                    ],
                },
            ],
        },
        {
            "raw": {"chunk": 1},
            "transcript": "Speaker 0: Doctor Leifer.",
            "words": [
                {"word": "Doctor", "start": 0.0, "end": 0.2, "speaker": 0},
                {"word": "Leifer", "start": 0.2, "end": 0.5, "speaker": 0},
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "transcript": "Doctor Leifer.",
                    "start": 0.0,
                    "end": 0.5,
                    "words": [
                        {"word": "Doctor", "start": 0.0, "end": 0.2, "speaker": 0},
                        {"word": "Leifer", "start": 0.2, "end": 0.5, "speaker": 0},
                    ],
                },
            ],
        },
    ]

    merged = assembler.reassemble_chunks(chunk_results, chunk_start_offsets=[0.0, 0.5])

    assert [u["transcript"] for u in merged["utterances"]] == ["Good afternoon, Doctor Leifer."]
    assert merged["transcript"] == "Speaker 0: Good afternoon, Doctor Leifer."


def test_reassemble_chunks_keeps_same_speaker_complete_sentences_separate():
    chunk_results = [
        {
            "raw": {"chunk": 0},
            "transcript": "Speaker 0: I do two things.",
            "words": [
                {"word": "I", "start": 0.0, "end": 0.1, "speaker": 0},
                {"word": "do", "start": 0.1, "end": 0.2, "speaker": 0},
                {"word": "two", "start": 0.2, "end": 0.3, "speaker": 0},
                {"word": "things", "start": 0.3, "end": 0.5, "speaker": 0},
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "transcript": "I do two things.",
                    "start": 0.0,
                    "end": 0.5,
                    "words": [
                        {"word": "I", "start": 0.0, "end": 0.1, "speaker": 0},
                        {"word": "do", "start": 0.1, "end": 0.2, "speaker": 0},
                        {"word": "two", "start": 0.2, "end": 0.3, "speaker": 0},
                        {"word": "things", "start": 0.3, "end": 0.5, "speaker": 0},
                    ],
                },
            ],
        },
        {
            "raw": {"chunk": 1},
            "transcript": "Speaker 0: I am on the faculty.",
            "words": [
                {"word": "I", "start": 0.0, "end": 0.1, "speaker": 0},
                {"word": "am", "start": 0.1, "end": 0.2, "speaker": 0},
                {"word": "on", "start": 0.2, "end": 0.3, "speaker": 0},
                {"word": "the", "start": 0.3, "end": 0.4, "speaker": 0},
                {"word": "faculty", "start": 0.4, "end": 0.7, "speaker": 0},
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "transcript": "I am on the faculty.",
                    "start": 0.0,
                    "end": 0.7,
                    "words": [
                        {"word": "I", "start": 0.0, "end": 0.1, "speaker": 0},
                        {"word": "am", "start": 0.1, "end": 0.2, "speaker": 0},
                        {"word": "on", "start": 0.2, "end": 0.3, "speaker": 0},
                        {"word": "the", "start": 0.3, "end": 0.4, "speaker": 0},
                        {"word": "faculty", "start": 0.4, "end": 0.7, "speaker": 0},
                    ],
                },
            ],
        },
    ]

    merged = assembler.reassemble_chunks(chunk_results, chunk_start_offsets=[0.0, 0.6])

    assert [u["transcript"] for u in merged["utterances"]] == [
        "I do two things.",
        "I am on the faculty.",
    ]


def test_merge_channel_assemblies_keeps_channels_as_separate_speakers():
    left = {
        "words": [
            {"word": "question", "start": 0.0, "end": 0.5, "speaker": 0},
        ],
        "utterances": [
            {"speaker": 0, "transcript": "question", "start": 0.0, "end": 0.5},
        ],
        "transcript": "Speaker 0: question",
        "raw_chunks": [{"chunk": "left"}],
    }
    right = {
        "words": [
            {"word": "answer", "start": 0.2, "end": 0.7, "speaker": 0},
        ],
        "utterances": [
            {"speaker": 0, "transcript": "answer", "start": 0.2, "end": 0.7},
        ],
        "transcript": "Speaker 0: answer",
        "raw_chunks": [{"chunk": "right"}],
    }

    merged = assembler.merge_channel_assemblies([left, right])

    assert [u["speaker"] for u in merged["utterances"]] == [0, 1]
    assert [u["speaker_label"] for u in merged["utterances"]] == ["Speaker 0", "Speaker 1"]
    assert [w["speaker"] for w in merged["words"]] == [0, 1]
    assert merged["transcript"] == "Speaker 0: question\n\nSpeaker 1: answer"
    assert merged["raw_chunks"] == [
        {"channel": 0, "raw": {"chunk": "left"}},
        {"channel": 1, "raw": {"chunk": "right"}},
    ]
