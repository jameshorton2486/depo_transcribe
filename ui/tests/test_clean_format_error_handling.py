"""Tests for the MarkerDriftError handling in TranscribeTab.

Verifies the post-Step-E behavior added on top of commit 601b943:

  * TranscribeTab._run_clean_format_job catches MarkerDriftError specifically
    (ahead of the generic Exception catch) and routes it through with a
    ``marker_drift=True`` flag in the result dict.
  * exc.stats lands in the WARNING log as ``marker_drift_stats: {...}``
    so the structured dict is grep-able for later threshold tuning.
  * TranscribeTab._on_clean_format_done fires ``messagebox.showerror`` when
    the result carries the marker_drift flag, matching the "Document Write
    Failed" popup style at the other no-output path.
  * Non-MarkerDriftError exceptions do not set the flag and do not fire
    the dedicated popup.

The tests build a MagicMock(spec=TranscribeTab) rather than instantiating
the CTk widget, so no Tk loop is required.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from clean_format.low_confidence_markers import MarkerDriftError
from ui.tab_transcribe import TranscribeTab


def _make_drift_error(
    *, input_count: int = 200, output_count: int = 153
) -> MarkerDriftError:
    dropped = input_count - output_count
    drop_pct = (dropped / input_count) * 100 if input_count else 0.0
    return MarkerDriftError(
        f"Systematic marker drift in Anthropic response: dropped "
        f"{dropped} of {input_count} markers ({drop_pct:.1f}%). "
        f"Cleanup pass is not honoring the marker preservation rule "
        f"for this chunk.",
        stats={
            "input_count": input_count,
            "output_count": output_count,
            "dropped": dropped,
        },
    )


class TestRunCleanFormatJobMarkerDriftCatch:
    """The except MarkerDriftError clause inside _run_clean_format_job."""

    def _prep_paths(self, tmp_path):
        (tmp_path / "Deepgram").mkdir(parents=True, exist_ok=True)
        raw_txt = tmp_path / "raw.txt"
        raw_txt.write_text("dummy raw transcript", encoding="utf-8")
        return {
            "output_dir": str(tmp_path),
            "raw_txt_path": str(raw_txt),
        }

    def _make_mock_self(self):
        mock_self = MagicMock(spec=TranscribeTab)
        mock_self._build_clean_format_case_meta.return_value = {
            "witness_name": "Test Witness",
            "deposition_date": "2026-05-12",
        }
        captured: list = []
        mock_self.after = lambda _delay, fn, payload: captured.append((fn, payload))
        return mock_self, captured

    def test_marker_drift_sets_flag_and_logs_stats(self, tmp_path, caplog):
        mock_self, captured = self._make_mock_self()
        job_result = self._prep_paths(tmp_path)
        drift_error = _make_drift_error(input_count=200, output_count=153)

        with patch(
            "clean_format.format_transcript", side_effect=drift_error
        ), patch("clean_format.write_deposition_docx"), patch(
            "clean_format.formatter.load_deepgram_words_from_json",
            return_value=[],
        ), caplog.at_level(logging.WARNING):
            TranscribeTab._run_clean_format_job(mock_self, job_result)

        assert len(captured) == 1, (
            "exactly one result dict should be scheduled on the UI thread"
        )
        _, payload = captured[0]
        assert payload["success"] is False
        assert payload["marker_drift"] is True
        assert "Systematic marker drift" in payload["error"]

        warning_records = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "marker_drift_stats" in r.getMessage()
        ]
        assert warning_records, (
            "exc.stats must land in a WARNING log line tagged "
            "'marker_drift_stats' for grep-ability"
        )
        msg = warning_records[0].getMessage()
        assert "input_count" in msg
        assert "dropped" in msg

    def test_generic_exception_does_not_set_marker_drift_flag(self, tmp_path):
        mock_self, captured = self._make_mock_self()
        job_result = self._prep_paths(tmp_path)

        with patch(
            "clean_format.format_transcript",
            side_effect=RuntimeError("some other failure"),
        ), patch("clean_format.write_deposition_docx"), patch(
            "clean_format.formatter.load_deepgram_words_from_json",
            return_value=[],
        ):
            TranscribeTab._run_clean_format_job(mock_self, job_result)

        assert len(captured) == 1
        _, payload = captured[0]
        assert payload["success"] is False
        assert "marker_drift" not in payload


class TestOnCleanFormatDonePopupOnMarkerDrift:
    """The messagebox.showerror call added to _on_clean_format_done."""

    def test_marker_drift_result_fires_showerror_with_exc_text(self):
        # spec= is intentionally omitted: _on_clean_format_done touches
        # instance attributes (_status_progress, etc.) that __init__
        # creates, which aren't visible on the class spec.
        mock_self = MagicMock()
        message = (
            "Systematic marker drift in Anthropic response: dropped "
            "47 of 200 markers (23.5%)."
        )
        result = {
            "success": False,
            "error": message,
            "marker_drift": True,
        }
        with patch("ui.tab_transcribe.messagebox") as fake_mb:
            TranscribeTab._on_clean_format_done(mock_self, result)

        assert fake_mb.showerror.called
        title, body = fake_mb.showerror.call_args.args
        assert title == "Cleanup Failed: Marker Drift"
        # The full exception text is preserved verbatim in the body.
        assert body == message

    def test_generic_failure_does_not_fire_showerror(self):
        mock_self = MagicMock()
        result = {"success": False, "error": "Some other failure"}
        with patch("ui.tab_transcribe.messagebox") as fake_mb:
            TranscribeTab._on_clean_format_done(mock_self, result)
        assert not fake_mb.showerror.called
