from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import assembler


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
