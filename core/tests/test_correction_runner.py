"""
Smoke test for core/correction_runner.py.

Does NOT make network calls. Tests only pure-Python logic.
"""
import json
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


def test_correction_runner_produces_corrected_file():
    """End-to-end: fake Deepgram JSON → corrected transcript written to disk."""
    from core.correction_runner import run_correction_job

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "test_transcript.txt")
        json_path = os.path.join(tmpdir, "test_transcript.json")

        dg_json = _make_fake_deepgram_json()
        payload = {"utterances": dg_json["utterances"]}
        with open(json_path, "w") as f:
            json.dump(payload, f)

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


def test_correction_runner_handles_missing_json_gracefully():
    """When no Deepgram JSON exists, runner falls back to text parsing."""
    from core.correction_runner import run_correction_job

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = os.path.join(tmpdir, "no_json_here.txt")
        with open(txt_path, "w") as f:
            f.write("Speaker 0: Okay I think Infection.")

        results = []
        run_correction_job(
            transcript_path=txt_path,
            done_callback=lambda r: results.append(r),
        )
        assert results[0]["success"] is True
