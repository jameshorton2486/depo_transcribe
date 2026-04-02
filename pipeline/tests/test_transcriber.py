from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import transcriber


def test_transcribe_chunk_sends_utt_split_to_deepgram(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    captured = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "results": {
                    "channels": [
                        {
                            "alternatives": [
                                {
                                    "transcript": "Test transcript.",
                                    "words": [],
                                }
                            ]
                        }
                    ],
                    "utterances": [],
                }
            },
        )

    monkeypatch.setattr(transcriber.os, "getenv", lambda key, default="": "test-key")
    monkeypatch.setattr(transcriber.httpx, "post", fake_post)
    monkeypatch.setattr(transcriber, "merge_utterances", lambda utterances, gap_threshold_seconds, min_word_count: utterances)

    transcriber.transcribe_chunk(str(audio_path), utt_split=0.7)

    params = parse_qs(urlparse(captured["url"]).query)

    assert params["utt_split"] == ["0.7"]
