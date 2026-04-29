from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import transcriber


def test_transcribe_chunk_sends_default_utt_split_to_deepgram(monkeypatch, tmp_path):
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

    transcriber.transcribe_chunk(str(audio_path))

    params = parse_qs(urlparse(captured["url"]).query)

    assert params["utt_split"] == ["0.8"]


def test_transcribe_chunk_uses_requested_defaults(monkeypatch, tmp_path):
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
    assert params["paragraphs"] == ["true"]
    assert params["diarize"] == ["true"]
    assert params["utterances"] == ["true"]
    assert params["utt_split"] == ["0.8"]
    assert params["filler_words"] == ["true"]
    assert params["smart_format"] == ["true"]
    assert params["numerals"] == ["true"]
    assert "diarize=True" not in captured["url"]
    assert "paragraphs=true" in captured["url"]


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
            "language": "en",
        }
    )

    assert params == {
        "utterances": "true",
        "paragraphs": "false",
        "language": "en",
    }


def test_enforce_required_deepgram_flags_overrides_invalid_values():
    params = transcriber.enforce_required_deepgram_flags(
        {
            "utterances": "false",
            "diarize": "false",
            "paragraphs": "false",
            "smart_format": "false",
            "numerals": "false",
            "utt_split": "1.2",
        }
    )

    assert params["utterances"] == "true"
    assert params["diarize"] == "true"
    assert params["paragraphs"] == "true"
    assert params["smart_format"] == "true"
    assert params["numerals"] == "true"
    assert params["utt_split"] == "0.8"


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
            "low_confidence": False,
        },
        {
            "speaker": 0,
            "start": 0.5,
            "end": 1.0,
            "transcript": "I do two things.",
            "confidence": 0.99,
            "words": [],
            "low_confidence": False,
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
            "low_confidence": False,
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


def test_transcribe_chunk_processes_near_silent_chunks_in_safe_mode(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio")

    post_called = {"value": False}

    def fake_post(url, content=None, headers=None, timeout=None):
        post_called["value"] = True
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
                                    "transcript": "Quiet testimony.",
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
                            "transcript": "Quiet testimony.",
                            "confidence": 0.99,
                            "words": [],
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(transcriber.os, "getenv", lambda key, default="": "test-key")
    monkeypatch.setattr(transcriber.httpx, "post", fake_post)
    monkeypatch.setattr(transcriber, "_probe_max_volume_db", lambda path: -60.0)
    monkeypatch.setattr(
        transcriber,
        "merge_utterances",
        lambda utterances, gap_threshold_seconds, min_word_count: utterances,
    )

    result = transcriber.transcribe_chunk(str(audio_path))

    assert post_called["value"] is True
    assert result["utterances"]
    assert result["raw_utterances"]
    assert (tmp_path / "sample_raw_utterances.json").exists()
    assert (tmp_path / "sample_merged_utterances.json").exists()


def test_merge_utterances_does_not_cross_speakers():
    utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 0.4,
            "transcript": "Hello there.",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 1,
            "start": 0.5,
            "end": 1.0,
            "transcript": "Different speaker.",
            "confidence": 0.99,
            "words": [],
        },
    ]

    result = transcriber.merge_utterances(utterances)

    assert len(result) == 2
    assert result[0]["speaker"] == 0
    assert result[1]["speaker"] == 1


def test_merge_utterances_merges_same_speaker_short_gap():
    utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 0.4,
            "transcript": "This is",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 0,
            "start": 0.7,
            "end": 1.1,
            "transcript": "a test.",
            "confidence": 0.99,
            "words": [],
        },
    ]

    result = transcriber.merge_utterances(utterances)

    assert len(result) == 1
    assert result[0]["transcript"] == "This is a test."
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 1.1


def test_merge_utterances_marks_low_confidence():
    utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 0.4,
            "transcript": "Quiet testimony.",
            "confidence": 0.81,
            "words": [],
        }
    ]

    result = transcriber.merge_utterances(utterances)

    assert result[0]["low_confidence"] is True


def test_smooth_speakers_corrects_short_flip_glitch():
    """A truly short A→B→A bounce (sub-200ms, non-answer text) still
    gets smoothed. This is the case the glitch heuristic exists for."""
    utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 0.4,
            "transcript": "Hello there.",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 1,
            "start": 0.45,
            "end": 0.55,  # 100ms — true sub-200ms glitch territory
            "transcript": "uh",
            "confidence": 0.40,
            "words": [],
        },
        {
            "speaker": 0,
            "start": 0.75,
            "end": 1.2,
            "transcript": "Continue.",
            "confidence": 0.99,
            "words": [],
        },
    ]

    result = transcriber.smooth_speakers(utterances)

    assert result[1]["speaker"] == 0


def test_smooth_speakers_preserves_short_witness_yes():
    """CONTRACT CHANGE: Witness saying 'Yes.' between two attorney lines
    must NOT be reassigned to the attorney's speaker, even when short.
    Previously _is_short_glitch + smooth_speakers erased these legitimate
    deposition responses. The whitelist in SHORT_ANSWER_WHITELIST
    guards against that."""
    utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 5.0,
            "transcript": "Do you solemnly swear to tell the truth?",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 1,
            "start": 5.2,
            "end": 5.45,  # 250ms — short, but a real witness "Yes."
            "transcript": "Yes.",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 0,
            "start": 5.7,
            "end": 7.0,
            "transcript": "Thank you.",
            "confidence": 0.99,
            "words": [],
        },
    ]

    result = transcriber.smooth_speakers(utterances)

    assert result[1]["speaker"] == 1, "Short 'Yes.' must stay with the witness"


def test_merge_utterances_keeps_short_witness_response_separate():
    """End-to-end: a real Speaker 0 → Speaker 1 'Yes.' → Speaker 0 pattern
    (with all gaps under MERGE_GAP_THRESHOLD_SECONDS) survives the merge
    intact. Before the SHORT_ANSWER_WHITELIST + tighter glitch threshold,
    'Yes.' was reassigned to Speaker 0 and absorbed into the surrounding
    attorney block."""
    utterances = [
        {
            "speaker": 0,
            "start": 0.0,
            "end": 5.0,
            "transcript": "Do you solemnly swear to tell the truth?",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 1,
            "start": 5.2,
            "end": 5.45,
            "transcript": "Yes.",
            "confidence": 0.99,
            "words": [],
        },
        {
            "speaker": 0,
            "start": 5.7,
            "end": 7.0,
            "transcript": "Thank you, sir.",
            "confidence": 0.99,
            "words": [],
        },
    ]

    smoothed = transcriber.smooth_speakers(utterances)
    result = transcriber.merge_utterances(smoothed)

    assert len(result) == 3
    assert [u["speaker"] for u in result] == [0, 1, 0]
    assert result[1]["transcript"] == "Yes."


def test_transcribe_chunk_rejects_empty_merged_output(monkeypatch, tmp_path):
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
    monkeypatch.setattr(transcriber, "merge_utterances", lambda *args, **kwargs: [])

    with pytest.raises(RuntimeError, match="No utterances returned"):
        transcriber.transcribe_chunk(str(audio_path))


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
