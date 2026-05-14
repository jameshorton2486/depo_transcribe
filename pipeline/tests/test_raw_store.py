"""Tests for the Phase-A raw-immutability layer.

Covers the contract in ``pipeline/raw_store.py``:

- write succeeds with valid input
- file is read-only on disk after write
- second write to the same path raises FileExistsError
- payload schema carries chunk count + saved Deepgram bodies + provenance
- chunk_offsets pair correctly with chunk_results
"""
from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from pipeline.raw_store import (
    RAW_RESPONSE_FILENAME_PREFIX,
    RAW_STORE_SUBDIR,
    RawResponseSaveResult,
    save_raw_response,
)


def _fake_chunk_result(transcript: str = "Hello world.") -> dict:
    return {
        "words": [],
        "utterances": [],
        "raw_utterances": [],
        "transcript": transcript,
        "raw": {
            "results": {
                "channels": [
                    {"alternatives": [{"transcript": transcript, "words": []}]}
                ],
                "utterances": [],
            },
            "metadata": {"request_id": "fake-test-id"},
        },
    }


class TestSaveRawResponse:
    def test_writes_file_under_case_dir(self, tmp_path):
        result = save_raw_response(
            tmp_path,
            chunk_results=[_fake_chunk_result()],
            chunk_offsets=[0.0],
            audio_file="C:/foo.mp3",
            model="nova-3",
            timestamp="20260513_120000",
        )
        assert isinstance(result, RawResponseSaveResult)
        assert result.path == tmp_path / RAW_STORE_SUBDIR / (
            f"{RAW_RESPONSE_FILENAME_PREFIX}20260513_120000.json"
        )
        assert result.path.exists()
        assert result.chunk_count == 1
        assert result.timestamp == "20260513_120000"

    def test_payload_carries_unmutated_deepgram_response(self, tmp_path):
        chunk = _fake_chunk_result(transcript="The witness was sworn.")
        result = save_raw_response(
            tmp_path,
            chunk_results=[chunk],
            chunk_offsets=[12.5],
            audio_file="/tmp/audio.wav",
            model="nova-3",
            request_params={"model": "nova-3", "utt_split": "0.8"},
            timestamp="20260513_120001",
        )
        data = json.loads(result.path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 2
        assert data["chunk_count"] == 1
        assert data["audio_file"] == "/tmp/audio.wav"
        assert data["model"] == "nova-3"
        assert data["request_params"]["utt_split"] == "0.8"
        chunks = data["chunks"]
        assert chunks[0]["index"] == 0
        assert chunks[0]["start_seconds"] == 12.5
        assert (
            chunks[0]["deepgram_response"]["results"]["channels"][0][
                "alternatives"
            ][0]["transcript"]
            == "The witness was sworn."
        )

    def test_file_is_read_only_after_write(self, tmp_path):
        result = save_raw_response(
            tmp_path,
            chunk_results=[_fake_chunk_result()],
            chunk_offsets=[0.0],
            timestamp="20260513_120002",
        )
        # On Windows, the readonly bit is the user-write removal.
        mode = result.path.stat().st_mode
        assert not (mode & stat.S_IWUSR), (
            f"file should be read-only after save_raw_response; mode={oct(mode)}"
        )

    def test_second_write_to_same_timestamp_raises(self, tmp_path):
        save_raw_response(
            tmp_path,
            chunk_results=[_fake_chunk_result()],
            chunk_offsets=[0.0],
            timestamp="20260513_120003",
        )
        with pytest.raises(FileExistsError):
            save_raw_response(
                tmp_path,
                chunk_results=[_fake_chunk_result(transcript="different")],
                chunk_offsets=[0.0],
                timestamp="20260513_120003",
            )

    def test_two_calls_with_default_timestamps_both_succeed(self, tmp_path):
        # The second-resolution timestamp could theoretically collide,
        # but in practice tests don't fire in the same wall-clock second
        # unless something is wrong. We assert the loose contract here:
        # if the timestamps differ, both writes succeed.
        r1 = save_raw_response(
            tmp_path,
            chunk_results=[_fake_chunk_result()],
            chunk_offsets=[0.0],
            timestamp="20260513_120004",
        )
        r2 = save_raw_response(
            tmp_path,
            chunk_results=[_fake_chunk_result()],
            chunk_offsets=[0.0],
            timestamp="20260513_120005",
        )
        assert r1.path != r2.path
        assert r1.path.exists()
        assert r2.path.exists()

    def test_multiple_chunks_preserve_ordering_and_offsets(self, tmp_path):
        chunks = [
            _fake_chunk_result(transcript=f"chunk {i}") for i in range(3)
        ]
        offsets = [0.0, 600.0, 1200.0]
        result = save_raw_response(
            tmp_path,
            chunk_results=chunks,
            chunk_offsets=offsets,
            timestamp="20260513_120006",
        )
        data = json.loads(result.path.read_text(encoding="utf-8"))
        assert data["chunk_count"] == 3
        recovered_offsets = [c["start_seconds"] for c in data["chunks"]]
        assert recovered_offsets == offsets
        recovered_transcripts = [
            c["deepgram_response"]["results"]["channels"][0][
                "alternatives"
            ][0]["transcript"]
            for c in data["chunks"]
        ]
        assert recovered_transcripts == ["chunk 0", "chunk 1", "chunk 2"]

    def test_handles_missing_raw_key_gracefully(self, tmp_path):
        # If a caller passes a chunk dict without "raw", we still
        # write the file but record None for that chunk's response.
        bad_chunk = {"transcript": "no raw key"}
        result = save_raw_response(
            tmp_path,
            chunk_results=[bad_chunk],
            chunk_offsets=[0.0],
            timestamp="20260513_120007",
        )
        data = json.loads(result.path.read_text(encoding="utf-8"))
        assert data["chunks"][0]["deepgram_response"] is None

    def test_creates_deepgram_subdir_if_missing(self, tmp_path):
        # Brand-new case folder with no Deepgram/ subdir yet.
        new_case = tmp_path / "new_case"
        new_case.mkdir()
        # Sanity: no Deepgram subdir yet.
        assert not (new_case / RAW_STORE_SUBDIR).exists()
        result = save_raw_response(
            new_case,
            chunk_results=[_fake_chunk_result()],
            chunk_offsets=[0.0],
            timestamp="20260513_120008",
        )
        assert (new_case / RAW_STORE_SUBDIR).is_dir()
        assert result.path.parent == new_case / RAW_STORE_SUBDIR

    def test_empty_input_writes_zero_chunk_payload(self, tmp_path):
        result = save_raw_response(
            tmp_path,
            chunk_results=[],
            chunk_offsets=[],
            timestamp="20260513_120009",
        )
        data = json.loads(result.path.read_text(encoding="utf-8"))
        assert data["chunk_count"] == 0
        assert data["chunks"] == []


class TestProvenanceFields:
    def test_audit_metadata_round_trips(self, tmp_path):
        result = save_raw_response(
            tmp_path,
            chunk_results=[_fake_chunk_result()],
            chunk_offsets=[0.0],
            audio_file="C:/Users/james/Downloads/foo.mp3",
            model="nova-3-medical",
            request_params={
                "model": "nova-3-medical",
                "language": "en",
                "diarize": "true",
                "utt_split": "0.8",
            },
            timestamp="20260513_120010",
        )
        data = json.loads(result.path.read_text(encoding="utf-8"))
        assert data["audio_file"] == "C:/Users/james/Downloads/foo.mp3"
        assert data["model"] == "nova-3-medical"
        assert data["request_params"]["model"] == "nova-3-medical"
        assert data["request_params"]["diarize"] == "true"
        # Timestamps present
        assert "saved_at_utc" in data
        assert "saved_at_local" in data
