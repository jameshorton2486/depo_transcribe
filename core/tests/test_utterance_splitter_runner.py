"""Tests for core.utterance_splitter_runner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core import utterance_splitter_runner


def _write_raw_json(path: Path, utterances: list[dict]) -> None:
    data = {
        "audio_file": "fake.wav",
        "model": "nova-3",
        "utterances": utterances,
        "raw_utterances": [],
        "words": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _utt(text: str, speaker: int = 0) -> dict:
    return {"speaker": speaker, "speaker_label": f"Speaker {speaker}", "transcript": text}


class TestRunner:
    def test_writes_split_file_next_to_input(self, tmp_path: Path) -> None:
        raw = tmp_path / "case" / "Deepgram" / "depo_raw.json"
        _write_raw_json(raw, [_utt("Yes.")])

        # No flagged utterances → AI never called → no client needed.
        # Patch split_utterances at the runner's import site.
        from spec_engine.utterance_splitter import SplitterMetadata
        with patch.object(
            utterance_splitter_runner,
            "split_utterances",
            return_value=([_utt("Yes.")], SplitterMetadata(
                original_count=1, split_count=1, model="claude-test"
            )),
        ):
            out_path = utterance_splitter_runner.run_splitter(raw)

        assert out_path == raw.parent / "depo_split_raw.json"
        assert out_path.exists()

        payload = json.loads(out_path.read_text(encoding="utf-8"))
        # Original preserved
        assert payload["utterances"] == [_utt("Yes.")]
        # New keys added
        assert "split_utterances" in payload
        assert "split_metadata" in payload
        assert payload["split_metadata"]["original_count"] == 1
        assert payload["split_metadata"]["model"] == "claude-test"
        assert "timestamp" in payload["split_metadata"]
        assert payload["split_metadata"]["source_raw"] == "depo_raw.json"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            utterance_splitter_runner.run_splitter(tmp_path / "nope_raw.json")

    def test_wrong_suffix_raises(self, tmp_path: Path) -> None:
        bogus = tmp_path / "depo.json"
        bogus.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="_raw.json"):
            utterance_splitter_runner.run_splitter(bogus)

    def test_no_utterances_raises(self, tmp_path: Path) -> None:
        raw = tmp_path / "case" / "Deepgram" / "depo_raw.json"
        raw.parent.mkdir(parents=True)
        raw.write_text(json.dumps({"utterances": []}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="no utterances"):
            utterance_splitter_runner.run_splitter(raw)
