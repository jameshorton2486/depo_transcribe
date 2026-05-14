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
    monkeypatch.setattr(
        transcriber,
        "merge_utterances",
        lambda utterances, gap_threshold_seconds, min_word_count: utterances,
    )

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
    monkeypatch.setattr(
        transcriber,
        "merge_utterances",
        lambda utterances, gap_threshold_seconds, min_word_count: utterances,
    )

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
    monkeypatch.setattr(
        transcriber,
        "merge_utterances",
        lambda utterances, gap_threshold_seconds, min_word_count: utterances,
    )

    transcriber.transcribe_chunk(
        str(audio_path), keyterms=["Matthew Coger", "Murphy Oil"]
    )

    params = parse_qs(urlparse(captured["url"]).query)

    assert params["keyterm"] == ["Matthew Coger", "Murphy Oil"]


def test_validate_deepgram_params_rejects_uppercase_boolean_strings():
    try:
        transcriber.validate_deepgram_params({"diarize": "True"})
    except ValueError as exc:
        assert "lowercase 'true'/'false'" in str(exc)
    else:
        raise AssertionError(
            "Expected validate_deepgram_params to reject uppercase boolean strings"
        )


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


def test_enforce_required_deepgram_flags_includes_filler_words_for_verbatim_compliance():
    """Defect #12: filler_words must be structurally enforced as 'true'
    to guarantee UFM §3.7/§3.8 verbatim legal compliance.

    The prior implementation set filler_words=True in the per-request
    params dict but did not include it in REQUIRED_DEEPGRAM_FLAGS.
    This left verbatim compliance dependent on the per-request dict
    rather than the enforcement layer. A future caller that passed
    filler_words=False would have silently violated UFM compliance.
    """
    from pipeline.transcriber import (
        REQUIRED_DEEPGRAM_FLAGS,
        enforce_required_deepgram_flags,
    )

    # The constant itself must contain the verbatim guarantee.
    assert REQUIRED_DEEPGRAM_FLAGS.get("filler_words") == "true"

    # A caller attempting to disable filler_words must be overridden.
    caller_params = {"filler_words": "false", "model": "nova-3"}
    enforced = enforce_required_deepgram_flags(caller_params)
    assert enforced["filler_words"] == "true"

    # A caller omitting filler_words entirely must still get it.
    caller_params_no_filler = {"model": "nova-3"}
    enforced_no_filler = enforce_required_deepgram_flags(caller_params_no_filler)
    assert enforced_no_filler["filler_words"] == "true"


def test_transcribe_chunk_logs_params_and_utterance_count(
    monkeypatch, tmp_path, capsys
):
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


def test_transcribe_chunk_processes_near_silent_chunks_in_safe_mode(
    monkeypatch, tmp_path
):
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

    with pytest.raises(
        RuntimeError, match="no utterances; transcription cannot proceed"
    ):
        transcriber.transcribe_chunk(str(audio_path))


# ── trim_keyterms_for_deepgram ──────────────────────────────────────────


def test_trim_keyterms_passes_short_list_unchanged():
    sent, stats = transcriber.trim_keyterms_for_deepgram(
        ["David Volk", "Bexar County", "Nathan Agu"]
    )
    assert sent == ["David Volk", "Bexar County", "Nathan Agu"]
    assert stats["sent"] == 3
    assert stats["dropped_oversize"] == 0
    assert stats["dropped_budget"] == 0
    assert stats["used_tokens"] > 0


def test_trim_keyterms_drops_entries_over_char_cap():
    junk = "x" * 200
    sent, stats = transcriber.trim_keyterms_for_deepgram(
        ["David Volk", junk, "Nathan Agu"]
    )
    assert junk not in sent
    assert sent == ["David Volk", "Nathan Agu"]
    assert stats["dropped_oversize"] == 1
    assert stats["oversize_examples"] == [junk]


def test_trim_keyterms_respects_token_budget(monkeypatch):
    # Force a tiny budget so the cap fires deterministically.
    monkeypatch.setattr("config.DEEPGRAM_MAX_KEYTERM_TOKENS", 5)
    # Each "abcd" is 4 chars  ~2 tokens (1 + 1 separator). Budget 5 fits 2.
    sent, stats = transcriber.trim_keyterms_for_deepgram(
        ["abcd", "efgh", "ijkl", "mnop"]
    )
    assert len(sent) < 4
    assert stats["dropped_budget"] == 4 - len(sent)
    assert stats["used_tokens"] <= 5


def test_trim_keyterms_handles_empty_and_whitespace():
    sent, stats = transcriber.trim_keyterms_for_deepgram([])
    assert sent == []
    assert stats["sent"] == 0

    sent2, stats2 = transcriber.trim_keyterms_for_deepgram(["", "  ", "real"])
    assert sent2 == ["real"]
    assert stats2["sent"] == 1


def test_trim_keyterms_drops_ocr_debris_single_word_allcaps():
    """Defect #13: single-word ALL-CAPS fragments from PDF title pages
    are dropped before reaching Deepgram.

    These fragments come from PDFs that have an ALL-CAPS heading like
    'UNITED STATES DISTRICT COURT WESTERN DISTRICT OF TEXAS'. Some
    extraction paths split this into individual word keyterms.
    """
    from pipeline.transcriber import trim_keyterms_for_deepgram

    keyterms = [
        "Heath Thomas",
        "UNITED", "STATES", "DISTRICT", "COURT", "WESTERN",
        "Steven A. Nunez",
        "DIVISION", "PLAINTIFF", "DEFENDANT",
    ]
    sent, stats = trim_keyterms_for_deepgram(keyterms)

    assert "Heath Thomas" in sent
    assert "Steven A. Nunez" in sent
    assert "UNITED" not in sent
    assert "STATES" not in sent
    assert "DISTRICT" not in sent
    assert "COURT" not in sent
    assert "WESTERN" not in sent
    assert "DIVISION" not in sent
    assert "PLAINTIFF" not in sent
    assert "DEFENDANT" not in sent
    assert stats["dropped_ocr_debris"] == 8


def test_trim_keyterms_preserves_short_acronyms_under_four_chars():
    """Defect #13: short acronyms like LLC, CSR, IBM, FBI are NOT
    OCR debris and must be preserved. The length floor of 4 chars
    protects them."""
    from pipeline.transcriber import trim_keyterms_for_deepgram

    keyterms = ["LLC", "CSR", "IBM", "FBI"]
    sent, stats = trim_keyterms_for_deepgram(keyterms)

    assert "LLC" in sent
    assert "CSR" in sent
    assert "IBM" in sent
    assert "FBI" in sent
    assert stats["dropped_ocr_debris"] == 0


def test_trim_keyterms_preserves_acronyms_with_periods():
    """Defect #13: acronyms with internal periods like 'P.C.' and
    'U.S.A.' are legitimate keyterms even though they're ALL-CAPS."""
    from pipeline.transcriber import trim_keyterms_for_deepgram

    keyterms = ["P.C.", "PLLC", "U.S.A.", "M.D."]
    sent, stats = trim_keyterms_for_deepgram(keyterms)

    assert "P.C." in sent
    assert "U.S.A." in sent
    assert "M.D." in sent
    # 'PLLC' is ALL-CAPS, 4 chars, no periods, no digits — would be
    # caught by the filter. This is acceptable: PLLC the entity name
    # would typically appear as part of a multi-word firm name like
    # 'Cukjati Law Firm, PLLC' which preserves it via the multi-word rule.
    assert stats["dropped_ocr_debris"] == 1
    assert "PLLC" in stats["ocr_debris_examples"]


def test_trim_keyterms_preserves_multi_word_allcaps_phrases():
    """Defect #13: multi-word ALL-CAPS phrases are legitimate and
    must be preserved. The single-token rule protects them."""
    from pipeline.transcriber import trim_keyterms_for_deepgram

    keyterms = [
        "UNITED STATES DISTRICT COURT",
        "WESTERN DISTRICT OF TEXAS",
        "BRAIN AND SPINE PERSONAL INJURY LAWYERS",
    ]
    sent, stats = trim_keyterms_for_deepgram(keyterms)

    assert "UNITED STATES DISTRICT COURT" in sent
    assert "WESTERN DISTRICT OF TEXAS" in sent
    assert "BRAIN AND SPINE PERSONAL INJURY LAWYERS" in sent
    assert stats["dropped_ocr_debris"] == 0


def test_trim_keyterms_preserves_tokens_with_digits():
    """Defect #13: tokens with digits (e.g., '25-cv--OLG') are
    case-identifier keyterms, not OCR debris."""
    from pipeline.transcriber import trim_keyterms_for_deepgram

    keyterms = ["25-cv--OLG", "2025-CVA-001596D2", "COVID19"]
    sent, stats = trim_keyterms_for_deepgram(keyterms)

    assert "25-cv--OLG" in sent
    assert "2025-CVA-001596D2" in sent
    assert "COVID19" in sent
    assert stats["dropped_ocr_debris"] == 0


def test_trim_keyterms_stats_include_ocr_debris_count():
    """Defect #13: the returned stats dict must include the new
    dropped_ocr_debris key and a sample of dropped examples."""
    from pipeline.transcriber import trim_keyterms_for_deepgram

    keyterms = ["Heath Thomas", "UNITED", "STATES", "DISTRICT", "COURT"]
    sent, stats = trim_keyterms_for_deepgram(keyterms)

    assert "dropped_ocr_debris" in stats
    assert "ocr_debris_examples" in stats
    assert stats["dropped_ocr_debris"] == 4
    assert len(stats["ocr_debris_examples"]) <= 5


def test_trim_keyterms_real_failure_log_reconstruction():
    """Defect #13: end-to-end regression test using the actual
    keyterm list that produced the Deepgram 400 error. The filter
    must drop the OCR debris while keeping all legitimate keyterms."""
    from pipeline.transcriber import trim_keyterms_for_deepgram

    keyterms = [
        # Legitimate (selected from failure log)
        "Heath Thomas", "Steven A. Nunez", "Cukjati Law Firm",
        "Brain and Spine Personal Injury Lawyers of San Antonio",
        "Karen M. Alvarado", "Tiffany Netcher", "P.C.",
        "San Antonio Division", "25-cv--OLG",
        # OCR debris (from failure log)
        "UNITED", "STATES", "DISTRICT", "COURT", "WESTERN", "ANTONIO",
        "DIVISION", "DELIA", "GARZA", "CIVIL", "ACTION", "HOME",
        "DEPOT", "SHAWN", "PLAINTIFF", "NOTICE", "INTENTION", "TAKE",
        "ORAL", "DEPOSITION", "HEATH", "THOMAS", "FURTHER", "GIVEN",
        "FIRM", "BRAIN", "SPINE", "PERSONAL", "INJURY", "LAWYERS",
        "STEVEN", "ATTORNEYS",
    ]
    sent, stats = trim_keyterms_for_deepgram(keyterms)

    # All 9 legitimate keyterms preserved
    for legit in ("Heath Thomas", "Steven A. Nunez", "Cukjati Law Firm",
                  "Brain and Spine Personal Injury Lawyers of San Antonio",
                  "Karen M. Alvarado", "Tiffany Netcher", "P.C.",
                  "San Antonio Division", "25-cv--OLG"):
        assert legit in sent, "Legitimate keyterm dropped: " + repr(legit)

    # All 32 debris fragments dropped
    assert stats["dropped_ocr_debris"] == 32
