"""Tests for ``core.corrections_runner``."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from core import corrections_runner


def _write_minimal_raw_json(path: Path) -> None:
    """Write a minimal ``{base}_raw.json`` with two diarized utterances."""
    data = {
        "audio_file": "fake.wav",
        "model": "nova-3",
        "audio_quality": "ENHANCED",
        "audio_tier": "ENHANCED",
        "created_at": "2026-05-07T00:00:00",
        "chunk_count": 1,
        "deepgram_keyterms_used": [],
        "transcript": "",
        "chunk_summaries": [],
        "utterances": [
            {
                "speaker": 0,
                "text": "What is your name?",
                "start": 0.0,
                "end": 1.0,
            },
            {
                "speaker": 1,
                "text": "My name is Coger.",
                "start": 1.0,
                "end": 2.0,
            },
        ],
        "raw_utterances": [],
        "words": [],
        "chunks": [],
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_job_config(
    path: Path,
    *,
    confirmed_spellings: dict | None = None,
    keyterms: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "ufm_fields": {},
        "confirmed_spellings": confirmed_spellings or {},
        "deepgram_keyterms": keyterms or [],
    }
    path.write_text(json.dumps(config), encoding="utf-8")


def _make_case(tmp_path: Path) -> tuple[Path, Path]:
    """Return (raw_path, job_config_path) for a freshly built case folder."""
    case = tmp_path / "case"
    deepgram_dir = case / "Deepgram"
    deepgram_dir.mkdir(parents=True)
    raw_path = deepgram_dir / "depo_raw.json"
    _write_minimal_raw_json(raw_path)
    job_config_path = case / "source_docs" / "job_config.json"
    return raw_path, job_config_path


def test_run_corrections_writes_corrected_txt(tmp_path: Path) -> None:
    raw_path, job_config_path = _make_case(tmp_path)
    _write_job_config(job_config_path, confirmed_spellings={"Koger": "Coger"})

    result_path = corrections_runner.run_corrections(raw_path)

    assert result_path == raw_path.parent / "depo_corrected.txt"
    assert result_path.exists()
    text = result_path.read_text(encoding="utf-8")
    assert text.startswith("# Corrected from depo_raw.json on ")
    # Provenance header is followed by actual content.
    assert len(text.splitlines()) >= 2


def test_run_corrections_missing_job_config(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    raw_path, _ = _make_case(tmp_path)
    # Intentionally do NOT create source_docs/job_config.json.

    with caplog.at_level("WARNING"):
        result_path = corrections_runner.run_corrections(raw_path)

    assert result_path.exists()
    assert any(
        "job_config.json not found" in rec.message for rec in caplog.records
    )


def test_run_corrections_overwrites_on_rerun(tmp_path: Path) -> None:
    raw_path, job_config_path = _make_case(tmp_path)
    _write_job_config(job_config_path)

    first = corrections_runner.run_corrections(raw_path)
    first_mtime = first.stat().st_mtime

    time.sleep(0.05)
    second = corrections_runner.run_corrections(raw_path)

    assert second == first
    assert second.stat().st_mtime >= first_mtime


def test_run_corrections_raises_on_missing_raw(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        corrections_runner.run_corrections(tmp_path / "missing_raw.json")


def test_run_corrections_raises_on_wrong_suffix(tmp_path: Path) -> None:
    bogus = tmp_path / "depo.json"
    bogus.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="_raw.json"):
        corrections_runner.run_corrections(bogus)


def test_run_corrections_raises_on_no_utterances(tmp_path: Path) -> None:
    case = tmp_path / "case"
    deepgram_dir = case / "Deepgram"
    deepgram_dir.mkdir(parents=True)
    raw_path = deepgram_dir / "depo_raw.json"
    raw_path.write_text(json.dumps({"utterances": []}), encoding="utf-8")
    _write_job_config(case / "source_docs" / "job_config.json")

    with pytest.raises(RuntimeError, match="no utterances"):
        corrections_runner.run_corrections(raw_path)


def test_run_corrections_ignores_malformed_job_config(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    raw_path, job_config_path = _make_case(tmp_path)
    job_config_path.parent.mkdir(parents=True, exist_ok=True)
    job_config_path.write_text("{ this is not json", encoding="utf-8")

    with caplog.at_level("WARNING"):
        result_path = corrections_runner.run_corrections(raw_path)

    assert result_path.exists()
    assert any("Could not parse" in rec.message for rec in caplog.records)


def test_run_corrections_falls_back_to_keyterms_key(tmp_path: Path) -> None:
    """If ``deepgram_keyterms`` is absent, runner reads ``keyterms``."""
    raw_path, job_config_path = _make_case(tmp_path)
    job_config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "ufm_fields": {},
        "confirmed_spellings": {},
        # Note: deepgram_keyterms intentionally absent.
        "keyterms": ["Coger", "Maloney"],
    }
    job_config_path.write_text(json.dumps(config), encoding="utf-8")

    # Should run without raising and produce a corrected file.
    result_path = corrections_runner.run_corrections(raw_path)
    assert result_path.exists()


def test_run_corrections_handles_production_utterance_shape(tmp_path: Path) -> None:
    """Real saved utterances (per ``core/job_runner.py``) carry the
    Deepgram-canonical ``transcript`` and ``speaker_label`` keys, not
    ``text`` and a bare numeric ``speaker``. The runner must adapt this
    shape so ``build_blocks`` produces non-empty output.

    This test caught the first real-world failure: 1164 utterances ->
    0 blocks because ``block_builder`` was reading ``text`` from a dict
    that only had ``transcript``. The fix lives in
    ``_adapt_saved_utterances`` inside the runner.
    """
    case = tmp_path / "case"
    deepgram_dir = case / "Deepgram"
    deepgram_dir.mkdir(parents=True)
    raw_path = deepgram_dir / "depo_raw.json"

    # Production-shape utterances: 'transcript' (not 'text'),
    # 'speaker_label' (not just numeric speaker).
    data = {
        "utterances": [
            {
                "speaker": 0,
                "speaker_label": "Speaker 0",
                "transcript": "What is your name?",
                "start": 0.0,
                "end": 1.0,
                "confidence": 0.99,
                "words": [],
            },
            {
                "speaker": 1,
                "speaker_label": "Speaker 1",
                "transcript": "My name is Coger.",
                "start": 1.0,
                "end": 2.0,
                "confidence": 0.97,
                "words": [],
            },
        ],
    }
    raw_path.write_text(json.dumps(data), encoding="utf-8")
    _write_job_config(case / "source_docs" / "job_config.json")

    result_path = corrections_runner.run_corrections(raw_path)

    text = result_path.read_text(encoding="utf-8")
    # Provenance header
    assert text.startswith("# Corrected from depo_raw.json on ")
    # Body must have non-trivial content — proves blocks were built.
    body = "\n".join(text.splitlines()[1:])
    assert body.strip(), f"corrected body is empty: {text!r}"


def test_adapt_saved_utterances_handles_mixed_shapes() -> None:
    """Direct unit test of the shape adapter, covering the variants we
    expect on the wire."""
    inputs = [
        # Production shape: transcript + speaker_label
        {"speaker": 0, "speaker_label": "Speaker 0", "transcript": "Real."},
        # Older shape: text + numeric speaker (pre-assembler)
        {"speaker": 1, "text": "Older."},
        # Numeric speaker only, no label — should construct "Speaker N"
        {"speaker": 2, "transcript": "No label."},
        # Empty transcript — must be skipped
        {"speaker": 3, "speaker_label": "Speaker 3", "transcript": ""},
        # Whitespace-only transcript — must be skipped
        {"speaker": 4, "speaker_label": "Speaker 4", "transcript": "   "},
        # Non-dict garbage — must be skipped
        "not-a-dict",
        None,
    ]
    out = corrections_runner._adapt_saved_utterances(inputs)  # type: ignore[arg-type]
    assert len(out) == 3
    assert out[0] == {"speaker": "Speaker 0", "text": "Real.", "type": "utterance"}
    assert out[1] == {"speaker": "Speaker 1", "text": "Older.", "type": "utterance"}
    assert out[2] == {"speaker": "Speaker 2", "text": "No label.", "type": "utterance"}


# ── Step 2E: split-utterances source selection ────────────────────────────────


class TestUtteranceSourceSelection:
    """Step 2E: corrections runner must prefer split_utterances when
    present, fall back to utterances otherwise, and raise on malformed
    split_utterances rather than silently falling back."""

    def test_split_utterances_preferred_when_present(self):
        from core.corrections_runner import _select_utterance_source

        data = {
            "utterances": [
                {"transcript": "original A"},
                {"transcript": "original B"},
            ],
            "split_utterances": [
                {"transcript": "split A1"},
                {"transcript": "split A2"},
                {"transcript": "split B"},
            ],
        }
        utts, source = _select_utterance_source(data)
        assert source == "split_utterances"
        assert len(utts) == 3
        assert utts[0]["transcript"] == "split A1"

    def test_falls_back_to_utterances_when_split_absent(self):
        from core.corrections_runner import _select_utterance_source

        data = {"utterances": [{"transcript": "original only"}]}
        utts, source = _select_utterance_source(data)
        assert source == "utterances"
        assert utts == [{"transcript": "original only"}]

    def test_raises_when_split_utterances_is_empty_list(self):
        from core.corrections_runner import _select_utterance_source

        data = {
            "utterances": [{"transcript": "original"}],
            "split_utterances": [],
        }
        with pytest.raises(RuntimeError, match="malformed"):
            _select_utterance_source(data)

    def test_raises_when_split_utterances_is_wrong_type(self):
        from core.corrections_runner import _select_utterance_source

        data = {
            "utterances": [{"transcript": "original"}],
            "split_utterances": "not a list",
        }
        with pytest.raises(RuntimeError, match="expected a list"):
            _select_utterance_source(data)

    def test_raises_when_split_utterance_item_missing_text(self):
        from core.corrections_runner import _select_utterance_source

        data = {
            "utterances": [{"transcript": "original"}],
            "split_utterances": [
                {"transcript": "valid item"},
                {"speaker": 1},  # missing both transcript and text
            ],
        }
        with pytest.raises(RuntimeError, match="neither 'transcript' nor 'text'"):
            _select_utterance_source(data)
