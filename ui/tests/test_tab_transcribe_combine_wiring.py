"""
ui/tests/test_tab_transcribe_combine_wiring.py

Tests for the multi-file Combine wiring on the Transcribe tab.

The TranscribeTab itself is heavy (case-folder resolution, audio
preview, NOD-PDF upload, intake AI, speaker suggestions) and not
practical to instantiate in a unit test. Instead, the methods added in
commit 4 are deliberately small and side-effect-isolated so they can
be exercised by binding them to a stub object that supplies just the
attributes they read.

This trades some realism for test stability — the integration we can't
unit-test cleanly (real Tk button clicks, real dialog rendering) is
covered by manual click-through verification listed in the order-of-
work plan.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ui.tab_transcribe import TranscribeTab


# ── Method existence + signatures ────────────────────────────────────────────


def test_methods_added_to_tab():
    """The four new methods exist on the class without instantiating it."""
    assert hasattr(TranscribeTab, "_open_combine_dialog")
    assert hasattr(TranscribeTab, "_ingest_selected_audio")
    assert hasattr(TranscribeTab, "_resolve_combine_output_dir")
    # _browse_file is unchanged in name, the wiring just delegates to
    # _ingest_selected_audio now.
    assert hasattr(TranscribeTab, "_browse_file")


# ── _resolve_combine_output_dir ──────────────────────────────────────────────


def test_resolve_uses_case_root_when_present(tmp_path):
    """When case_root resolves and exists, output dir is
    {case_root}/source_docs/."""
    case_root = tmp_path / "2026" / "Apr" / "DC-25-13430" / "leifer_dr"
    case_root.mkdir(parents=True)

    stub = SimpleNamespace(
        _get_current_save_path=lambda: str(case_root),
        _create_case_folders_now=MagicMock(),
    )
    result = TranscribeTab._resolve_combine_output_dir(stub)

    assert result == case_root / "source_docs"
    stub._create_case_folders_now.assert_called_once()


def test_resolve_falls_back_when_case_root_empty(tmp_path):
    """No case info filled in → fallback to TEMP_DIR/combined_<ts>/."""
    stub = SimpleNamespace(
        _get_current_save_path=lambda: "",
        _create_case_folders_now=MagicMock(),
    )

    with patch("config.TEMP_DIR", str(tmp_path)):
        result = TranscribeTab._resolve_combine_output_dir(stub)

    # Folder creation should NOT happen — there is no case folder yet.
    stub._create_case_folders_now.assert_not_called()
    # Result lives under TEMP_DIR with a "combined_" prefix.
    assert result.parent == tmp_path
    assert result.name.startswith("combined_")


def test_resolve_falls_back_when_case_root_missing(tmp_path):
    """case_root reported but folder doesn't actually exist → fallback.
    Defends against stale paths from incomplete intake."""
    nonexistent = tmp_path / "does" / "not" / "exist"
    stub = SimpleNamespace(
        _get_current_save_path=lambda: str(nonexistent),
        _create_case_folders_now=MagicMock(),
    )

    with patch("config.TEMP_DIR", str(tmp_path)):
        result = TranscribeTab._resolve_combine_output_dir(stub)

    stub._create_case_folders_now.assert_not_called()
    assert result.parent == tmp_path
    assert result.name.startswith("combined_")


def test_resolve_strips_whitespace_from_case_root(tmp_path):
    """Some intake paths come back with surrounding whitespace —
    treat that as not-yet-set rather than a real path."""
    stub = SimpleNamespace(
        _get_current_save_path=lambda: "   ",
        _create_case_folders_now=MagicMock(),
    )
    with patch("config.TEMP_DIR", str(tmp_path)):
        result = TranscribeTab._resolve_combine_output_dir(stub)

    assert result.parent == tmp_path
    assert result.name.startswith("combined_")


# ── _ingest_selected_audio ───────────────────────────────────────────────────


def test_ingest_resets_case_state_and_extracts_filename(tmp_path):
    """Single-file Browse and multi-file Combine should both go through
    _ingest_selected_audio so case-state cleanup + filename extraction
    happen consistently."""
    after_calls = []
    stub = SimpleNamespace(
        _correction_mode=False,
        _clear_correction_mode=MagicMock(),
        _reset_case_state=MagicMock(),
        _selected_file=None,
        _set_entry_text=MagicMock(),
        _file_entry=object(),
        _apply_filename_extraction=MagicMock(),
        _auto_detect_source_docs=MagicMock(),
        after=lambda delay, fn: after_calls.append((delay, fn)),
    )

    target = str(tmp_path / "combined.mp3")
    TranscribeTab._ingest_selected_audio(stub, target)

    stub._reset_case_state.assert_called_once()
    stub._clear_correction_mode.assert_not_called()  # not in correction mode
    assert stub._selected_file == target
    stub._set_entry_text.assert_called_once_with(stub._file_entry, target)
    stub._apply_filename_extraction.assert_called_once_with(target)
    # _auto_detect_source_docs is scheduled via .after(300, …)
    assert len(after_calls) == 1
    assert after_calls[0][0] == 300
    assert after_calls[0][1] is stub._auto_detect_source_docs


def test_ingest_clears_correction_mode_when_active(tmp_path):
    stub = SimpleNamespace(
        _correction_mode=True,
        _clear_correction_mode=MagicMock(),
        _reset_case_state=MagicMock(),
        _selected_file=None,
        _set_entry_text=MagicMock(),
        _file_entry=object(),
        _apply_filename_extraction=MagicMock(),
        _auto_detect_source_docs=MagicMock(),
        after=lambda delay, fn: None,
    )
    TranscribeTab._ingest_selected_audio(stub, str(tmp_path / "x.mp3"))
    stub._clear_correction_mode.assert_called_once()


# ── _open_combine_dialog ─────────────────────────────────────────────────────


def test_open_dialog_ingests_result_path_on_success(tmp_path):
    """On success: dialog returns a path → _ingest_selected_audio is
    called with that path."""
    fake_dialog = MagicMock()
    combined_path = tmp_path / "combined.mp3"
    fake_dialog.result_path = combined_path

    stub = SimpleNamespace(
        _resolve_combine_output_dir=lambda: tmp_path,
        wait_window=MagicMock(),
        _ingest_selected_audio=MagicMock(),
    )

    with patch(
        "ui.dialog_combine_audio.CombineAudioDialog",
        return_value=fake_dialog,
    ):
        TranscribeTab._open_combine_dialog(stub)

    stub.wait_window.assert_called_once_with(fake_dialog)
    stub._ingest_selected_audio.assert_called_once_with(str(combined_path))


def test_open_dialog_does_nothing_on_cancel(tmp_path):
    """On cancel: dialog.result_path is None → no ingestion."""
    fake_dialog = MagicMock()
    fake_dialog.result_path = None

    stub = SimpleNamespace(
        _resolve_combine_output_dir=lambda: tmp_path,
        wait_window=MagicMock(),
        _ingest_selected_audio=MagicMock(),
    )

    with patch(
        "ui.dialog_combine_audio.CombineAudioDialog",
        return_value=fake_dialog,
    ):
        TranscribeTab._open_combine_dialog(stub)

    stub.wait_window.assert_called_once_with(fake_dialog)
    stub._ingest_selected_audio.assert_not_called()


def test_open_dialog_passes_case_audio_dir_through(tmp_path):
    """The dialog must receive the resolved output dir so it knows
    where to write the combined file."""
    captured = {}

    def fake_dialog_init(parent, case_audio_dir):
        captured["parent"] = parent
        captured["case_audio_dir"] = case_audio_dir
        d = MagicMock()
        d.result_path = None
        return d

    stub = SimpleNamespace(
        _resolve_combine_output_dir=lambda: tmp_path / "source_docs",
        wait_window=MagicMock(),
        _ingest_selected_audio=MagicMock(),
    )

    with patch(
        "ui.dialog_combine_audio.CombineAudioDialog",
        side_effect=fake_dialog_init,
    ):
        TranscribeTab._open_combine_dialog(stub)

    assert captured["parent"] is stub
    assert captured["case_audio_dir"] == tmp_path / "source_docs"
