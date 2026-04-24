"""
Smoke test for core/correction_runner.py.

Does NOT make network calls. Tests only pure-Python logic.
"""
import json
import logging
import os
import tempfile
import pytest


def _make_fake_deepgram_json():
    return {
        "utterances": [
            {
                "speaker": 2,
                "start": 0.0,
                "end": 3.5,
                "transcript": "Did you review the document.",
                "words": [],
                "confidence": 0.97,
            },
            {
                "speaker": 1,
                "start": 4.0,
                "end": 5.1,
                "transcript": "Yes sir.",
                "words": [],
                "confidence": 0.95,
            },
            {
                "speaker": 2,
                "start": 5.5,
                "end": 8.2,
                "transcript": "Infection.",
                "words": [],
                "confidence": 0.88,
            },
        ]
    }


def test_correction_runner_produces_corrected_file(monkeypatch):
    """End-to-end: fake Deepgram JSON → corrected transcript written to disk."""
    from core.correction_runner import run_correction_job

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "test_transcript.txt")
        json_path = os.path.join(tmpdir, "test_transcript.json")

        dg_json = _make_fake_deepgram_json()
        payload = {"utterances": dg_json["utterances"]}
        with open(json_path, "w") as f:
            json.dump(payload, f)
        monkeypatch.setattr(
            "core.correction_runner._load_job_config_for_transcript",
            lambda _path: {
                "ufm_fields": {
                    "speaker_map": {"1": "THE WITNESS", "2": "MR. SMITH"},
                    "speaker_map_verified": True,
                },
                "confirmed_spellings": {},
            },
        )

        with open(txt_path, "w") as f:
            f.write("Speaker 2: Did you review the document.\n\n"
                    "Speaker 1: Yes sir.\n\n"
                    "Speaker 2: Infection.")

        results = []
        run_correction_job(
            transcript_path=txt_path,
            progress_callback=None,
            done_callback=lambda r: results.append(r),
        )

        assert results, "done_callback was never called"
        result = results[0]
        assert result["success"] is True, f"Correction failed: {result.get('error')}"
        assert result["correction_count"] >= 0

        corrected_path = result["corrected_path"]
        assert corrected_path and os.path.isfile(corrected_path), \
            "Corrected file was not written"

        corrected_text = open(corrected_path).read()
        assert "Objection" in corrected_text or len(corrected_text) > 0


def test_correction_runner_rejects_missing_json(monkeypatch):
    """When no Deepgram JSON exists, runner must fail instead of parsing raw text."""
    from core.correction_runner import run_correction_job

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "no_json_here.txt")
        with open(txt_path, "w") as f:
            f.write("Speaker 0: Okay I think Infection.")
        monkeypatch.setattr(
            "core.correction_runner._load_job_config_for_transcript",
            lambda _path: {
                "ufm_fields": {
                    "speaker_map": {"0": "THE REPORTER"},
                    "speaker_map_verified": True,
                },
                "confirmed_spellings": {},
            },
        )

        results = []
        run_correction_job(
            transcript_path=txt_path,
            done_callback=lambda r: results.append(r),
        )
        assert results[0]["success"] is False
        assert "Deepgram JSON not found" in results[0]["error"]


def test_format_blocks_to_text_delegates_to_emit_blocks(monkeypatch):
    from core.correction_runner import format_blocks_to_text

    captured = {}

    def _fake_emit_blocks(blocks):
        captured["blocks"] = blocks
        return "PROCESSED BLOCK OUTPUT"

    monkeypatch.setattr("spec_engine.emitter.emit_blocks", _fake_emit_blocks)

    sample_blocks = [{"text": "sample"}]
    result = format_blocks_to_text(sample_blocks)

    assert result == "PROCESSED BLOCK OUTPUT"
    assert captured["blocks"] == sample_blocks


def test_build_job_config_maps_court_type_to_job_config_court_type():
    from core.correction_runner import _build_job_config_from_ufm

    cfg = _build_job_config_from_ufm(
        {
            "ufm_fields": {
                "court_type": "County Court at Law",
            },
            "confirmed_spellings": {},
        }
    )

    assert cfg.court_type == "County Court at Law"


def test_build_job_config_ignores_malformed_speaker_map_keys(caplog):
    from core.correction_runner import _build_job_config_from_ufm

    cfg = _build_job_config_from_ufm(
        {
            "ufm_fields": {
                "speaker_map": {
                    "1": "THE WITNESS",
                    "bad": "MR. SMITH",
                    "2": "THE REPORTER",
                },
            },
            "confirmed_spellings": {},
        }
    )

    assert cfg.speaker_map == {1: "THE WITNESS", 2: "THE REPORTER"}
    assert "Ignoring non-integer speaker_map key" in caplog.text


def test_build_job_config_populates_ai_proper_nouns_from_saved_context():
    from core.correction_runner import _build_job_config_from_ufm

    cfg = _build_job_config_from_ufm(
        {
            "ufm_fields": {
                "cause_number": "C-226025-G",
                "witness_name": "Nadia Yvonne Trevino",
                "reporter_name": "Miah Bardot",
                "plaintiff_name": "Nadia Yvonne Trevino",
                "defendant_name": "Tabitha Marie Ortiz",
                "plaintiff_counsel": [{"name": "Ed Siconi", "firm": "Reyna Law"}],
                "defense_counsel": [{"name": "Sutton Davis", "firm": "Defense Firm"}],
            },
            "confirmed_spellings": {"Ivonne": "Yvonne"},
            "deepgram_keyterms": ["Jobstown Pizza and Grill", "Brownsville"],
        }
    )

    assert hasattr(cfg, "all_proper_nouns")
    assert "Jobstown Pizza and Grill" in cfg.all_proper_nouns
    assert "Brownsville" in cfg.all_proper_nouns
    assert "Yvonne" in cfg.all_proper_nouns
    assert "Nadia Yvonne Trevino" in cfg.all_proper_nouns
    assert "Miah Bardot" in cfg.all_proper_nouns
    assert "Sutton Davis" in cfg.all_proper_nouns
    assert "Ed Siconi" in cfg.all_proper_nouns


def test_build_job_config_deduplicates_ai_proper_nouns():
    from core.correction_runner import _build_job_config_from_ufm

    cfg = _build_job_config_from_ufm(
        {
            "ufm_fields": {
                "witness_name": "Nadia Yvonne Trevino",
            },
            "confirmed_spellings": {"Nadia Ivonne": "Nadia Yvonne Trevino"},
            "deepgram_keyterms": ["Nadia Yvonne Trevino", "Nadia Yvonne Trevino"],
        }
    )

    assert cfg.all_proper_nouns.count("Nadia Yvonne Trevino") == 1


def test_run_correction_job_returns_processed_text_not_raw_text(monkeypatch):
    from core.correction_runner import run_correction_job
    from spec_engine.models import Block

    processed_blocks = [Block(speaker_id=1, text="Processed answer.", raw_text="")]

    monkeypatch.setattr(
        "spec_engine.block_builder.build_blocks_from_deepgram",
        lambda deepgram_data: [Block(speaker_id=1, text="RAW INPUT SHOULD NOT BE RETURNED", raw_text="RAW INPUT SHOULD NOT BE RETURNED")],
    )
    monkeypatch.setattr(
        "spec_engine.processor.process_blocks",
        lambda blocks, job_config, run_logger=None: processed_blocks,
    )
    monkeypatch.setattr(
        "core.correction_runner._load_job_config_for_transcript",
        lambda _path: {"ufm_fields": {"speaker_map_verified": True}, "confirmed_spellings": {}},
    )
    monkeypatch.setattr(
        "core.correction_runner.format_blocks_to_text",
        lambda blocks: "PROCESSED OUTPUT ONLY",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "source.txt")
        json_path = os.path.join(tmpdir, "source.json")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("RAW INPUT SHOULD NOT BE RETURNED")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"utterances": [{"speaker": 1, "transcript": "RAW INPUT SHOULD NOT BE RETURNED", "words": []}]}, f)

        results = []
        run_correction_job(
            transcript_path=txt_path,
            done_callback=lambda r: results.append(r),
        )

        assert results, "done_callback was never called"
        result = results[0]
        assert result["success"] is True
        assert result["corrected_text"] == "PROCESSED OUTPUT ONLY"
        assert result["corrected_text"] != "RAW INPUT SHOULD NOT BE RETURNED"

        corrected_path = result["corrected_path"]
        assert corrected_path and os.path.isfile(corrected_path)
        with open(corrected_path, "r", encoding="utf-8") as f:
            assert f.read() == "PROCESSED OUTPUT ONLY"


def test_run_correction_job_passes_run_logger_to_process_blocks(monkeypatch):
    from core.correction_runner import run_correction_job
    from spec_engine.models import Block

    captured = {}

    monkeypatch.setattr(
        "spec_engine.block_builder.build_blocks_from_deepgram",
        lambda deepgram_data: [Block(speaker_id=1, text="RAW INPUT", raw_text="RAW INPUT")],
    )
    monkeypatch.setattr(
        "core.correction_runner._load_job_config_for_transcript",
        lambda _path: {
            "ufm_fields": {
                "speaker_map": {"1": "THE WITNESS"},
                "speaker_map_verified": True,
            },
            "confirmed_spellings": {},
        },
    )

    def _process(blocks, job_config, run_logger=None):
        captured["run_logger"] = run_logger
        return blocks

    monkeypatch.setattr("spec_engine.processor.process_blocks", _process)

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "source.txt")
        json_path = os.path.join(tmpdir, "source.json")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("RAW INPUT")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"utterances": [{"speaker": 1, "transcript": "RAW INPUT", "words": []}]}, f)

        results = []
        run_correction_job(txt_path, done_callback=lambda r: results.append(r))

        assert results[0]["success"] is True
        assert captured["run_logger"] is not None


def test_run_correction_job_allows_unverified_speaker_map_in_draft_mode(monkeypatch):
    from core.correction_runner import run_correction_job
    from spec_engine.models import Block

    monkeypatch.setattr(
        "spec_engine.block_builder.build_blocks_from_deepgram",
        lambda deepgram_data: [Block(speaker_id=1, text="RAW INPUT", raw_text="RAW INPUT")],
    )
    monkeypatch.setattr(
        "core.correction_runner._load_job_config_for_transcript",
        lambda _path: {"ufm_fields": {"speaker_map_verified": False}, "confirmed_spellings": {}},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "source.txt")
        json_path = os.path.join(tmpdir, "source.json")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("RAW INPUT")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"utterances": [{"speaker": 1, "transcript": "RAW INPUT", "words": []}]}, f)

        results = []
        run_correction_job(txt_path, done_callback=lambda r: results.append(r))

        assert results[0]["success"] is True
        assert results[0]["draft_mode"] is True


def test_run_correction_job_logs_module_path(monkeypatch, caplog):
    from core.correction_runner import run_correction_job

    caplog.set_level(logging.INFO)

    monkeypatch.setattr(
        "core.correction_runner._load_job_config_for_transcript",
        lambda _path: {"ufm_fields": {"speaker_map_verified": False}, "confirmed_spellings": {}},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "source.txt")
        json_path = os.path.join(tmpdir, "source.json")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("RAW INPUT")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"utterances": [{"speaker": 1, "transcript": "RAW INPUT", "words": []}]}, f)

        results = []
        run_correction_job(txt_path, done_callback=lambda r: results.append(r))

        assert results[0]["success"] is True
        assert "Using correction runner module:" in caplog.text


def test_run_correction_job_rejects_json_without_utterances(monkeypatch):
    from core.correction_runner import run_correction_job

    monkeypatch.setattr(
        "core.correction_runner._load_job_config_for_transcript",
        lambda _path: {"ufm_fields": {"speaker_map_verified": True}, "confirmed_spellings": {}},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "source.txt")
        json_path = os.path.join(tmpdir, "source.json")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("RAW INPUT")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"transcript": "missing utterances"}, f)

        results = []
        run_correction_job(txt_path, done_callback=lambda r: results.append(r))

        assert results[0]["success"] is False
        assert "missing 'utterances'" in results[0]["error"]


def test_run_correction_job_rejects_empty_block_stream(monkeypatch):
    from core.correction_runner import run_correction_job

    monkeypatch.setattr("spec_engine.block_builder.build_blocks_from_deepgram", lambda deepgram_data: [])
    monkeypatch.setattr(
        "core.correction_runner._load_job_config_for_transcript",
        lambda _path: {"ufm_fields": {"speaker_map_verified": True}, "confirmed_spellings": {}},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "source.txt")
        json_path = os.path.join(tmpdir, "source.json")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("RAW INPUT")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"utterances": [{"speaker": 1, "transcript": "RAW INPUT", "words": []}]}, f)

        results = []
        run_correction_job(txt_path, done_callback=lambda r: results.append(r))

        assert results[0]["success"] is False
        assert "No transcript blocks could be generated." in results[0]["error"]


def test_run_correction_job_handles_start_pipeline_session_failure(monkeypatch):
    from core.correction_runner import run_correction_job

    monkeypatch.setattr(
        "app_logging.start_pipeline_session",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("session start failed")),
    )

    results = []
    run_correction_job("C:\\fake\\transcript.txt", done_callback=lambda r: results.append(r))

    assert results[0]["success"] is False
    assert "session start failed" in results[0]["error"]
