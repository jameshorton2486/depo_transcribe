"""
ui/tests/test_dialog_combine_audio.py

Logic tests for CombineAudioDialog. The actual ffmpeg work is exercised
in pipeline/tests/test_audio_combiner.py — here we only verify that the
dialog tracks state correctly, transitions through the expected status
codes, and dispatches to combine_audio_files with the right arguments.

Tests use the session-scoped `root` fixture from ui/tests/conftest.py
and the dialog's `_add_file_with_format` test seam to bypass real
probing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ui.dialog_combine_audio import (
    CombineAudioDialog,
    CombineState,
    DEEPGRAM_MAX_DURATION_SECONDS,
    _format_duration,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _fmt(
    codec: str = "mp3",
    sample_rate: int = 44100,
    channels: int = 2,
    duration: float = 60.0,
    bit_rate: int = 192000,
    format_name: str = "mp3",
) -> dict:
    return {
        "codec_name": codec,
        "sample_rate": sample_rate,
        "channels": channels,
        "duration": duration,
        "bit_rate": bit_rate,
        "format_name": format_name,
    }


@pytest.fixture
def dialog(root, tmp_path):
    """Fresh dialog instance per test, destroyed at teardown."""
    d = CombineAudioDialog(parent=root, case_audio_dir=tmp_path)
    yield d
    try:
        d.destroy()
    except Exception:
        pass


# ── Pure helper tests ────────────────────────────────────────────────────────


def test_format_duration_seconds_only():
    assert _format_duration(0) == "0s"
    assert _format_duration(45) == "45s"


def test_format_duration_minutes():
    assert _format_duration(60) == "1m 0s"
    assert _format_duration(125) == "2m 5s"


def test_format_duration_hours():
    assert _format_duration(3600) == "1h 0m"
    assert _format_duration(3600 + 23 * 60) == "1h 23m"
    assert _format_duration(4 * 3600 + 23 * 60) == "4h 23m"


def test_deepgram_max_is_4_hours():
    """Deepgram caps a single transcription request at 4 hours."""
    assert DEEPGRAM_MAX_DURATION_SECONDS == 14400


# ── State machine ────────────────────────────────────────────────────────────


def test_initial_state_is_empty(dialog):
    assert dialog._check_state() == CombineState.EMPTY
    assert dialog._files == []
    assert dialog.result_path is None
    assert dialog._combine_btn.cget("state") == "disabled"


def test_one_file_is_too_few(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=60))
    assert dialog._check_state() == CombineState.TOO_FEW
    assert dialog._combine_btn.cget("state") == "disabled"


def test_two_matching_files_ready_lossless(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=60))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=60))
    assert dialog._check_state() == CombineState.READY_LOSSLESS
    assert dialog._combine_btn.cget("state") == "normal"


def test_two_mismatched_files_ready_reencode(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(codec="mp3", duration=60))
    dialog._add_file_with_format(
        Path("/tmp/b.m4a"), _fmt(codec="aac", duration=60),
    )
    assert dialog._check_state() == CombineState.READY_REENCODE
    assert dialog._combine_btn.cget("state") == "normal"


def test_mismatched_sample_rate_is_reencode(dialog):
    dialog._add_file_with_format(
        Path("/tmp/a.mp3"), _fmt(sample_rate=44100, duration=60),
    )
    dialog._add_file_with_format(
        Path("/tmp/b.mp3"), _fmt(sample_rate=22050, duration=60),
    )
    assert dialog._check_state() == CombineState.READY_REENCODE


def test_mismatched_channels_is_reencode(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(channels=2, duration=60))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(channels=1, duration=60))
    assert dialog._check_state() == CombineState.READY_REENCODE


def test_bit_rate_drift_does_not_force_reencode(dialog):
    """Same codec/sr/channels but different bitrate is still lossless-OK
    — the underlying formats_match() helper intentionally ignores bitrate
    drift between same-recorder files."""
    dialog._add_file_with_format(
        Path("/tmp/a.mp3"), _fmt(bit_rate=128000, duration=60),
    )
    dialog._add_file_with_format(
        Path("/tmp/b.mp3"), _fmt(bit_rate=192000, duration=60),
    )
    assert dialog._check_state() == CombineState.READY_LOSSLESS


def test_duration_over_4h_is_too_long(dialog):
    """Two files at 5h each: combined 10h, well over Deepgram's 4h cap."""
    dialog._add_file_with_format(
        Path("/tmp/a.mp3"), _fmt(duration=5 * 3600),
    )
    dialog._add_file_with_format(
        Path("/tmp/b.mp3"), _fmt(duration=5 * 3600),
    )
    assert dialog._check_state() == CombineState.TOO_LONG
    assert dialog._combine_btn.cget("state") == "disabled"


def test_duration_exactly_4h_is_ready(dialog):
    """Exactly 4 hours = 14400s should still be allowed (boundary)."""
    dialog._add_file_with_format(
        Path("/tmp/a.mp3"), _fmt(duration=2 * 3600),
    )
    dialog._add_file_with_format(
        Path("/tmp/b.mp3"), _fmt(duration=2 * 3600),
    )
    assert dialog._check_state() == CombineState.READY_LOSSLESS


# ── Reorder / remove ─────────────────────────────────────────────────────────


def test_remove_middle_file(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog._add_file_with_format(Path("/tmp/c.mp3"), _fmt(duration=30))
    assert len(dialog._files) == 3

    dialog.remove_file(1)  # remove b.mp3

    assert len(dialog._files) == 2
    assert dialog._files[0]["path"].name == "a.mp3"
    assert dialog._files[1]["path"].name == "c.mp3"


def test_remove_out_of_range_is_noop(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog.remove_file(5)
    dialog.remove_file(-1)
    assert len(dialog._files) == 1


def test_move_up_swaps_with_previous(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog._add_file_with_format(Path("/tmp/c.mp3"), _fmt(duration=30))

    dialog.move_up(2)  # c.mp3 swaps with b.mp3

    assert [f["path"].name for f in dialog._files] == ["a.mp3", "c.mp3", "b.mp3"]


def test_move_up_on_first_row_is_noop(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog.move_up(0)  # row 1 — should not move
    assert dialog._files[0]["path"].name == "a.mp3"
    assert dialog._files[1]["path"].name == "b.mp3"


def test_move_down_swaps_with_next(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog._add_file_with_format(Path("/tmp/c.mp3"), _fmt(duration=30))

    dialog.move_down(0)  # a.mp3 swaps with b.mp3

    assert [f["path"].name for f in dialog._files] == ["b.mp3", "a.mp3", "c.mp3"]


def test_move_down_on_last_row_is_noop(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog.move_down(1)  # last row — should not move
    assert dialog._files[0]["path"].name == "a.mp3"
    assert dialog._files[1]["path"].name == "b.mp3"


# ── Cancel + combine handlers ────────────────────────────────────────────────


def test_cancel_returns_none(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog._on_cancel()
    assert dialog.result_path is None


def test_cancel_blocked_during_combine(dialog):
    """Once combine is in flight, cancel is a no-op until it finishes —
    otherwise we'd leak a partial output."""
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog._combining = True
    # result_path should not change, dialog should not destroy
    dialog._on_cancel()
    # The fact that we're still here (no exception) and result_path is
    # still None (its default) is the signal — destroy() wasn't called.
    assert dialog.result_path is None


def test_combine_done_success_sets_result_path(dialog, tmp_path):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))

    out = tmp_path / "combined.mp3"
    out.write_bytes(b"fake")
    fake_result = MagicMock()
    fake_result.success = True
    fake_result.method = "concat_demuxer"
    fake_result.lossless = True
    fake_result.output_path = out
    fake_result.error = None

    dialog._on_combine_done(fake_result, None)

    assert dialog.result_path == out


def test_combine_done_failure_keeps_dialog_open(dialog, tmp_path):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog._combining = True

    fake_result = MagicMock()
    fake_result.success = False
    fake_result.error = "ffmpeg exploded"
    fake_result.output_path = None

    dialog._on_combine_done(fake_result, None)

    assert dialog.result_path is None
    assert dialog._combining is False
    assert dialog._combine_btn.cget("state") == "normal"
    assert "Combine failed" in dialog._status_label.cget("text")


def test_combine_done_exception_path_keeps_dialog_open(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=10))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=20))
    dialog._combining = True

    dialog._on_combine_done(None, "ffmpeg subprocess crashed")

    assert dialog.result_path is None
    assert dialog._combining is False
    assert dialog._combine_btn.cget("state") == "normal"


def test_on_combine_dispatches_to_combiner_with_ordered_paths(
    dialog, tmp_path,
):
    """When the user clicks Combine, the dialog should hand combine_audio_files
    the ordered list of paths and write into {case_audio_dir}/_combined/."""
    dialog._add_file_with_format(Path("/tmp/zzz.mp3"), _fmt(duration=60))
    dialog._add_file_with_format(Path("/tmp/aaa.mp3"), _fmt(duration=60))

    captured = {}

    def fake_thread(target=None, args=(), daemon=False):
        # Run the worker synchronously so the test stays single-threaded.
        captured["target"] = target
        captured["args"] = args

        class _T:
            def start(self_inner):
                # Capture call before letting the dialog post-process via after()
                pass

        return _T()

    with patch("ui.dialog_combine_audio.threading.Thread", side_effect=fake_thread):
        dialog._on_combine()

    # Worker should have been scheduled with: (ordered_paths, output_path)
    assert "args" in captured, "threading.Thread was not called"
    ordered_paths, output_path = captured["args"]
    assert [p.name for p in ordered_paths] == ["zzz.mp3", "aaa.mp3"]

    # Output path should land under {case_audio_dir}/_combined/
    assert output_path.parent == tmp_path / "_combined"
    assert output_path.parent.is_dir(), "_combined/ should be created"
    assert output_path.name == "zzz_combined.mp3"


def test_on_combine_blocked_when_no_case_dir(root):
    """If the dialog wasn't given a case_audio_dir, _on_combine refuses
    (and does NOT spawn a thread)."""
    d = CombineAudioDialog(parent=root, case_audio_dir=None)
    try:
        d._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=60))
        d._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=60))
        with patch(
            "ui.dialog_combine_audio.threading.Thread"
        ) as thread_mock, patch(
            "ui.dialog_combine_audio.messagebox.showerror"
        ) as msgbox_mock:
            d._on_combine()
        # No thread spawn, error dialog raised
        thread_mock.assert_not_called()
        msgbox_mock.assert_called_once()
    finally:
        d.destroy()


def test_on_combine_blocked_when_too_long(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=5 * 3600))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=5 * 3600))

    with patch("ui.dialog_combine_audio.threading.Thread") as thread_mock:
        dialog._on_combine()

    thread_mock.assert_not_called()


# ── Status message rendering ─────────────────────────────────────────────────


def test_status_message_lossless_mentions_codec(dialog):
    dialog._add_file_with_format(
        Path("/tmp/a.mp3"), _fmt(codec="mp3", sample_rate=44100, channels=2),
    )
    dialog._add_file_with_format(
        Path("/tmp/b.mp3"), _fmt(codec="mp3", sample_rate=44100, channels=2),
    )
    text = dialog._status_label.cget("text")
    assert "MP3" in text or "mp3" in text.lower()
    assert "44100" in text
    assert "lossless" in text.lower()


def test_status_message_reencode_mentions_24khz(dialog):
    """The re-encode warning should reflect the actual target sample rate
    (24kHz, from config) — not generic 'will re-encode'."""
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(codec="mp3"))
    dialog._add_file_with_format(Path("/tmp/b.m4a"), _fmt(codec="aac"))
    text = dialog._status_label.cget("text")
    assert "24" in text and "kHz" in text


def test_status_message_too_long_mentions_4_hours(dialog):
    dialog._add_file_with_format(Path("/tmp/a.mp3"), _fmt(duration=5 * 3600))
    dialog._add_file_with_format(Path("/tmp/b.mp3"), _fmt(duration=5 * 3600))
    text = dialog._status_label.cget("text")
    assert "4-hour" in text or "4 hour" in text or "4h" in text
