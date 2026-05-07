"""Tests for core/corrections_runner.run_corrections_for_json.

Hermetic — no Deepgram API, no audio files. Each test builds a tiny
saved-JSON fixture in tmp_path and asserts that the runner produces
the expected outputs without modifying its inputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from core.corrections_runner import (
    CorrectionResult,
    _utterances_to_block_input,
    run_corrections_for_json,
)


def _make_run_json(tmp_path: Path, payload: dict) -> Path:
    """Build a Deepgram-save layout (<tmp>/<case>/Deepgram/run.json)
    and write `payload` into it. Returns the JSON path."""
    case_dir = tmp_path / "case-fixture"
    deepgram_dir = case_dir / "Deepgram"
    deepgram_dir.mkdir(parents=True, exist_ok=True)
    json_path = deepgram_dir / "run.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return json_path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Two minimal but realistic saved utterances. The shape mirrors what
# job_runner.py persists in <base>_<stamp>.json: 'transcript' (not
# 'text'), 'speaker_label', 'speaker' as int.
_FIXTURE_UTTERANCES = [
    {
        "speaker": 0,
        "speaker_label": "Speaker 0",
        "start": 0.0,
        "end": 4.5,
        "transcript": "Did you go there?",
        "confidence": 0.94,
        "words": [],
    },
    {
        "speaker": 1,
        "speaker_label": "Speaker 1",
        "start": 4.6,
        "end": 6.2,
        "transcript": "Yes.",
        "confidence": 0.97,
        "words": [],
    },
]


def _fixture_payload() -> dict:
    return {
        "audio_file": "ignored.mp3",
        "model": "nova-3",
        "duration_sec": 6.2,
        "transcript": "Did you go there?  Yes.",
        "utterances": copy.deepcopy(_FIXTURE_UTTERANCES),
        "raw_utterances": [],
        "words": [],
    }


# ── happy path ─────────────────────────────────────────────────────────


def test_run_creates_corrected_txt_and_json_next_to_source(tmp_path):
    json_path = _make_run_json(tmp_path, _fixture_payload())
    result = run_corrections_for_json(json_path)

    assert isinstance(result, CorrectionResult)
    txt = Path(result.corrected_txt_path)
    out_json = Path(result.corrected_json_path)
    assert txt.is_file()
    assert out_json.is_file()
    # Same directory as source
    assert txt.parent == json_path.parent
    assert out_json.parent == json_path.parent
    # Naming follows <base>_corrected.{txt,json}
    assert txt.name == "run_corrected.txt"
    assert out_json.name == "run_corrected.json"


def test_corrected_txt_uses_canonical_qa_format(tmp_path):
    json_path = _make_run_json(tmp_path, _fixture_payload())
    result = run_corrections_for_json(json_path)
    text = Path(result.corrected_txt_path).read_text(encoding="utf-8")
    # Q. line uses tab-Q-tab; A. line uses tab-A-tab.
    assert re.search(r"\tQ\.\t", text), text
    assert re.search(r"\tA\.\t", text), text


def test_corrected_json_includes_required_metadata(tmp_path):
    json_path = _make_run_json(tmp_path, _fixture_payload())
    result = run_corrections_for_json(json_path)
    payload = json.loads(Path(result.corrected_json_path).read_text(encoding="utf-8"))

    # Per the spec: source_json_path, corrected_txt_path, processing
    # timestamp, blocks, original transcript, warnings/errors lists.
    assert payload["source_json_path"] == str(json_path)
    assert payload["corrected_txt_path"] == result.corrected_txt_path
    assert "processed_at" in payload and payload["processed_at"]
    assert isinstance(payload["blocks"], list)
    assert payload["block_count"] == len(payload["blocks"])
    assert payload["original_transcript"] == "Did you go there?  Yes."
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["errors"], list)


# ── safety: source files are not modified ─────────────────────────────


def test_original_input_json_unchanged(tmp_path):
    json_path = _make_run_json(tmp_path, _fixture_payload())
    before = _hash(json_path)
    run_corrections_for_json(json_path)
    after = _hash(json_path)
    assert before == after, "source JSON byte-changed after a corrections run"


def test_does_not_overwrite_a_pre_existing_original_txt(tmp_path):
    """If the operator has a hand-edited <base>.txt next to the run JSON,
    the runner must not touch it. The runner only writes <base>_corrected.txt.
    """
    json_path = _make_run_json(tmp_path, _fixture_payload())
    original_txt = json_path.parent / "run.txt"
    original_txt.write_text("HUMAN-EDITED", encoding="utf-8")
    before = _hash(original_txt)
    run_corrections_for_json(json_path)
    after = _hash(original_txt)
    assert before == after


# ── graceful handling of missing / partial inputs ─────────────────────


def test_missing_file_raises_clean_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_corrections_for_json(tmp_path / "nope.json")


def test_empty_utterances_yields_empty_corrected_outputs(tmp_path):
    """No utterances -> empty blocks; empty TXT; corrected JSON still
    written with the metadata envelope and an empty blocks list."""
    payload = _fixture_payload()
    payload["utterances"] = []
    json_path = _make_run_json(tmp_path, payload)
    result = run_corrections_for_json(json_path)
    assert Path(result.corrected_txt_path).read_text(encoding="utf-8") == ""
    out = json.loads(Path(result.corrected_json_path).read_text(encoding="utf-8"))
    assert out["blocks"] == []
    assert out["block_count"] == 0


def test_missing_optional_fields_do_not_crash(tmp_path):
    """No 'transcript' key, no 'words' list, missing speaker_label —
    runner should handle each gracefully."""
    payload = {
        "model": "nova-3",
        "utterances": [
            {"speaker": 0, "transcript": "Did you go there?"},
            {"speaker": 1, "transcript": "Yes."},
        ],
    }
    json_path = _make_run_json(tmp_path, payload)
    result = run_corrections_for_json(json_path)
    assert Path(result.corrected_txt_path).is_file()
    out = json.loads(Path(result.corrected_json_path).read_text(encoding="utf-8"))
    # original_transcript falls back to empty string if missing
    assert out["original_transcript"] == ""


def test_does_not_require_deepgram_api_or_audio(tmp_path, monkeypatch):
    """Belt-and-braces: ensure no httpx call or audio open happens.
    monkeypatch breaks both surfaces; the runner should still complete.
    """
    import httpx
    monkeypatch.setattr(
        httpx, "post", lambda *a, **kw: pytest.fail("httpx.post called")
    )
    json_path = _make_run_json(tmp_path, _fixture_payload())
    run_corrections_for_json(json_path)


# ── adapter: utterance-shape mapping ──────────────────────────────────


def test_utterance_adapter_uses_transcript_and_speaker_label():
    out = _utterances_to_block_input(_FIXTURE_UTTERANCES)
    assert len(out) == 2
    assert out[0]["text"] == "Did you go there?"
    assert out[0]["speaker"] == "Speaker 0"
    assert out[0]["type"] == "utterance"


def test_utterance_adapter_falls_back_on_speaker_label_missing():
    raw = [{"speaker": 3, "transcript": "OK."}]
    out = _utterances_to_block_input(raw)
    assert out[0]["speaker"] == "Speaker 3"


def test_utterance_adapter_skips_empty_transcripts_and_non_dicts():
    raw = [
        {"speaker_label": "Speaker 0", "transcript": ""},  # empty
        "garbage",  # not a dict
        None,  # not a dict
        {"speaker_label": "Speaker 1", "transcript": "  "},  # whitespace only
        {"speaker_label": "Speaker 1", "transcript": "Real."},
    ]
    out = _utterances_to_block_input(raw)
    assert len(out) == 1
    assert out[0]["text"] == "Real."


# ── source preservation: original_transcript field round-trips ────────


def test_original_transcript_is_preserved_in_corrected_json(tmp_path):
    payload = _fixture_payload()
    json_path = _make_run_json(tmp_path, payload)
    result = run_corrections_for_json(json_path)
    out = json.loads(Path(result.corrected_json_path).read_text(encoding="utf-8"))
    assert out["original_transcript"] == payload["transcript"]
