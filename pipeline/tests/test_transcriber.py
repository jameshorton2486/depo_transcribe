from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import transcriber


def test_transcribe_chunk_sends_utt_split_to_deepgram(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    captured = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        return SimpleNamespace(
            status_code=200,
            text="",
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
                    "utterances": [
                        {
                            "speaker": 0,
                            "start": 0.0,
                            "end": 1.0,
                            "transcript": "Test transcript.",
                            "confidence": 0.99,
                            "words": [],
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(transcriber.os, "getenv", lambda key, default="": "test-key")
    monkeypatch.setattr(transcriber.httpx, "post", fake_post)
    monkeypatch.setattr(transcriber, "merge_utterances", lambda utterances, gap_threshold_seconds, min_word_count: utterances)

    transcriber.transcribe_chunk(str(audio_path), utt_split=0.7)

    params = parse_qs(urlparse(captured["url"]).query)

    assert params["utt_split"] == ["0.7"]


def test_transcribe_chunk_uses_legal_safe_defaults(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    captured = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        return SimpleNamespace(
            status_code=200,
            text="",
            raise_for_status=lambda: None,
            json=lambda: {
                "results": {
                    "channels": [
                        {
                            "alternatives": [
                                {
                                    "transcript": "Uh, I think so.",
                                    "words": [],
                                }
                            ]
                        }
                    ],
                    "utterances": [
                        {
                            "speaker": 0,
                            "start": 0.0,
                            "end": 1.0,
                            "transcript": "Uh, I think so.",
                            "confidence": 0.99,
                            "words": [],
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(transcriber.os, "getenv", lambda key, default="": "test-key")
    monkeypatch.setattr(transcriber.httpx, "post", fake_post)
    monkeypatch.setattr(transcriber, "merge_utterances", lambda utterances, gap_threshold_seconds, min_word_count: utterances)

    transcriber.transcribe_chunk(str(audio_path), model="nova-3")

    params = parse_qs(urlparse(captured["url"]).query)

    assert params["model"] == ["nova-3"]
    assert params["punctuate"] == ["true"]
    assert params["paragraphs"] == ["false"]
    assert params["diarize"] == ["true"]
    assert params["utterances"] == ["true"]
    assert params["filler_words"] == ["true"]
    assert params["smart_format"] == ["false"]
    assert params["numerals"] == ["false"]
    assert "diarize=True" not in captured["url"]
    assert "paragraphs=True" not in captured["url"]


def test_transcribe_chunk_includes_keyterms_in_request(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    captured = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        return SimpleNamespace(
            status_code=200,
            text="",
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
                    "utterances": [
                        {
                            "speaker": 0,
                            "start": 0.0,
                            "end": 1.0,
                            "transcript": "Test transcript.",
                            "confidence": 0.99,
                            "words": [],
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(transcriber.os, "getenv", lambda key, default="": "test-key")
    monkeypatch.setattr(transcriber.httpx, "post", fake_post)
    monkeypatch.setattr(transcriber, "merge_utterances", lambda utterances, gap_threshold_seconds, min_word_count: utterances)

    transcriber.transcribe_chunk(str(audio_path), keyterms=["Matthew Coger", "Murphy Oil"])

    params = parse_qs(urlparse(captured["url"]).query)

    assert params["keyterm"] == ["Matthew Coger", "Murphy Oil"]


def test_validate_deepgram_params_rejects_uppercase_boolean_strings():
    try:
        transcriber.validate_deepgram_params({"diarize": "True"})
    except ValueError as exc:
        assert "lowercase 'true'/'false'" in str(exc)
    else:
        raise AssertionError("Expected validate_deepgram_params to reject uppercase boolean strings")


def test_normalize_params_preserves_false_values_and_all_keys():
    params = transcriber.normalize_params(
        {
            "utterances": True,
            "paragraphs": False,
            "utt_split": 1.2,
            "language": "en",
        }
    )

    assert params == {
        "utterances": "true",
        "paragraphs": "false",
        "utt_split": 1.2,
        "language": "en",
    }


def test_enforce_required_deepgram_flags_overrides_invalid_values():
    params = transcriber.enforce_required_deepgram_flags(
        {"utterances": "false", "diarize": "false", "paragraphs": "true"}
    )

    assert params["utterances"] == "true"
    assert params["diarize"] == "true"
    assert params["paragraphs"] == "false"


def test_transcribe_chunk_logs_params_and_utterance_count(monkeypatch, tmp_path, capsys):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    def fake_post(url, content=None, headers=None, timeout=None):
        return SimpleNamespace(
            status_code=200,
            text="",
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
                    "utterances": [
                        {
                            "speaker": 0,
                            "start": 0.0,
                            "end": 1.0,
                            "transcript": "Test transcript.",
                            "confidence": 0.99,
                            "words": [],
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(transcriber.os, "getenv", lambda key, default="": "test-key")
    monkeypatch.setattr(transcriber.httpx, "post", fake_post)
    monkeypatch.setattr(
        transcriber,
        "merge_utterances",
        lambda utterances, gap_threshold_seconds, min_word_count: utterances,
    )

    transcriber.transcribe_chunk(str(audio_path))

    captured = capsys.readouterr()
    assert "DEEPGRAM PARAMS:" in captured.out
    assert "'utterances': 'true'" in captured.out
    assert "Utterances received: 1" in captured.out


def test_transcribe_chunk_returns_raw_and_merged_utterances(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    raw_utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 0.5,
            "transcript": "Well,",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 0,
            "start": 0.5,
            "end": 1.0,
            "transcript": "I do two things.",
            "confidence": 0.99,
            "words": [],
        },
    ]
    merged_utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 1.0,
            "transcript": "Well, I do two things.",
            "confidence": 0.99,
            "words": [],
        },
    ]

    def fake_post(url, content=None, headers=None, timeout=None):
        return SimpleNamespace(
            status_code=200,
            text="",
            raise_for_status=lambda: None,
            json=lambda: {
                "results": {
                    "channels": [
                        {
                            "alternatives": [
                                {
                                    "transcript": "Well, I do two things.",
                                    "words": [],
                                }
                            ]
                        }
                    ],
                    "utterances": raw_utterances,
                }
            },
        )

    monkeypatch.setattr(transcriber.os, "getenv", lambda key, default="": "test-key")
    monkeypatch.setattr(transcriber.httpx, "post", fake_post)
    monkeypatch.setattr(
        transcriber,
        "merge_utterances",
        lambda utterances, gap_threshold_seconds, min_word_count: merged_utterances,
    )

    result = transcriber.transcribe_chunk(str(audio_path))

    assert result["raw_utterances"] == raw_utterances
    assert result["utterances"] == merged_utterances


def test_transcribe_chunk_rejects_missing_utterances(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    def fake_post(url, content=None, headers=None, timeout=None):
        return SimpleNamespace(
            status_code=200,
            text="",
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

    with pytest.raises(RuntimeError, match="no utterances; transcription cannot proceed"):
        transcriber.transcribe_chunk(str(audio_path))
