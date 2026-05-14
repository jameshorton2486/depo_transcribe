"""Schema-v2 contract checks for the current immutable raw-store payload."""
from __future__ import annotations

import json

from pipeline.raw_store import save_raw_response


def _chunk(
    transcript: str,
    request_id: str,
    speaker: int = 0,
    start: float = 0.0,
    end: float = 1.0,
) -> dict:
    return {
        "raw": {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": transcript,
                                "words": [
                                    {
                                        "word": transcript.split()[0],
                                        "start": start,
                                        "end": end,
                                        "confidence": 0.99,
                                        "speaker": speaker,
                                    }
                                ],
                            }
                        ]
                    }
                ],
                "utterances": [
                    {
                        "speaker": speaker,
                        "start": start,
                        "end": end,
                        "transcript": transcript,
                        "confidence": 0.99,
                        "words": [],
                    }
                ],
            },
            "metadata": {"request_id": request_id},
        }
    }


def test_schema_v2_payload_captures_current_provenance_contract(tmp_path):
    result = save_raw_response(
        tmp_path,
        chunk_results=[
            _chunk("First chunk.", "req-1", start=0.0, end=1.0),
            _chunk("Second chunk.", "req-2", start=10.0, end=11.0),
        ],
        chunk_offsets=[0.0, 600.0],
        audio_file="C:/cases/example/audio.wav",
        model="nova-3-medical",
        request_params={
            "model": "nova-3-medical",
            "language": "en",
            "diarize": "true",
            "utt_split": "0.8",
            "keyterm": ["Mohammad Etminan", "laminectomy"],
        },
        keyterms=["Mohammad Etminan", "laminectomy"],
        timestamp="20260513_130000",
    )

    payload = json.loads(result.path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 2
    assert payload["audio_file"] == "C:/cases/example/audio.wav"
    assert payload["model"] == "nova-3-medical"
    assert payload["chunk_count"] == 2
    assert payload["request_params"]["utt_split"] == "0.8"
    assert payload["request_params"]["keyterm"] == [
        "Mohammad Etminan",
        "laminectomy",
    ]
    assert payload["keyterms_sent"] == ["Mohammad Etminan", "laminectomy"]
    assert payload["chunks"][0]["index"] == 0
    assert payload["chunks"][0]["start_seconds"] == 0.0
    assert payload["chunks"][0]["deepgram_response"]["metadata"]["request_id"] == "req-1"
    assert payload["chunks"][1]["index"] == 1
    assert payload["chunks"][1]["start_seconds"] == 600.0
    assert payload["chunks"][1]["deepgram_response"]["metadata"]["request_id"] == "req-2"
