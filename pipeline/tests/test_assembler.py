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
