"""
ui/tab_transcript.py

Transcript review tab with:
  - editable transcript view
  - word-level confidence highlighting
  - click-to-jump VLC playback
  - review DOCX export for confidence audit
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from core.confidence_docx_exporter import export_confidence_docx
from core.job_config_manager import load_job_config, merge_and_save
from core.vlc_player import VLCPlayer
from core.word_data_loader import get_flagged_summary, get_confidence_tier, load_words_for_transcript
from ui.tab_transcribe import (
    _build_ui_speaker_reference_text,
    _normalize_ui_speaker_map,
    _normalize_ui_speaker_suggestion,
)

_CONFIDENCE_STOP_WORDS = frozenset({
    "a", "an", "the",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "into", "through", "about", "as", "up", "down", "out",
    "and", "or", "but", "so", "yet", "nor",
    "i", "you", "he", "she", "it", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "its", "our",
    "their", "that", "this", "these", "those",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "do", "did", "does", "have", "has", "had", "will", "would",
    "can", "could", "should", "may", "might", "shall",
    "not", "no", "yes", "just", "also", "very", "well",
    "now", "then", "here", "there", "too", "so",
    "mr", "ms", "mrs", "dr", "sir", "ma'am",
    "okay", "ok", "right", "correct",
})

CONFIDENCE_AMBER_THRESHOLD = 0.75
CONFIDENCE_RED_THRESHOLD = 0.50

COLOR_AMBER = "#B8860B"
COLOR_RED = "#CC2200"

_TRANSCRIPTION_PROGRESS_RE = re.compile(r'chunk\s+(\d+)\s+of\s+(\d+)', re.IGNORECASE)
_SPEAKER_LABEL_RE = re.compile(r'(^|\n)(Speaker\s+(\d+)):\s*', re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOG_FILES = ("app.log", "pipeline.log")


def _extract_speaker_ids(text: str) -> list[str]:
    speaker_ids = {match.group(3) for match in _SPEAKER_LABEL_RE.finditer(text or "")}
    return sorted(speaker_ids, key=int)


def _normalize_transcript_speaker_map(raw: dict | None) -> dict[int, str]:
    return _normalize_ui_speaker_map(raw)


def _apply_speaker_map_to_text(text: str, speaker_map: dict[int, str]) -> str:
    def _replace(match: re.Match) -> str:
        speaker_id = int(match.group(3))
        replacement = speaker_map.get(speaker_id)
        if not replacement:
            return match.group(0)
        prefix = match.group(1) or ""
        return f"{prefix}{replacement}: "

    return _SPEAKER_LABEL_RE.sub(_replace, text or "")


def _build_progressive_speaker_defaults(
    transcript_text: str,
    saved_map: dict[int, str] | None,
    suggestion: dict[str, object] | None,
) -> dict[str, str]:
    speaker_ids = _extract_speaker_ids(transcript_text)
    normalized_saved = _normalize_transcript_speaker_map(saved_map or {})
    defaults: dict[str, str] = {}

    for sid in speaker_ids:
        try:
            speaker_id = int(sid)
        except ValueError:
            continue
        defaults[f"Speaker {sid}"] = normalized_saved.get(speaker_id, f"Speaker {sid}")

    return defaults


def _resolve_case_root_for_transcript(filepath: str) -> tuple[str | None, bool]:
    path = Path(filepath)
    parent = path.parent

    if parent.name.lower() == "deepgram":
        return str(parent.parent), True

    if (parent / "Deepgram").is_dir() and (parent / "source_docs").is_dir():
        return str(parent), True

    return None, False


def _build_transcript_context_status(config_data: dict[str, Any] | None) -> tuple[str, str]:
    if not isinstance(config_data, dict) or not config_data:
        return (
            "No case configuration found — limited corrections will run.",
            "#CCAA44",
        )

    ufm = config_data.get("ufm_fields", {})
    if not isinstance(ufm, dict) or not ufm:
        return (
            "Case configuration loaded, but UFM fields are missing — draft corrections only.",
            "#CCAA44",
        )

    mode = "Final" if ufm.get("speaker_map_verified") else "Draft"
    return (
        f"Case configuration loaded — Mode: {mode}.",
        "#44FF44" if mode == "Final" else "#CCAA44",
    )


def _build_debug_bundle_paths(
    transcript_path: str | None,
    case_root: str | None,
) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []

    for log_name in _LOG_FILES:
        paths.append((f"logs/{log_name}", _REPO_ROOT / "logs" / log_name))

    if transcript_path:
        transcript = Path(transcript_path)
        paths.append(("transcript", transcript))

        json_path = transcript.with_suffix(".json")
        if transcript.stem.endswith("_corrected"):
            base_stem = transcript.stem[: -len("_corrected")]
            json_path = transcript.with_name(f"{base_stem}.json")
        paths.append(("deepgram_json", json_path))

        corrected_path = transcript.with_name(f"{transcript.stem}_corrected.txt")
        corrections_path = transcript.with_name(f"{transcript.stem}_corrections.json")
        if transcript.stem.endswith("_corrected"):
            corrected_path = transcript
            corrections_path = transcript.with_name(
                f"{transcript.stem[: -len('_corrected')]}_corrections.json"
            )

        paths.append(("corrected_transcript", corrected_path))
        paths.append(("corrections_json", corrections_path))

    if case_root:
        paths.append(("job_config", Path(case_root) / "source_docs" / "job_config.json"))

    deduped: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for label, path in paths:
        resolved = Path(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append((label, resolved))

    return deduped


def _build_debug_bundle_text(
    transcript_path: str | None,
    case_root: str | None,
) -> str:
    sections = ["# Depo Transcribe Debug Bundle"]

    for label, path in _build_debug_bundle_paths(transcript_path, case_root):
        sections.append("")
        sections.append(f"## {label}")
        sections.append(f"PATH: {path}")
        if not path.exists():
            sections.append("[missing]")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            sections.append(f"[unreadable] {exc}")
            continue
        sections.append(content.rstrip())

    return "\n".join(sections).strip() + "\n"


class TranscriptTab(ctk.CTkFrame):
    """Transcript review workspace with audio sync and confidence markup."""

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._current_path: str | None = None
        self._corrected_path: str | None = None
        self._current_folder_path: str | None = None
        self._audio_path: str | None = None
        self._review_docx_path: str | None = None
        self._formatted_docx_path: str | None = None
        self._original_text: str | None = None
        self._processed_text: str | None = None
        self._canonical_text: str = ""
        self._word_map: list[dict] = []
        self._word_timings: list[dict] = []
        self._sync_timer_id: str | None = None
        self._remap_job: str | None = None
        self._edit_mode: bool = False
        self._current_word_idx: int = -1
        self.review_state: dict[int, str] = {}
        self._current_review_idx: int = -1
        self._case_root: str | None = None
        self._speaker_entries: dict[str, ctk.CTkEntry] = {}
        self._speaker_map_suggestion: dict[str, object] = {}
        self._saved_speaker_map: dict[int, str] = {}
        self._speaker_map_verified: bool = False
        self._speaker_mapping_dirty: bool = False
        self._speaker_panel_expanded: bool = True
        self._mapping_source_text: str = ""
        self._selected_speaker_label: str | None = None
        self._job_config_data: dict[str, Any] = {}

        self._player: VLCPlayer | None = None
        self._player_ready = False
        self._speed_rates = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        self._speed_idx = 2   # index into _speed_rates; 2 = 1.0x (default)
        self._gap_threshold = 2.0   # seconds of silence that qualify as a skippable gap
        self._waveform_peaks: list[float] = []   # normalised 0.0–1.0 amplitude per bucket
        self._waveform_duration: float = 0.0
        self._waveform_request_id: int = 0
        self._position_job = None
        self._click_pending_id: str | None = None
        self._click_count: int = 0
        self._user_is_editing: bool = False
        self._last_edit_position: str | None = None
        self._edit_idle_timer_id: str | None = None

        self._words: list[dict] = []
        self._word_data_request_id = 0
        self._low_confidence_words: list[dict] = []
        self._ai_running = False
        self._format_running = False
        self._transcription_running = False
        self._bottom_panel_visible = False
        self._conf_list_visible = False
        self._speaker_tools_visible = False

        self._highlight_var = ctk.BooleanVar(value=True)
        self._build_ui()
        self._init_player()

    def _active_transcript_path(self) -> str | None:
        if self._corrected_path and os.path.isfile(self._corrected_path):
            return self._corrected_path
        return self._current_path

    def _save_target_path(self) -> str | None:
        return self._active_transcript_path()

    def _update_audio_state(self, text: str, color: str = "#445566") -> None:
        self._audio_state_label.configure(text=text, text_color=color)

    def _toggle_bottom_panel(self) -> None:
        if self._bottom_panel_visible:
            self._bottom_panel.pack_forget()
            self._panel_toggle_btn.configure(text="▶  Audio & Review Tools")
            self._bottom_panel_visible = False
        else:
            self._bottom_panel.pack(fill="x", side="bottom", before=self._panel_toggle_btn)
            self._panel_toggle_btn.configure(text="▼  Audio & Review Tools")
            self._bottom_panel_visible = True

    def _ensure_bottom_panel_open(self) -> None:
        if not self._bottom_panel_visible:
            self._toggle_bottom_panel()

    def _toggle_speaker_tools(self) -> None:
        if self._speaker_tools_visible:
            self._edit_toolbar.pack_forget()
            self._speaker_toggle_btn.configure(text="+ Insert Speaker Break")
            self._speaker_tools_visible = False
        else:
            self._edit_toolbar.pack(fill="x", padx=8, pady=(0, 4), after=self._speaker_toggle_btn)
            self._speaker_toggle_btn.configure(text="− Insert Speaker Break")
            self._speaker_tools_visible = True

    def _toggle_conf_list(self) -> None:
        if not self._low_confidence_words:
            self._conf_toggle_btn.configure(text="▶  0 low-confidence words")
            return
        if self._conf_list_visible:
            self._low_conf_frame.pack_forget()
            self._conf_list_visible = False
            self._conf_toggle_btn.configure(text=f"▶  {len(self._low_confidence_words)} low-confidence words")
        else:
            self._low_conf_frame.pack(fill="x", padx=8, pady=(0, 2), after=self._conf_toggle_btn)
            self._conf_list_visible = True
            self._conf_toggle_btn.configure(text=f"▼  {len(self._low_confidence_words)} low-confidence words")

    def _update_path_label(self) -> None:
        target = self._corrected_path or self._current_path
        if not target:
            self._path_label.configure(text="No file loaded", text_color="#445566")
            return
        name = os.path.basename(target)
        if len(name) > 70:
            name = name[:67] + "..."
        prefix = "Processed" if self._corrected_path else "Loaded"
        self._path_label.configure(text=f"{prefix}: {name}", text_color="#445566")

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(2, 1))

        ctk.CTkLabel(
            header,
            text="Transcript",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left")

        self._open_file_btn = ctk.CTkButton(
            header,
            text=" Open File",
            width=110,
            command=self._browse_transcript_file,
        )
        self._open_file_btn.pack(side="right", padx=(4, 0))

        self._run_corrections_btn = ctk.CTkButton(
            header,
            text="⚙ Run Corrections",
            width=145,
            fg_color="#1A6B3A",
            hover_color="#145230",
            state="disabled",
            command=self._run_corrections_pipeline,
        )
        self._run_corrections_btn.pack(side="right", padx=(4, 0))

        # Optional Claude AI pass over the current transcript text. Disabled
        # until a transcript is loaded. Runs in a background thread via
        # _on_ai_correct_clicked -> _start_ai_correction -> _run_ai_job.
        self._ai_correct_btn = ctk.CTkButton(
            header,
            text="✨ AI Correct",
            width=130,
            fg_color="#6B2A8C",
            hover_color="#4E1E66",
            state="disabled",
            command=self._on_ai_correct_clicked,
        )
        self._ai_correct_btn.pack(side="right", padx=(4, 0))

        self._format_btn = None

        self._fnr_toggle_btn = ctk.CTkButton(
            header,
            text="Find & Replace",
            width=120,
            fg_color="transparent",
            border_width=1,
            border_color="#334",
            text_color="#8ab",
            command=self._toggle_find_replace,
        )
        self._fnr_toggle_btn.pack(side="right", padx=(4, 0))

        self._copy_btn = ctk.CTkButton(
            header,
            text=" Copy All",
            width=110,
            command=self._copy_all,
            state="disabled",
        )
        self._copy_btn.pack(side="right", padx=(4, 0))

        self._copy_debug_btn = ctk.CTkButton(
            header,
            text="Copy Debug Bundle",
            width=150,
            command=self._copy_debug_bundle,
            state="disabled",
        )
        self._copy_debug_btn.pack(side="right", padx=(4, 0))

        self._save_btn = ctk.CTkButton(
            header,
            text=" Save",
            width=90,
            command=self._save_transcript,
            state="disabled",
        )
        self._save_btn.pack(side="right", padx=(4, 0))

        self._status_bar = ctk.CTkFrame(self, height=22, fg_color="#0A1520", corner_radius=0)
        self._status_bar.pack(fill="x", padx=0, pady=(0, 1))
        self._status_bar.pack_propagate(False)

        self._path_label = ctk.CTkLabel(
            self._status_bar,
            text="No file loaded",
            font=ctk.CTkFont(size=11),
            text_color="#445566",
            anchor="w",
        )
        self._path_label.pack(side="left", padx=8)

        self._status_label = ctk.CTkLabel(
            self._status_bar,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="#7D8FA3",
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True, padx=(8, 8))

        self._audio_state_label = ctk.CTkLabel(
            self._status_bar,
            text="Audio stopped",
            font=ctk.CTkFont(size=11),
            text_color="#445566",
            anchor="e",
        )
        self._audio_state_label.pack(side="right", padx=8)

        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._progress_bar = ctk.CTkProgressBar(
            self._progress_frame,
            width=400,
            height=16,
            corner_radius=4,
            fg_color="#1A2A3A",
            progress_color="#1558C0",
        )
        self._progress_bar.pack(side="left", padx=(0, 10))
        self._progress_bar.set(0)
        self._progress_label = ctk.CTkLabel(
            self._progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#AABBCC",
            anchor="w",
        )
        self._progress_label.pack(side="left", fill="x", expand=True)
        self._progress_frame.pack(fill="x", padx=10, pady=(0, 1))
        self._progress_frame.pack_forget()

        self._speaker_map_card = ctk.CTkFrame(self, fg_color="#0D1A2A", corner_radius=6)
        self._speaker_map_title_row = ctk.CTkFrame(self._speaker_map_card, fg_color="transparent")
        self._speaker_map_title_row.pack(fill="x", padx=10, pady=(8, 4))
        self._speaker_map_toggle_btn = ctk.CTkButton(
            self._speaker_map_title_row,
            text="▼ Speaker Mapping (Global)",
            anchor="w",
            fg_color="transparent",
            hover_color="#132334",
            text_color="white",
            border_width=0,
            command=self._toggle_speaker_mapping_panel,
        )
        self._speaker_map_toggle_btn.pack(side="left", fill="x", expand=True)
        self._speaker_map_status = ctk.CTkLabel(
            self._speaker_map_title_row,
            text="No transcript loaded",
            font=ctk.CTkFont(size=11),
            text_color="#7D8FA3",
        )
        self._speaker_map_status.pack(side="left", padx=(10, 0))
        self._speaker_map_btn_row = ctk.CTkFrame(self._speaker_map_card, fg_color="transparent")
        self._speaker_map_btn_row.pack(fill="x", padx=10, pady=(0, 4))
        self._apply_speakers_btn = ctk.CTkButton(
            self._speaker_map_btn_row,
            text="Apply Speaker Names",
            width=120,
            fg_color="#1558C0",
            hover_color="#0F3E8A",
            command=self._apply_progressive_speaker_mapping,
        )
        self._apply_speakers_btn.pack(side="left", padx=(0, 6))
        self._reset_speakers_btn = ctk.CTkButton(
            self._speaker_map_btn_row,
            text="Reset",
            width=90,
            fg_color="#22384F",
            hover_color="#2D4A69",
            command=self._reset_progressive_speaker_mapping,
        )
        self._reset_speakers_btn.pack(side="left", padx=(0, 6))
        self._speaker_hint_label = ctk.CTkLabel(
            self._speaker_map_card,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#7DAACC",
            anchor="w",
            justify="left",
        )
        self._speaker_hint_label.pack(fill="x", padx=10, pady=(0, 4))
        self._speaker_rows_frame = ctk.CTkFrame(self._speaker_map_card, fg_color="transparent")
        self._speaker_rows_frame.pack(fill="x", padx=10, pady=(0, 8))
        self._speaker_map_card.pack(fill="x", padx=14, pady=(0, 6))
        self._speaker_map_card.pack_forget()

        self._bottom_panel = ctk.CTkFrame(self, fg_color="#0F1A24", corner_radius=0)

        player_row = ctk.CTkFrame(self._bottom_panel, fg_color="transparent")
        player_row.pack(fill="x", padx=8, pady=(6, 2))

        self._play_btn = ctk.CTkButton(player_row, text="Play", width=72, command=self._play_audio)
        self._play_btn.pack(side="left", padx=(0, 4))

        self._pause_btn = ctk.CTkButton(player_row, text="Pause", width=72, command=self._pause_audio)
        self._pause_btn.pack(side="left", padx=(0, 4))

        self._stop_btn = ctk.CTkButton(player_row, text="Stop", width=72, command=self._stop_audio)
        self._stop_btn.pack(side="left", padx=(0, 8))

        # ── Speed control ────────────────────────────────────────────────────
        self._speed_down_btn = ctk.CTkButton(
            player_row, text="◀", width=24, command=self._speed_down,
            font=ctk.CTkFont(size=13),
        )
        self._speed_down_btn.pack(side="left", padx=(0, 2))

        self._speed_label = ctk.CTkLabel(
            player_row, text="1.0×", width=38,
            font=ctk.CTkFont(size=13), anchor="center",
        )
        self._speed_label.pack(side="left")

        self._speed_up_btn = ctk.CTkButton(
            player_row, text="▶", width=24, command=self._speed_up,
            font=ctk.CTkFont(size=13),
        )
        self._speed_up_btn.pack(side="left", padx=(2, 8))
        # ────────────────────────────────────────────────────────────────────

        self._skip_gap_btn = ctk.CTkButton(
            player_row, text="⏭ Skip Gap", width=90,
            command=self._skip_to_next_speech,
            font=ctk.CTkFont(size=13),
        )
        self._skip_gap_btn.pack(side="left", padx=(0, 8))

        self._position_label = ctk.CTkLabel(
            player_row,
            text="00:00 / 00:00",
            width=110,
            anchor="w",
            font=ctk.CTkFont(size=13),
        )
        self._position_label.pack(side="left")

        self._audio_label = ctk.CTkLabel(
            player_row,
            text="No audio loaded",
            anchor="w",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self._audio_label.pack(side="left", padx=(10, 10), fill="x", expand=True)

        self._load_audio_btn = ctk.CTkButton(
            player_row,
            text="Load Audio/Video",
            width=140,
            command=self._browse_audio_file,
        )
        self._load_audio_btn.pack(side="right")

        # ── Waveform scrubber ────────────────────────────────────────────────
        self._waveform_frame = ctk.CTkFrame(self._bottom_panel, fg_color="#0D1420", corner_radius=4)
        self._waveform_frame.pack(fill="x", padx=8, pady=(0, 2))
        self._waveform_frame.pack_forget()   # hidden until audio is loaded

        self._waveform_canvas = tk.Canvas(
            self._waveform_frame,
            height=48,
            bg="#0D1420",
            highlightthickness=0,
            cursor="hand2",
        )
        self._waveform_canvas.pack(fill="x", padx=2, pady=2)
        self._waveform_canvas.bind("<Button-1>", self._on_waveform_click)
        self._waveform_canvas.bind("<Configure>", self._on_waveform_resize)
        # ────────────────────────────────────────────────────────────────────

        shortcut_row = ctk.CTkFrame(self._bottom_panel, fg_color="transparent", height=24)
        shortcut_row.pack(fill="x", padx=8, pady=(0, 2))
        ctk.CTkLabel(
            shortcut_row,
            text="Double-click word = seek + play  ·  Single click = stop  ·  Space = play/pause  ·  Esc = stop  ·  ← → = ±2s",
            font=ctk.CTkFont(size=11),
            text_color="#445566",
            anchor="w",
        ).pack(side="left")

        self._speaker_toggle_btn = ctk.CTkButton(
            self._bottom_panel,
            text="+ Insert Speaker Break",
            height=24,
            fg_color="transparent",
            hover_color="#1A2A3A",
            font=ctk.CTkFont(size=11),
            anchor="w",
            command=self._toggle_speaker_tools,
        )
        self._speaker_toggle_btn.pack(fill="x", padx=8, pady=(0, 2))

        conf_row = ctk.CTkFrame(self._bottom_panel, fg_color="transparent")

        self._conf_label = ctk.CTkLabel(
            conf_row,
            text="Confidence: no word-level data loaded",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._conf_label.pack(side="left")

        self._highlight_toggle = ctk.CTkCheckBox(
            conf_row,
            text="Highlight",
            variable=self._highlight_var,
            command=self._refresh_confidence_highlights,
            font=ctk.CTkFont(size=11),
        )
        self._highlight_toggle.pack(side="right")

        self._confirm_btn = ctk.CTkButton(
            conf_row,
            text="Confirm",
            width=88,
            fg_color="#1A6B3A",
            hover_color="#145230",
            command=self._confirm_current_word,
        )
        self._confirm_btn.pack(side="right", padx=(0, 6))

        self._next_flagged_btn = ctk.CTkButton(
            conf_row,
            text="Next →",
            width=78,
            fg_color="transparent",
            border_width=1,
            border_color="#334",
            text_color="#8ab",
            command=self._go_to_next_flagged,
        )
        self._next_flagged_btn.pack(side="right", padx=(0, 6))

        self._prev_flagged_btn = ctk.CTkButton(
            conf_row,
            text="← Prev",
            width=78,
            fg_color="transparent",
            border_width=1,
            border_color="#334",
            text_color="#8ab",
            command=self._go_to_previous_flagged,
        )
        self._prev_flagged_btn.pack(side="right", padx=(0, 6))

        self._low_conf_pady = (0, 3)
        self._conf_toggle_btn = ctk.CTkButton(
            self._bottom_panel,
            text="▶ 0 low-confidence words",
            height=24,
            fg_color="transparent",
            hover_color="#1A2A3A",
            font=ctk.CTkFont(size=11),
            anchor="w",
            command=self._toggle_conf_list,
        )
        self._conf_toggle_btn.pack(fill="x", padx=8, pady=(0, 2))

        self._low_conf_frame = ctk.CTkFrame(self._bottom_panel, fg_color="#101826")

        low_conf_header = ctk.CTkFrame(self._low_conf_frame, fg_color="transparent")
        low_conf_header.pack(fill="x", padx=8, pady=(6, 2))

        self._low_conf_title = ctk.CTkLabel(
            low_conf_header,
            text="Low-Confidence Review: no transcript loaded",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#CCAA44",
            anchor="w",
        )
        self._low_conf_title.pack(side="left")

        self._low_conf_box = ctk.CTkTextbox(
            self._low_conf_frame,
            height=80,
            font=ctk.CTkFont(family="Courier New", size=12),
            state="disabled",
        )
        self._low_conf_box.pack(fill="x", padx=8, pady=(0, 4))

        # ── Find & Replace bar (hidden until activated) ─────────────────────
        self._fnr_bar = ctk.CTkFrame(self, fg_color="#0D1A2A", corner_radius=0)
        # Not packed yet — shown by _toggle_find_replace()

        fnr_inner = ctk.CTkFrame(self._fnr_bar, fg_color="transparent")
        fnr_inner.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            fnr_inner, text="Find:", width=46, anchor="e",
            font=ctk.CTkFont(size=13), text_color="#7DAACC"
        ).pack(side="left")
        self._find_entry = ctk.CTkEntry(fnr_inner, width=220, placeholder_text="Search text…")
        self._find_entry.pack(side="left", padx=(6, 12))

        ctk.CTkLabel(
            fnr_inner, text="Replace:", width=58, anchor="e",
            font=ctk.CTkFont(size=13), text_color="#7DAACC"
        ).pack(side="left")
        self._replace_entry = ctk.CTkEntry(fnr_inner, width=220, placeholder_text="Replacement…")
        self._replace_entry.pack(side="left", padx=(6, 12))

        self._fnr_case_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            fnr_inner, text="Match case", variable=self._fnr_case_var,
            font=ctk.CTkFont(size=13), width=100
        ).pack(side="left", padx=(0, 12))

        self._fnr_replace_one_btn = ctk.CTkButton(
            fnr_inner, text="Replace Next", width=110,
            fg_color="#1558C0", hover_color="#0F3E8A",
            command=self._fnr_replace_next,
        )
        self._fnr_replace_one_btn.pack(side="left", padx=(0, 6))

        self._fnr_replace_all_btn = ctk.CTkButton(
            fnr_inner, text="Replace All", width=100,
            fg_color="#B8860B", hover_color="#9A7209",
            font=ctk.CTkFont(weight="bold"),
            command=self._fnr_replace_all,
        )
        self._fnr_replace_all_btn.pack(side="left", padx=(0, 12))

        self._fnr_match_label = ctk.CTkLabel(
            fnr_inner, text="", width=140,
            font=ctk.CTkFont(size=13), text_color="#7DAACC", anchor="w",
        )
        self._fnr_match_label.pack(side="left")

        ctk.CTkButton(
            fnr_inner, text="✕", width=28, height=28,
            fg_color="transparent", border_width=1, border_color="#334455",
            text_color="#AA6666", hover_color="#2A0A0A",
            command=self._close_find_replace,
        ).pack(side="right")

        self._find_entry.bind("<KeyRelease>", lambda _: self._fnr_update_count())
        self._find_entry.bind("<Return>", lambda _: self._fnr_replace_next())
        self._replace_entry.bind("<Return>", lambda _: self._fnr_replace_all())

        self._fnr_current_pos = "1.0"

        # ── Speaker break toolbar (always visible) ───────────────────────────
        self._edit_toolbar = ctk.CTkFrame(self._bottom_panel, fg_color="#0D1B2A", corner_radius=4)

        edit_tb_inner = ctk.CTkFrame(self._edit_toolbar, fg_color="transparent")
        edit_tb_inner.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(
            edit_tb_inner, text="Speaker label:",
            font=ctk.CTkFont(size=13), text_color="#7DAACC"
        ).pack(side="left")

        self._speaker_break_entry = ctk.CTkEntry(
            edit_tb_inner, width=120, placeholder_text="e.g. Speaker 4"
        )
        self._speaker_break_entry.pack(side="left", padx=(6, 8))

        ctk.CTkButton(
            edit_tb_inner,
            text="↵  Insert Speaker Break",
            width=180,
            fg_color="#1558C0",
            hover_color="#0F3E8A",
            command=self._insert_speaker_break,
        ).pack(side="left")

        ctk.CTkLabel(
            edit_tb_inner,
            text="← positions cursor before new speaker turn",
            font=ctk.CTkFont(size=13),
            text_color="#445566",
        ).pack(side="left", padx=(12, 0))

        conf_row.pack(fill="x", padx=8, pady=(0, 2))

        self._log_box = ctk.CTkTextbox(
            self._bottom_panel,
            height=24,
            font=ctk.CTkFont(family="Courier New", size=13),
            state="disabled",
        )
        self._log_box.pack(fill="x", padx=8, pady=(0, 3))

        action_row = ctk.CTkFrame(self._bottom_panel, fg_color="transparent")
        action_row.pack(fill="x", padx=8, pady=(0, 4))

        self._open_folder_btn = ctk.CTkButton(
            action_row,
            text="Open Output Folder",
            width=150,
            state="disabled",
            command=self._open_output_folder,
        )
        self._open_folder_btn.pack(side="left", padx=(0, 6))

        self._open_transcript_btn = ctk.CTkButton(
            action_row,
            text="Open Transcript",
            width=130,
            state="disabled",
            command=self._open_transcript_file,
        )
        self._open_transcript_btn.pack(side="left", padx=(0, 6))

        self._export_review_btn = ctk.CTkButton(
            action_row,
            text="Export Review DOCX",
            width=150,
            state="disabled",
            command=self._export_review_docx,
        )
        self._export_review_btn.pack(side="left", padx=(0, 6))

        self._open_review_btn = ctk.CTkButton(
            action_row,
            text="Open Review DOCX",
            width=140,
            state="disabled",
            command=self._open_review_docx,
        )
        self._open_review_btn.pack(side="left")

        self._textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier New", size=13),
            wrap="word",
            state="normal",
            undo=True,
        )
        self._textbox.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self._textbox._textbox.bind("<<Modified>>", self._on_textbox_modified)
        self._textbox._textbox.bind("<Button-1>", self._on_textbox_click)
        self._textbox._textbox.bind("<Double-Button-1>", self._on_textbox_double_click)
        self._textbox._textbox.bind("<Control-Button-1>", self._on_ctrl_click_seek)
        self._textbox._textbox.bind("<Key>", self._on_key_press_in_transcript)
        self._textbox._textbox.bind("<FocusOut>", self._on_transcript_focus_out)
        self._textbox._textbox.bind("<FocusIn>", self._on_transcript_focus_in)
        self._textbox._textbox.bind("<space>", self._on_space_play_pause)
        self._textbox._textbox.bind("<Escape>", self._on_escape_stop)
        self._textbox._textbox.bind("<Left>", self._on_skip_back)
        self._textbox._textbox.bind("<Right>", self._on_skip_forward)
        self._textbox._textbox.bind("<Control-z>", lambda _: self._textbox._textbox.edit_undo() or "break")
        self._textbox._textbox.bind("<Control-Z>", lambda _: self._textbox._textbox.edit_undo() or "break")
        self._textbox._textbox.bind("<Control-y>", lambda _: self._textbox._textbox.edit_redo() or "break")
        self.winfo_toplevel().bind("<Control-h>", lambda _: self._toggle_find_replace())
        self.winfo_toplevel().bind("<Escape>", lambda _: self._close_find_replace())
        self._textbox._textbox.bind("<Button-3>", self._show_context_menu)
        self._textbox.bind("<Button-3>", self._show_context_menu, add=True)

        self._panel_toggle_btn = ctk.CTkButton(
            self,
            text="▶  Audio & Review Tools",
            height=28,
            fg_color="#1A2A3A",
            hover_color="#1E3A5F",
            font=ctk.CTkFont(size=12),
            anchor="w",
            command=self._toggle_bottom_panel,
        )
        self._panel_toggle_btn.pack(fill="x", padx=0, pady=0, side="bottom")

    def _init_player(self):
        def worker():
            player = VLCPlayer()
            self.after(0, lambda: self._on_player_ready(player))

        threading.Thread(target=worker, daemon=True).start()

    def _on_player_ready(self, player: VLCPlayer):
        self._player = player
        self._player_ready = True
        if player.is_available:
            self._audio_label.configure(text="VLC ready", text_color="#7DD8E8")
            self._update_audio_state("Audio ready", "#7DD8E8")
        else:
            self._audio_label.configure(
                text="VLC unavailable (install python-vlc to enable playback)",
                text_color="#CC8844",
            )
            self._update_audio_state("Audio unavailable", "#CC8844")
        if self._audio_path:
            self.set_audio_file(self._audio_path)

    def append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")
        self._update_progress_from_message(msg)

    def set_status(self, text: str, color: str = "gray"):
        self._status_label.configure(text=text, text_color=color)
        self._update_progress_from_message(text)

    @staticmethod
    def _normalize_confidence_token(token: str) -> str:
        return token.strip().lower().rstrip(".,;:?!")

    def _is_confidence_stop_word(self, token: str) -> bool:
        return self._normalize_confidence_token(token) in _CONFIDENCE_STOP_WORDS

    def _show_progress(self) -> None:
        if not self._progress_frame.winfo_ismapped():
            self._progress_frame.pack(fill="x", padx=14, pady=(0, 2), before=self._textbox)

    def _hide_progress(self) -> None:
        if self._progress_frame.winfo_ismapped():
            self._progress_frame.pack_forget()

    def _update_progress_from_message(self, message: str) -> None:
        if not self._transcription_running:
            return
        if not message:
            return
        match = _TRANSCRIPTION_PROGRESS_RE.search(message)
        if match:
            chunk_num = int(match.group(1))
            total_chunks = max(1, int(match.group(2)))
            percent = max(0.0, min(1.0, chunk_num / total_chunks))
            self._show_progress()
            self._progress_bar.set(percent)
            self._progress_label.configure(
                text=f"Transcribing... chunk {chunk_num} of {total_chunks} ({int(percent * 100)}%)"
            )
            return
        lowered = message.lower()
        if any(token in lowered for token in ("transcription started", "processing audio", "splitting into chunks", "normalizing audio", "validating audio")):
            self._show_progress()
            if "processing audio" in lowered:
                self._progress_bar.set(0.05)
            self._progress_label.configure(text=message)
        elif "transcription complete" in lowered or "complete ✓" in lowered:
            self._progress_bar.set(1.0)
            self._progress_label.configure(text=message)
        elif "failed" in lowered or lowered.startswith("error:"):
            self._progress_label.configure(text=message)

    def _iter_pending_confidence_items(self):
        for idx, item in enumerate(self._word_map):
            if item["char_start"] < 0:
                continue
            if self.review_state.get(idx, "pending") != "pending":
                continue
            if self._is_confidence_stop_word(str(item.get("word", ""))):
                continue
            confidence = float(item.get("confidence", 1.0) or 1.0)
            yield idx, item, confidence

    def _word_item_at_event(self, event):
        if not self._word_map:
            return None, -1
        try:
            click_index = self._textbox._textbox.index(f"@{event.x},{event.y}")
        except Exception:
            return None, -1
        char_offset = self._index_to_char_offset(click_index)
        best = None
        best_idx = -1
        best_dist = float("inf")
        for idx, item in enumerate(self._word_map):
            if item["char_start"] < 0:
                continue
            if item["char_start"] <= char_offset <= item["char_end"]:
                return item, idx
            dist = min(abs(char_offset - item["char_start"]), abs(char_offset - item["char_end"]))
            if dist < best_dist:
                best_dist = dist
                best = item
                best_idx = idx
        return best, best_idx

    def _flash_word_item(self, item: dict) -> None:
        if item["char_start"] < 0:
            return
        widget = self._textbox._textbox
        widget.tag_config("seek_flash", background="#355C7D", foreground="white")
        start_idx = f"1.0+{item['char_start']}c"
        end_idx = f"1.0+{item['char_end']}c"
        widget.tag_remove("seek_flash", "1.0", "end")
        widget.tag_add("seek_flash", start_idx, end_idx)
        self.after(400, lambda: widget.tag_remove("seek_flash", "1.0", "end"))

    def _seek_audio(self, timestamp: float) -> bool:
        if self._player and self._player.jump_to(timestamp):
            self._schedule_position_update()
            self._start_sync_timer()
            return True
        return False

    def _is_audio_playing(self) -> bool:
        return bool(self._player and self._player.is_loaded and self._player.is_playing)

    def _show_context_menu(self, event):
        widget = self._textbox._textbox
        selected = ""
        try:
            selected = widget.get("sel.first", "sel.last").strip()
        except Exception:
            selected = ""

        clicked_item, _ = self._word_item_at_event(event)
        menu = tk.Menu(widget, tearoff=0)

        target_text = selected or (str(clicked_item.get("word", "")).strip() if clicked_item else "")
        if target_text:
            menu.add_command(
                label=f'Correct "{target_text[:30]}"...',
                command=lambda text=target_text: self._open_correction_dialog(text),
            )
            menu.add_separator()

        if clicked_item:
            item_copy = dict(clicked_item)
            word = str(clicked_item.get("word", "")).strip()
            menu.add_command(
                label=f'Replace "{word}"…',
                command=lambda: self._ctx_replace_one(item_copy),
            )
            menu.add_command(
                label=f'Replace ALL "{word}"…',
                command=lambda: self._ctx_replace_all(word),
            )
            menu.add_command(
                label=f'Seek audio → "{word}"',
                command=lambda: self._on_word_clicked(float(item_copy["start"])),
            )
            menu.add_separator()

        menu.add_command(label="Find & Replace...", command=self._toggle_find_replace)
        menu.add_command(label="Copy", command=lambda: self._textbox._textbox.event_generate("<<Copy>>"))
        menu.add_separator()
        menu.add_command(label="Run Corrections", command=self._run_corrections_pipeline)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _open_correction_dialog(self, selected_text: str) -> None:
        self._toggle_find_replace(prefill=selected_text)

    def set_transcription_running(self):
        self._transcription_running = True
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self.set_status("Transcription running…", "white")
        self._progress_bar.set(0)
        self._progress_label.configure(text="Processing audio...")
        self._show_progress()
        self._open_folder_btn.configure(state="disabled")
        self._open_transcript_btn.configure(state="disabled")
        self._export_review_btn.configure(state="disabled")
        self._open_review_btn.configure(state="disabled")
        self._copy_btn.configure(state="disabled")
        self._copy_debug_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._run_corrections_btn.configure(state="disabled")
        self._ai_correct_btn.configure(state="disabled")
        if self._format_btn is not None:
            self._format_btn.configure(state="disabled")
        self._path_label.configure(text="Processing…", text_color="gray")
        self._update_audio_state("Audio stopped", "#445566")

    def set_transcription_complete(self, transcript_path: str, folder_path: str):
        self._transcription_running = False
        self._current_folder_path = folder_path
        self.set_status("✓ Transcription complete", "#44FF44")
        self._hide_progress()
        self._open_folder_btn.configure(state="normal")
        self._open_transcript_btn.configure(state="normal")
        self.load_transcript(transcript_path)
        self._ensure_bottom_panel_open()
        try:
            self.winfo_toplevel().corrections_tab.set_source(transcript_path)
        except AttributeError:
            pass

    def set_transcription_failed(self, error_msg: str):
        self._transcription_running = False
        self.set_status(f"Failed: {error_msg[:80]}", "#FF4444")
        self._hide_progress()

    def load_transcript(self, filepath: str):
        if not filepath or not os.path.isfile(filepath):
            return
        try:
            content = self._read_transcript(filepath)
            self._case_root, has_case_context = _resolve_case_root_for_transcript(filepath)
            self._current_path = filepath
            self._corrected_path = None
            self._review_docx_path = None
            self.review_state = {}
            self._current_review_idx = -1
            self._open_review_btn.configure(state="disabled")
            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")
            self._textbox.insert("1.0", content)
            self._original_text = content
            self._processed_text = None
            self._canonical_text = content
            self._mapping_source_text = content
            self._textbox.edit_modified(False)
            self._textbox._textbox.edit_modified(False)
            self._textbox._textbox.edit_reset()
            self._edit_mode = False
            self._update_path_label()
            self._copy_btn.configure(state="normal")
            self._copy_debug_btn.configure(state="normal")
            self._save_btn.configure(state="normal")
            self._run_corrections_btn.configure(state="normal")
            self._ai_correct_btn.configure(state="normal")
            if self._format_btn is not None:
                self._format_btn.configure(state="normal")
            self.set_status(
                "Loaded — type to edit · Ctrl+Click seeks playback · Space toggles audio · Ctrl+Z to undo.",
                "gray",
            )
            self._ensure_bottom_panel_open()
            try:
                self.winfo_toplevel().corrections_tab.notify_transcript_loaded(filepath)
            except AttributeError:
                pass
            self._load_progressive_speaker_state(filepath)
            context_text, context_color = _build_transcript_context_status(self._job_config_data)
            self.append_log(context_text)
            if not has_case_context:
                self.append_log("Transcript is outside a detected case folder — speaker persistence is limited.")
                self.set_status("Loaded transcript outside case folder — limited corrections will run.", "#CCAA44")
            else:
                self.set_status(context_text, context_color)
            self._load_low_confidence_words(filepath)
            self._load_word_data(filepath)
        except Exception as exc:
            self._path_label.configure(text=f"Failed to load: {exc}", text_color="#CC4444")

    def _load_progressive_speaker_state(self, filepath: str) -> None:
        self._speaker_entries.clear()
        self._speaker_mapping_dirty = False
        self._selected_speaker_label = None
        resolved_case_root, _ = _resolve_case_root_for_transcript(filepath)
        self._case_root = resolved_case_root
        config_data = load_job_config(self._case_root) if self._case_root else {}
        self._job_config_data = config_data if isinstance(config_data, dict) else {}
        ufm = config_data.get("ufm_fields", {}) if isinstance(config_data, dict) else {}
        self._saved_speaker_map = _normalize_transcript_speaker_map(
            ufm.get("speaker_map", {}) if isinstance(ufm, dict) else {}
        )
        self._speaker_map_suggestion = _normalize_ui_speaker_suggestion(
            config_data.get("speaker_map_suggestion", {}) if isinstance(config_data, dict) else {}
        )
        self._speaker_map_verified = bool(ufm.get("speaker_map_verified", False)) if isinstance(ufm, dict) else False
        self._refresh_speaker_mapping_panel()

    def _refresh_speaker_mapping_panel(self) -> None:
        for widget in self._speaker_rows_frame.winfo_children():
            widget.destroy()
        self._speaker_entries.clear()

        speaker_ids = _extract_speaker_ids(self._mapping_source_text or self._canonical_text)
        if not speaker_ids:
            self._speaker_map_card.pack_forget()
            return

        defaults = _build_progressive_speaker_defaults(
            self._mapping_source_text or self._canonical_text,
            self._saved_speaker_map,
            self._speaker_map_suggestion,
        )
        reference_text = _build_ui_speaker_reference_text(self._speaker_map_suggestion)
        self._speaker_hint_label.configure(
            text=(
                f"NOD reference: {reference_text}"
                if reference_text
                else "Assign names manually to each detected speaker, then apply globally."
            )
        )

        for sid in speaker_ids:
            row = ctk.CTkFrame(self._speaker_rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row,
                text=f"Speaker {sid}:",
                width=100,
                anchor="w",
                font=ctk.CTkFont(weight="bold"),
            ).pack(side="left", padx=(0, 8))
            entry = ctk.CTkEntry(row, width=260, placeholder_text=f"Speaker {sid}")
            entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            default_label = defaults.get(f"Speaker {sid}", "")
            if default_label:
                entry.insert(0, default_label)
            self._speaker_entries[f"Speaker {sid}"] = entry

        self._speaker_map_status.configure(
            text=(
                "Speaker names applied"
                if self._speaker_map_verified
                else ("Updated — click Apply Speaker Names" if self._speaker_mapping_dirty else "Manual mapping")
            ),
            text_color="#44FF44" if self._speaker_map_verified else "#CCAA44",
        )
        self._set_speaker_mapping_panel_expanded(not self._speaker_map_verified)
        self._speaker_map_card.pack(fill="x", padx=14, pady=(0, 6), before=self._textbox)

    def _set_speaker_mapping_panel_expanded(self, expanded: bool) -> None:
        self._speaker_panel_expanded = bool(expanded)
        if hasattr(self, "_speaker_map_toggle_btn"):
            self._speaker_map_toggle_btn.configure(
                text=("▼ Speaker Mapping (Global)" if self._speaker_panel_expanded else "▶ Speaker Mapping (Global)")
            )
        if not hasattr(self, "_speaker_map_card"):
            return
        if self._speaker_panel_expanded:
            self._speaker_map_btn_row.pack(fill="x", padx=10, pady=(0, 4))
            self._speaker_hint_label.pack(fill="x", padx=10, pady=(0, 4))
            self._speaker_rows_frame.pack(fill="x", padx=10, pady=(0, 8))
        else:
            self._speaker_map_btn_row.pack_forget()
            self._speaker_hint_label.pack_forget()
            self._speaker_rows_frame.pack_forget()

    def _toggle_speaker_mapping_panel(self) -> None:
        self._set_speaker_mapping_panel_expanded(not self._speaker_panel_expanded)

    @staticmethod
    def _set_speaker_entry_value(entry: Any, value: str) -> None:
        entry.configure(state="normal")
        if hasattr(entry, "delete") and hasattr(entry, "insert"):
            entry.delete(0, "end")
            entry.insert(0, value)
            return
        if hasattr(entry, "set"):
            entry.set(value)

    def _collect_progressive_speaker_map(self) -> dict[int, str]:
        speaker_map: dict[int, str] = {}
        for original_label, entry in self._speaker_entries.items():
            replacement = " ".join(entry.get().split()).strip()
            if not replacement:
                continue
            try:
                sid = int(original_label.replace("Speaker ", "").strip())
            except ValueError:
                continue
            speaker_map[sid] = replacement
        return speaker_map

    def _persist_progressive_speaker_map(self, speaker_map: dict[int, str], verified: bool) -> None:
        if not self._case_root:
            return
        config_data = load_job_config(self._case_root)
        ufm = dict(config_data.get("ufm_fields", {})) if isinstance(config_data, dict) else {}
        ufm["speaker_map"] = {str(k): v for k, v in speaker_map.items()}
        ufm["speaker_map_verified"] = bool(verified)
        merge_and_save(self._case_root, ufm_fields=ufm)

    def _reset_progressive_speaker_mapping(self) -> None:
        defaults = _build_progressive_speaker_defaults(
            self._mapping_source_text or self._canonical_text,
            self._saved_speaker_map,
            self._speaker_map_suggestion,
        )
        for speaker_label, entry in self._speaker_entries.items():
            self._set_speaker_entry_value(entry, defaults.get(speaker_label, speaker_label))
        self._saved_speaker_map = {}
        self._speaker_map_verified = False
        self._speaker_mapping_dirty = False
        self._persist_progressive_speaker_map({}, verified=False)
        self._apply_text_update(self._mapping_source_text or self._canonical_text)
        self._processed_text = None
        self._speaker_map_status.configure(text="Reset", text_color="#7DD8E8")
        self._set_speaker_mapping_panel_expanded(True)
        self.append_log("Speaker mapping reset to raw speaker labels.")

    def _apply_progressive_speaker_mapping(self) -> None:
        speaker_map = self._collect_progressive_speaker_map()
        if not speaker_map:
            self.set_status("Assign at least one speaker label first.", "#FFAA44")
            return
        self._saved_speaker_map = dict(speaker_map)
        self._speaker_map_verified = True
        self._speaker_mapping_dirty = False
        self._persist_progressive_speaker_map(speaker_map, verified=True)

        remapped_text = _apply_speaker_map_to_text(self._mapping_source_text or self._canonical_text, speaker_map)
        self._apply_text_update(remapped_text)
        self._canonical_text = remapped_text
        self._processed_text = remapped_text
        self._speaker_map_status.configure(text="Applied", text_color="#44FF44")
        self._set_speaker_mapping_panel_expanded(False)
        self.set_status("Speaker names applied.", "#44FF44")
        self.append_log(
            "Speaker names applied: "
            + ", ".join(f"Speaker {sid} → {label}" for sid, label in sorted(speaker_map.items()))
        )

    def _read_transcript(self, filepath: str) -> str:
        if filepath.lower().endswith(".docx"):
            from docx import Document

            doc = Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs)
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    def _load_word_data(self, filepath: str):
        self._word_data_request_id += 1
        request_id = self._word_data_request_id
        self._conf_label.configure(text="Confidence: loading word-level data…", text_color="#9AA3B2")
        self._export_review_btn.configure(state="disabled")

        def worker():
            words = load_words_for_transcript(filepath)
            self.after(0, lambda: self._on_word_data_loaded(request_id, filepath, words))

        threading.Thread(target=worker, daemon=True).start()

    def _load_low_confidence_words(self, filepath: str) -> None:
        low_conf: list[dict] = []
        try:
            from pathlib import Path
            from core.job_config_manager import load_job_config

            case_root = str(Path(filepath).parent.parent)
            job_config = load_job_config(case_root)
            if isinstance(job_config, dict):
                raw_words = job_config.get("low_confidence_words", []) or []
                if isinstance(raw_words, list):
                    low_conf = [item for item in raw_words if isinstance(item, dict)]
        except Exception as exc:
            self.append_log(f"Low-confidence review unavailable: {exc}")
        self._update_low_confidence_panel(low_conf)

    def _update_low_confidence_panel(self, words: list[dict]) -> None:
        filtered_words = [
            item for item in list(words or [])
            if not self._is_confidence_stop_word(str(item.get("word", "") or ""))
        ]
        self._low_confidence_words = filtered_words

        if not self._low_confidence_words:
            if self._low_conf_frame.winfo_ismapped():
                self._low_conf_frame.pack_forget()
            self._conf_list_visible = False
            self._conf_toggle_btn.configure(text="▶  0 low-confidence words")
            self._low_conf_title.configure(
                text="Low-Confidence Review: no transcript loaded",
                text_color="#CCAA44",
            )
            self._low_conf_box._textbox.unbind("<Button-1>")
            return
        if self._conf_list_visible and not self._low_conf_frame.winfo_ismapped():
            self._low_conf_frame.pack(fill="x", padx=8, pady=(0, 2), after=self._conf_toggle_btn)

        self._low_conf_box.configure(state="normal")
        self._low_conf_box.delete("1.0", "end")

        critical_words = [
            item for item in self._low_confidence_words
            if float(item.get("confidence", 0.0) or 0.0) < CONFIDENCE_RED_THRESHOLD
        ]
        amber_words = [
            item for item in self._low_confidence_words
            if CONFIDENCE_RED_THRESHOLD <= float(item.get("confidence", 0.0) or 0.0) < CONFIDENCE_AMBER_THRESHOLD
        ]

        self._low_conf_title.configure(
            text=(
                f"Critical (below 50%): {len(critical_words)} words  |  "
                f"Needs Review (50-75%): {len(amber_words)} words"
            ),
            text_color="#CCAA44",
        )
        lines = [f"Critical (below 50%): {len(critical_words)} words"]
        for item in critical_words[:10]:
            word = str(item.get("word", "") or "")
            confidence = float(item.get("confidence", 0.0) or 0.0)
            start = float(item.get("start", 0.0) or 0.0)
            lines.append(f"{word:20s}  {confidence:.2f}  @ {start:.1f}s")
        if len(critical_words) > 10:
            lines.append(f"... and {len(critical_words) - 10} more critical")
        lines.append("")
        lines.append(f"Needs Review (50-75%): {len(amber_words)} words")
        for item in amber_words[:10]:
            word = str(item.get("word", "") or "")
            confidence = float(item.get("confidence", 0.0) or 0.0)
            start = float(item.get("start", 0.0) or 0.0)
            lines.append(f"{word:20s}  {confidence:.2f}  @ {start:.1f}s")
        if len(amber_words) > 10:
            lines.append(f"... and {len(amber_words) - 10} more needs review")

        self._low_conf_box.insert("1.0", "\n".join(lines))
        self._low_conf_box.configure(state="disabled")
        self._conf_toggle_btn.configure(
            text=f"{'▼' if self._conf_list_visible else '▶'}  {len(self._low_confidence_words)} low-confidence words"
        )

        def _on_panel_click(event, _box=self._low_conf_box, _words=self._low_confidence_words):
            try:
                index = _box._textbox.index(f"@{event.x},{event.y}")
                line_num = int(index.split(".")[0]) - 1
                if 0 <= line_num < len(_words[:20]):
                    start = float(_words[line_num].get("start", 0.0) or 0.0)
                    self._on_word_clicked(start)
            except Exception:
                pass
            return "break"

        self._low_conf_box._textbox.bind("<Button-1>", _on_panel_click)
        self.append_log(f"Loaded {len(self._low_confidence_words)} low-confidence words")

    def _on_word_data_loaded(self, request_id: int, filepath: str, words: list[dict]):
        if request_id != self._word_data_request_id or filepath != self._active_transcript_path():
            return
        self._restore_review_state(words)
        self._words = words
        self._word_timings = list(words)
        if words:
            self._build_word_map(words)
            self._render_with_confidence(words)
            self._export_review_btn.configure(state="normal")
        else:
            self._word_map = []
            self._word_timings = []
            self.review_state = {}
            self._current_review_idx = -1
            self._update_confidence_summary()
            self._export_review_btn.configure(state="disabled")
        self.append_log(f"Loaded {len(words)} timestamped words")

    def _update_confidence_summary(self):
        if not self._words:
            self._conf_label.configure(
                text="Confidence: no word-level data found",
                text_color="#9AA3B2",
            )
            return
        pending_items = list(self._iter_pending_confidence_items())
        critical = sum(1 for _, _, confidence in pending_items if confidence < CONFIDENCE_RED_THRESHOLD)
        amber = sum(
            1
            for _, _, confidence in pending_items
            if CONFIDENCE_RED_THRESHOLD <= confidence < CONFIDENCE_AMBER_THRESHOLD
        )
        flagged_color = COLOR_RED if critical else (COLOR_AMBER if amber else "#44AA44")
        self._conf_label.configure(
            text=(
                f"Review: {len(self._words)} words  |  "
                f"Critical (below 50%): {critical} words  |  "
                f"Needs Review (50-75%): {amber} words"
            ),
            text_color=flagged_color,
        )

    def _render_with_confidence(self, words: list[dict]):
        # DO NOT update the textbox here.
        # The textbox always shows the canonical file content loaded by
        # load_transcript(). Confidence highlighting is applied via tag
        # coloring only — the underlying text is never replaced.
        # Replacing the textbox content with a word-reconstruction would
        # corrupt the file when _save_transcript() is called.
        #
        # Apply confidence tags to the existing text instead.
        self._apply_confidence_tags(words)

    def _build_word_map(self, words: list[dict]) -> None:
        """Build a char-range map from Deepgram words onto the canonical textbox text."""
        self._word_map = []
        self._current_word_idx = -1
        self._current_review_idx = -1
        if not words:
            self._update_confidence_summary()
            return

        content = self._textbox.get("1.0", "end")
        content_lower = content.lower()
        search_pos = 0

        widget = self._textbox._textbox
        for tag_name in widget.tag_names():
            if tag_name.startswith("w"):
                widget.tag_delete(tag_name)

        for word_index, raw in enumerate(words):
            word_text = str(raw.get("word") or raw.get("text") or "").strip()
            if not word_text:
                continue

            word_lower = word_text.lower()
            found_start = -1

            candidate = content_lower.find(word_lower, search_pos)
            while candidate != -1:
                before_ok = (
                    candidate == 0
                    or not content[candidate - 1].isalpha()
                )
                end_pos = candidate + len(word_text)
                after_ok = (
                    end_pos >= len(content)
                    or not content[end_pos].isalpha()
                )
                # Reject single-letter matches immediately followed by "."
                # ("A." / "Q." are structural labels, not spoken words).
                label_false_match = (
                    len(word_text) == 1
                    and end_pos < len(content)
                    and content[end_pos] == "."
                )
                if before_ok and after_ok and not label_false_match:
                    found_start = candidate
                    break
                candidate = content_lower.find(word_lower, candidate + 1)

            if found_start == -1:
                found_start = content_lower.find(word_lower, search_pos)

            if found_start == -1:
                self._word_map.append({
                    "word":       word_text,
                    "start":      float(raw.get("start", 0.0) or 0.0),
                    "end":        float(raw.get("end",   0.0) or 0.0),
                    "confidence": float(raw.get("confidence", 1.0) or 1.0),
                    "char_start": -1,
                    "char_end":   -1,
                    "word_index": word_index,
                })
                continue

            self._word_map.append({
                "word":       word_text,
                "start":      float(raw.get("start", 0.0) or 0.0),
                "end":        float(raw.get("end",   0.0) or 0.0),
                "confidence": float(raw.get("confidence", 1.0) or 1.0),
                "char_start": found_start,
                "char_end":   found_start + len(word_text),
                "word_index": word_index,
            })
            start_tk = f"1.0+{found_start}c"
            end_tk = f"1.0+{found_start + len(word_text)}c"
            widget.tag_add(f"w{word_index}", start_tk, end_tk)
            # Single-char tokens from digit-by-digit cause numbers can false-match
            # inside merged corrected strings and push the sequential search too far.
            if len(word_text) > 1:
                search_pos = found_start + len(word_text)

        widget.tag_config("current_word", background="#0A3A1A", foreground="#44FF88")
        widget.tag_config("conf_low", foreground=COLOR_RED)
        widget.tag_config("conf_mid", foreground=COLOR_AMBER)
        self._apply_confidence_highlights()

        self._update_confidence_summary()

    def _apply_confidence_tags(self, word_list) -> None:
        self._apply_confidence_highlights()

    def _apply_confidence_highlights(self) -> None:
        widget = self._textbox._textbox
        widget.tag_remove("conf_low", "1.0", "end")
        widget.tag_remove("conf_mid", "1.0", "end")
        if not self._highlight_var.get():
            return
        for idx, item, confidence in self._iter_pending_confidence_items():
            start_idx = f"1.0+{item['char_start']}c"
            end_idx = f"1.0+{item['char_end']}c"
            if confidence < CONFIDENCE_RED_THRESHOLD:
                widget.tag_add("conf_low", start_idx, end_idx)
            elif confidence < CONFIDENCE_AMBER_THRESHOLD:
                widget.tag_add("conf_mid", start_idx, end_idx)

    def _refresh_confidence_highlights(self) -> None:
        self._apply_confidence_highlights()

    @staticmethod
    def _review_key(word: dict) -> tuple[float, float]:
        return (
            round(float(word.get("start", 0.0) or 0.0), 3),
            round(float(word.get("end", 0.0) or 0.0), 3),
        )

    def _restore_review_state(self, words: list[dict]) -> None:
        previous = {}
        for idx, word in enumerate(self._words):
            state = self.review_state.get(idx)
            if state in {"confirmed", "corrected"}:
                previous[self._review_key(word)] = state

        self.review_state = {}
        for idx, word in enumerate(words):
            word_text = str(word.get("word") or word.get("text") or "").strip()
            if not word_text:
                continue
            confidence = float(word.get("confidence", 1.0) or 1.0)
            if confidence < CONFIDENCE_AMBER_THRESHOLD and not self._is_confidence_stop_word(word_text):
                self.review_state[idx] = previous.get(self._review_key(word), "pending")

    def get_next_flagged(self, current_idx: int) -> int | None:
        for i in range(current_idx + 1, len(self._words)):
            if self.review_state.get(i) == "pending":
                return i
        return None

    def get_previous_flagged(self, current_idx: int) -> int | None:
        for i in range(current_idx - 1, -1, -1):
            if self.review_state.get(i) == "pending":
                return i
        return None

    def _jump_to_review_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._word_map):
            return
        item = self._word_map[idx]
        self._current_review_idx = idx
        self._on_word_clicked(float(item["start"]))
        if item["char_start"] >= 0:
            self._textbox._textbox.mark_set("insert", f"1.0+{item['char_start']}c")
            self._textbox._textbox.see(f"1.0+{item['char_start']}c")

    def _go_to_next_flagged(self) -> None:
        start_idx = self._current_review_idx if self._current_review_idx >= 0 else -1
        idx = self.get_next_flagged(start_idx)
        if idx is None and start_idx >= 0:
            idx = self.get_next_flagged(-1)
        if idx is None:
            self.set_status("No pending flagged words remain.", "#44AA44")
            return
        self._jump_to_review_index(idx)

    def _go_to_previous_flagged(self) -> None:
        start_idx = self._current_review_idx if self._current_review_idx >= 0 else len(self._words)
        idx = self.get_previous_flagged(start_idx)
        if idx is None and start_idx < len(self._words):
            idx = self.get_previous_flagged(len(self._words))
        if idx is None:
            self.set_status("No pending flagged words remain.", "#44AA44")
            return
        self._jump_to_review_index(idx)

    def confirm_word(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._word_map):
            return
        if self.review_state.get(idx) != "pending":
            return
        self.review_state[idx] = "confirmed"
        self._apply_confidence_highlights()
        self._update_confidence_summary()
        self.set_status(f'Confirmed: "{self._word_map[idx]["word"]}"', "#44FF44")

    def _confirm_current_word(self) -> None:
        if self._current_review_idx >= 0:
            self.confirm_word(self._current_review_idx)
        else:
            self.set_status("Select or navigate to a flagged word first.", "#FFAA44")

    def _find_changed_range(self, old_text: str, new_text: str) -> tuple[int, int]:
        prefix = 0
        old_len = len(old_text)
        new_len = len(new_text)
        while prefix < old_len and prefix < new_len and old_text[prefix] == new_text[prefix]:
            prefix += 1

        old_suffix = old_len
        new_suffix = new_len
        while old_suffix > prefix and new_suffix > prefix and old_text[old_suffix - 1] == new_text[new_suffix - 1]:
            old_suffix -= 1
            new_suffix -= 1

        return prefix, old_suffix

    def _mark_reviewed_range(self, start_char: int, end_char: int, state: str) -> None:
        for idx, item in enumerate(self._word_map):
            char_start = item.get("char_start", -1)
            char_end = item.get("char_end", -1)
            if char_start < 0 or char_end < 0:
                continue
            overlaps = (
                max(char_start, start_char) < min(char_end, end_char)
                or (start_char == end_char and char_start <= start_char <= char_end)
            )
            if overlaps and self.review_state.get(idx) == "pending":
                self.review_state[idx] = state
                self._current_review_idx = idx

    def _browse_transcript_file(self):
        path = filedialog.askopenfilename(
            title="Open Transcript",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Word Documents", "*.docx"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.load_transcript(path)

    def _browse_audio_file(self):
        path = filedialog.askopenfilename(
            title="Load Audio / Video",
            filetypes=[
                ("Media files", "*.mp3 *.mp4 *.wav *.m4a *.mov *.avi *.mkv *.flac"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.set_audio_file(path)

    def set_audio_file(self, audio_path: str):
        self._audio_path = audio_path
        if not audio_path or not os.path.isfile(audio_path):
            self._audio_label.configure(text="Audio file not found", text_color="#CC4444")
            self._update_audio_state("Audio file not found", "#CC4444")
            return

        name = os.path.basename(audio_path)
        if not self._player_ready:
            self._audio_label.configure(text=f"Pending VLC init: {name}", text_color="#7DD8E8")
            self._update_audio_state("Waiting for audio player", "#7DD8E8")
            return
        if not self._player or not self._player.is_available:
            self._audio_label.configure(text=f"Audio unavailable: {name}", text_color="#CC8844")
            self._update_audio_state("Audio unavailable", "#CC8844")
            return

        def worker():
            ok = self._player.load(audio_path)
            self.after(0, lambda: self._on_audio_loaded(audio_path, ok))

        threading.Thread(target=worker, daemon=True).start()

    def _on_audio_loaded(self, audio_path: str, ok: bool):
        if audio_path != self._audio_path:
            return
        if ok:
            self._audio_label.configure(text=os.path.basename(audio_path), text_color="#7DD8E8")
            self._update_audio_state("Audio loaded", "#7DD8E8")
            self._schedule_position_update()
            self._load_waveform(audio_path)
            self._ensure_bottom_panel_open()
        else:
            self._audio_label.configure(text=f"Could not load audio: {os.path.basename(audio_path)}", text_color="#CC4444")
            self._update_audio_state("Audio load failed", "#CC4444")

    def _on_word_clicked(self, start_time: float):
        if self._seek_audio(start_time):
            self.set_status(f"Jumped to {self._format_seconds(start_time)}", "#7DD8E8")

    def _on_key_press_in_transcript(self, event) -> None:
        if event.keysym in (
            "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Super_L", "Super_R",
            "Left", "Right", "Up", "Down",
            "Home", "End", "Prior", "Next",
            "F1", "F2", "F3", "F4", "F5", "F6",
            "F7", "F8", "F9", "F10", "F11", "F12",
        ):
            return
        self._user_is_editing = True
        self._save_edit_position()
        self._reset_edit_idle_timer()

    def _save_edit_position(self) -> None:
        try:
            self._last_edit_position = self._textbox._textbox.index("insert")
        except Exception:
            pass

    def _reset_edit_idle_timer(self) -> None:
        if self._edit_idle_timer_id is not None:
            self.after_cancel(self._edit_idle_timer_id)
        self._edit_idle_timer_id = self.after(3000, self._on_edit_idle)

    def _on_edit_idle(self) -> None:
        self._edit_idle_timer_id = None
        self._user_is_editing = False

    def _on_transcript_focus_out(self, _event) -> None:
        self._save_edit_position()
        self._user_is_editing = False
        if self._edit_idle_timer_id is not None:
            self.after_cancel(self._edit_idle_timer_id)
            self._edit_idle_timer_id = None

    def _on_transcript_focus_in(self, _event) -> None:
        self._user_is_editing = False

    def _restore_edit_position(self, position: str) -> None:
        try:
            self._textbox._textbox.mark_set("insert", position)
        except Exception:
            pass

    def _on_textbox_click(self, event) -> None:
        item, idx = self._word_item_at_event(event)
        if idx >= 0:
            self._current_review_idx = idx
        if self._click_pending_id is not None:
            self.after_cancel(self._click_pending_id)
            self._click_pending_id = None
        self._click_pending_id = self.after(250, self._execute_single_click_stop)

    def _on_textbox_double_click(self, event) -> str:
        if self._click_pending_id is not None:
            self.after_cancel(self._click_pending_id)
            self._click_pending_id = None

        edit_pos = self._last_edit_position if self._user_is_editing else None
        if not self._player or not self._word_timings:
            return

        item, idx = self._word_item_at_event(event)
        if item and idx >= 0:
            self._current_review_idx = idx
            if self._seek_audio(float(item["start"])):
                self._flash_word_item(item)
                self._play_audio()
                if edit_pos is not None:
                    self.after(10, lambda pos=edit_pos: self._restore_edit_position(pos))
                return "break"

        try:
            click_index = self._textbox._textbox.index(f"@{event.x},{event.y}")
        except Exception:
            return

        result = self._seek_to_nearest_word(click_index)
        if edit_pos is not None:
            self.after(10, lambda pos=edit_pos: self._restore_edit_position(pos))
        return result

    def _execute_single_click_stop(self) -> None:
        self._click_pending_id = None
        if self._is_audio_playing():
            self._stop_audio()
            self._save_edit_position()

    def _seek_to_nearest_word(self, text_index: str):
        try:
            tags = self._textbox._textbox.tag_names(text_index)
            word_tag = next((tag for tag in tags if tag.startswith("w")), None)
            if not word_tag:
                return
            word_index = int(word_tag[1:])
            if word_index >= len(self._word_timings):
                return
            item = self._word_map[word_index] if word_index < len(self._word_map) else None
            start_time = float(self._word_timings[word_index].get("start", 0.0) or 0.0)
            if self._seek_audio(start_time):
                if item:
                    self._flash_word_item(item)
                self._play_audio()
                return "break"
        except Exception:
            return

    def _on_ctrl_click_seek(self, event) -> str:
        edit_pos = self._last_edit_position if self._user_is_editing else None
        item, idx = self._word_item_at_event(event)
        if not item:
            return "break"
        if idx >= 0:
            self._current_review_idx = idx
        if self._seek_audio(float(item["start"])):
            self._flash_word_item(item)
            self._play_audio()
            if edit_pos is not None:
                self.after(10, lambda pos=edit_pos: self._restore_edit_position(pos))
        return "break"

    def _on_space_play_pause(self, _event) -> str:
        if not self._player:
            return "break"
        if self._is_audio_playing():
            self._pause_audio()
        else:
            self._play_audio()
        return "break"

    def _on_escape_stop(self, _event) -> str:
        self._stop_audio()
        return "break"

    def _on_skip_back(self, _event) -> str:
        if self._player and self._player.is_loaded:
            target = max(0.0, self._player.position_seconds - 2.0)
            if self._seek_audio(target):
                self._schedule_position_update()
        return "break"

    def _on_skip_forward(self, _event) -> str:
        if self._player and self._player.is_loaded:
            target = max(0.0, self._player.position_seconds + 2.0)
            if self._seek_audio(target):
                self._schedule_position_update()
        return "break"

    def _show_word_correction_popup(self, click_x: int, click_y: int) -> None:
        """Locate the word under the click and open a correction popup near it."""
        try:
            click_index = self._textbox._textbox.index(f"@{click_x},{click_y}")
        except Exception:
            return

        char_offset = self._index_to_char_offset(click_index)

        target = None
        target_idx = -1
        for i, item in enumerate(self._word_map):
            if item["char_start"] < 0:
                continue
            if item["char_start"] <= char_offset <= item["char_end"]:
                target = item
                target_idx = i
                break

        if target is None:
            return

        was_playing = bool(self._player and self._player.is_playing)
        if was_playing:
            self._player.pause()
            self._stop_sync_timer()

        popup = ctk.CTkToplevel(self)
        popup.title("Correct Word")
        popup.geometry("320x130")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        popup.grab_set()

        try:
            root = self.winfo_toplevel()
            abs_x = root.winfo_x() + self._textbox.winfo_rootx() - root.winfo_rootx() + click_x
            abs_y = root.winfo_y() + self._textbox.winfo_rooty() - root.winfo_rooty() + click_y + 30
            popup.geometry(f"320x130+{abs_x}+{abs_y}")
        except Exception:
            pass

        ctk.CTkLabel(
            popup,
            text=f'Correct:  "{target["word"]}"',
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).pack(fill="x", pady=(14, 6), padx=16)

        entry_var = ctk.StringVar(value=target["word"])
        entry = ctk.CTkEntry(popup, textvariable=entry_var, width=288)
        entry.pack(pady=(0, 8), padx=16)
        entry.select_range(0, "end")
        entry.focus_set()

        def apply(new_word: str | None = None) -> None:
            val = (new_word or entry_var.get()).strip()
            popup.grab_release()
            popup.destroy()
            if val and val != target["word"]:
                self._apply_word_correction(target_idx, target, val)
            if was_playing:
                self._play_audio()

        def cancel() -> None:
            popup.grab_release()
            popup.destroy()
            if was_playing:
                self._play_audio()

        entry.bind("<Return>", lambda _e: apply())
        entry.bind("<Escape>", lambda _e: cancel())
        popup.protocol("WM_DELETE_WINDOW", cancel)

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkButton(btn_row, text="Apply", width=134, command=apply).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="Cancel", width=134,
            fg_color="transparent", border_width=1, border_color="#445",
            text_color="#8ab", command=cancel,
        ).pack(side="left")

    def _apply_word_correction(self, target_idx: int, target: dict, new_word: str) -> None:
        """Replace a word in the textbox and update the word_map accordingly."""
        old_word = target["word"]
        old_len = target["char_end"] - target["char_start"]
        new_len = len(new_word)
        delta = new_len - old_len

        inner = self._textbox._textbox
        inner.config(state="normal")
        inner.delete(f"1.0+{target['char_start']}c", f"1.0+{target['char_end']}c")
        inner.insert(f"1.0+{target['char_start']}c", new_word)

        # Update this word's map entry
        self._word_map[target_idx]["word"] = new_word
        self._word_map[target_idx]["char_end"] = target["char_start"] + new_len
        self._word_map[target_idx]["confidence"] = 1.0
        self.review_state[target_idx] = "corrected"
        self._current_review_idx = target_idx

        # Shift all subsequent entries
        for j in range(target_idx + 1, len(self._word_map)):
            if self._word_map[j]["char_start"] >= 0:
                self._word_map[j]["char_start"] += delta
                self._word_map[j]["char_end"] += delta

        self._canonical_text = self._textbox.get("1.0", "end-1c")
        self._apply_confidence_highlights()
        self._update_confidence_summary()
        self.set_status(f'Corrected: "{old_word}"  →  "{new_word}"', "#44FF44")

    def _replace_word_dialog(self, item: dict) -> None:
        """Replace a single word occurrence via a small modal dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Replace Word")
        dialog.geometry("420x140")
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=f'Replace  "{item["word"]}"  with:', anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )
        entry = ctk.CTkEntry(dialog, width=380)
        entry.insert(0, item["word"])
        entry.pack(padx=16, pady=(0, 10))
        entry.select_range(0, "end")
        entry.focus()

        def _do_replace():
            new_text = entry.get().strip()
            if not new_text:
                dialog.destroy()
                return
            content = self._canonical_text or self._textbox.get("1.0", "end-1c")
            updated = content[: item["char_start"]] + new_text + content[item["char_end"]:]
            self._apply_text_update(updated, mark_reviewed=True)
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkButton(btn_row, text="Replace", width=100, command=_do_replace).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Cancel", width=80, fg_color="transparent",
            border_width=1, command=dialog.destroy
        ).pack(side="left", padx=(8, 0))
        entry.bind("<Return>", lambda _: _do_replace())

    def _ctx_replace_one(self, item: dict) -> None:
        """Replace a single word instance from the right-click context menu."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Replace Word")
        dialog.geometry("440x150")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()

        ctk.CTkLabel(
            dialog, text=f'Replace  "{item["word"]}"  with:',
            anchor="w", font=ctk.CTkFont(size=12),
        ).pack(fill="x", padx=16, pady=(16, 4))

        entry = ctk.CTkEntry(dialog, width=400)
        entry.insert(0, item["word"])
        entry.select_range(0, "end")
        entry.pack(padx=16, pady=(0, 12))
        entry.focus()

        def _apply():
            new_text = entry.get()
            # If unchanged, just close — do not re-render or leave selection
            if new_text == item["word"]:
                self._textbox._textbox.tag_remove("sel", "1.0", "end")
                dialog.destroy()
                return
            if new_text == "":
                dialog.destroy()
                return
            content = self._canonical_text or self._textbox.get("1.0", "end-1c")
            cs = item["char_start"]
            ce = item["char_end"]
            updated = content[:cs] + new_text + content[ce:]
            self._apply_text_update(updated, mark_reviewed=True)
            self.append_log(f'Replaced "{item["word"]}" → "{new_text}" (single instance)')
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16)
        ctk.CTkButton(
            btn_row, text="Replace", width=100,
            fg_color="#1558C0", command=_apply
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Cancel", width=80,
            fg_color="transparent", border_width=1,
            command=dialog.destroy
        ).pack(side="left", padx=(8, 0))
        entry.bind("<Return>", lambda _: _apply())
        entry.bind("<Escape>", lambda _: dialog.destroy())

    def _replace_all_dialog(self, word: str) -> None:
        """Find and replace ALL occurrences of a word in the transcript."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Replace All")
        dialog.geometry("460x180")
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Find:", anchor="w").pack(fill="x", padx=16, pady=(14, 2))
        find_entry = ctk.CTkEntry(dialog, width=420)
        find_entry.insert(0, word)
        find_entry.pack(padx=16, pady=(0, 6))

        ctk.CTkLabel(dialog, text="Replace with:", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        replace_entry = ctk.CTkEntry(dialog, width=420)
        replace_entry.pack(padx=16, pady=(0, 10))
        replace_entry.focus()

        def _do_replace_all():
            find_text = find_entry.get().strip()
            replace_text = replace_entry.get().strip()
            if not find_text:
                dialog.destroy()
                return
            content = self._canonical_text or self._textbox.get("1.0", "end-1c")
            import re as _re
            pattern = _re.compile(_re.escape(find_text), _re.IGNORECASE)
            count = len(pattern.findall(content))
            updated = pattern.sub(replace_text, content)
            self._apply_text_update(updated, mark_reviewed=True)
            self.append_log(
                f'Replace All: "{find_text}" → "{replace_text}"  ({count} replacement{"s" if count != 1 else ""})'
            )
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16)
        ctk.CTkButton(btn_row, text="Replace All", width=120, command=_do_replace_all).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Cancel", width=80, fg_color="transparent",
            border_width=1, command=dialog.destroy
        ).pack(side="left", padx=(8, 0))
        replace_entry.bind("<Return>", lambda _: _do_replace_all())

    def _ctx_replace_all(self, word: str) -> None:
        """Replace all instances of a word from the right-click context menu."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Replace All")
        dialog.geometry("440x190")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()

        ctk.CTkLabel(
            dialog, text="Find:", anchor="w",
            font=ctk.CTkFont(size=12)
        ).pack(fill="x", padx=16, pady=(16, 2))
        find_entry = ctk.CTkEntry(dialog, width=400)
        find_entry.insert(0, word)
        find_entry.pack(padx=16, pady=(0, 8))

        ctk.CTkLabel(
            dialog, text="Replace with:", anchor="w",
            font=ctk.CTkFont(size=12)
        ).pack(fill="x", padx=16, pady=(0, 2))
        replace_entry = ctk.CTkEntry(dialog, width=400)
        replace_entry.pack(padx=16, pady=(0, 12))
        replace_entry.focus()

        def _apply():
            find_text = find_entry.get().strip()
            replace_text = replace_entry.get()
            if not find_text:
                dialog.destroy()
                return
            import re as _re
            content = self._canonical_text or self._textbox.get("1.0", "end-1c")
            pattern = _re.compile(_re.escape(find_text), _re.IGNORECASE)
            count = len(pattern.findall(content))
            if count == 0:
                self.set_status(f'No instances of "{find_text}" found.', "#CC4444")
                dialog.destroy()
                return
            updated = pattern.sub(replace_text, content)
            self._apply_text_update(updated, mark_reviewed=True)
            self.append_log(
                f'Replace All: "{find_text}" → "{replace_text}"  '
                f'({count} replacement{"s" if count != 1 else ""})'
            )
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16)
        ctk.CTkButton(
            btn_row, text="Replace All", width=110,
            fg_color="#B8860B", hover_color="#9A7209",
            font=ctk.CTkFont(weight="bold"),
            command=_apply
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Cancel", width=80,
            fg_color="transparent", border_width=1,
            command=dialog.destroy
        ).pack(side="left", padx=(8, 0))
        replace_entry.bind("<Return>", lambda _: _apply())
        replace_entry.bind("<Escape>", lambda _: dialog.destroy())

    def _open_find_replace_dialog(self) -> None:
        """Open Replace All with an empty find field."""
        self._replace_all_dialog("")

    def _apply_text_update(self, updated_content: str, mark_reviewed: bool = False) -> None:
        """Apply a text change to both the textbox and canonical text, then rebuild word map."""
        old_content = self._canonical_text or self._textbox.get("1.0", "end-1c")
        if mark_reviewed:
            start_char, end_char = self._find_changed_range(old_content, updated_content)
            self._mark_reviewed_range(start_char, end_char, "corrected")
        self._canonical_text = updated_content

        # Preserve cursor position and scroll fraction across the full
        # delete/re-insert so the viewport stays where the user is working.
        widget = self._textbox._textbox
        try:
            cursor_pos = widget.index("insert")
            yview_frac = widget.yview()[0]
        except Exception:
            cursor_pos = "1.0"
            yview_frac = 0.0

        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", updated_content)

        try:
            widget.mark_set("insert", cursor_pos)
            widget.yview_moveto(yview_frac)
        except Exception:
            pass

        if self._words:
            self._build_word_map(self._words)
        else:
            self._word_map = []

        # Do NOT clear waveform here — the audio file has not changed, only
        # the text. Clearing waveform_peaks breaks the audio sync playhead.
        # Waveform clearing belongs only in set_audio_file() / load_transcript().

        # Clear any lingering text selection.
        widget.tag_remove("sel", "1.0", "end")
        self.set_status("Change applied — click Save to write to disk.", "#FFCC44")

    # ── Find & Replace ────────────────────────────────────────────────────

    def _toggle_find_replace(self, prefill: str | None = None) -> None:
        """Show or hide the Find & Replace bar."""
        if self._fnr_bar.winfo_ismapped():
            if prefill is None:
                self._close_find_replace()
                return
        else:
            self._fnr_bar.pack(fill="x", padx=0, pady=0, before=self._textbox)
            self._fnr_toggle_btn.configure(
                fg_color="#1558C0", border_color="#1558C0", text_color="white"
            )

        self._find_entry.focus()
        self._find_entry.select_range(0, "end")
        if prefill is not None:
            self._find_entry.delete(0, "end")
            self._find_entry.insert(0, prefill)
            self._find_entry.select_range(0, "end")
            self._fnr_update_count()
            return

        try:
            sel = self._textbox._textbox.get("sel.first", "sel.last")
            if sel.strip():
                self._find_entry.delete(0, "end")
                self._find_entry.insert(0, sel.strip())
                self._fnr_update_count()
        except Exception:
            pass

    def _close_find_replace(self) -> None:
        """Hide the Find & Replace bar and clear highlights."""
        self._fnr_bar.pack_forget()
        self._fnr_toggle_btn.configure(
            fg_color="transparent", border_color="#334", text_color="#8ab"
        )
        self._textbox._textbox.tag_remove("fnr_highlight", "1.0", "end")
        self._textbox._textbox.tag_remove("fnr_current", "1.0", "end")
        self._fnr_match_label.configure(text="")
        self._fnr_current_pos = "1.0"

    def _fnr_update_count(self) -> None:
        """Update the match count label as the user types."""
        find_text = self._find_entry.get()
        if not find_text:
            self._fnr_match_label.configure(text="")
            self._textbox._textbox.tag_remove("fnr_highlight", "1.0", "end")
            return

        content = self._canonical_text or self._textbox.get("1.0", "end-1c")
        flags = 0 if self._fnr_case_var.get() else re.IGNORECASE
        matches = list(re.finditer(re.escape(find_text), content, flags))
        count = len(matches)

        widget = self._textbox._textbox
        widget.tag_remove("fnr_highlight", "1.0", "end")
        widget.tag_config("fnr_highlight", background="#3A3A00", foreground="#FFEE44")
        widget.tag_config("fnr_current", background="#B8860B", foreground="white")

        for match in matches:
            start_idx = f"1.0+{match.start()}c"
            end_idx = f"1.0+{match.end()}c"
            widget.tag_add("fnr_highlight", start_idx, end_idx)

        if count == 0:
            self._fnr_match_label.configure(text="No matches", text_color="#CC4444")
        elif count == 1:
            self._fnr_match_label.configure(text="1 match", text_color="#44CC44")
        else:
            self._fnr_match_label.configure(text=f"{count} matches", text_color="#44CC44")

        self._fnr_current_pos = "1.0"

    def _fnr_replace_next(self) -> None:
        """Replace the next occurrence of the find text."""
        find_text = self._find_entry.get().strip()
        replace_text = self._replace_entry.get()
        if not find_text:
            return

        content = self._canonical_text or self._textbox.get("1.0", "end-1c")
        flags = 0 if self._fnr_case_var.get() else re.IGNORECASE

        try:
            start_offset = self._index_to_char_offset(self._fnr_current_pos)
        except Exception:
            start_offset = 0

        match = re.search(re.escape(find_text), content[start_offset:], flags)
        if match is None and start_offset > 0:
            match = re.search(re.escape(find_text), content, flags)
            start_offset = 0
            self._fnr_match_label.configure(text="Wrapped to top", text_color="#FFAA44")

        if match is None:
            self._fnr_match_label.configure(text="No matches", text_color="#CC4444")
            return

        abs_start = start_offset + match.start()
        abs_end = start_offset + match.end()

        widget = self._textbox._textbox
        widget.tag_remove("fnr_current", "1.0", "end")
        cur_start = f"1.0+{abs_start}c"
        cur_end = f"1.0+{abs_end}c"
        widget.tag_add("fnr_current", cur_start, cur_end)
        widget.see(cur_start)

        updated = content[:abs_start] + replace_text + content[abs_end:]
        self._apply_text_update(updated)

        self._fnr_current_pos = f"1.0+{abs_start + len(replace_text)}c"
        self._fnr_update_count()

    def _fnr_replace_all(self) -> None:
        """Replace every occurrence and report the count."""
        find_text = self._find_entry.get().strip()
        replace_text = self._replace_entry.get()
        if not find_text:
            return

        content = self._canonical_text or self._textbox.get("1.0", "end-1c")
        flags = 0 if self._fnr_case_var.get() else re.IGNORECASE
        pattern = re.compile(re.escape(find_text), flags)
        count = len(pattern.findall(content))

        if count == 0:
            self._fnr_match_label.configure(text="No matches found", text_color="#CC4444")
            return

        updated = pattern.sub(replace_text, content)
        self._apply_text_update(updated)

        self._fnr_match_label.configure(
            text=f"✓  {count} replacement{'s' if count != 1 else ''} made",
            text_color="#44FF44",
        )
        self.append_log(
            f'Find & Replace: "{find_text}" → "{replace_text}"  '
            f'({count} replacement{"s" if count != 1 else ""})'
        )
        self._fnr_current_pos = "1.0"
        self._textbox._textbox.tag_remove("fnr_highlight", "1.0", "end")
        self._textbox._textbox.tag_remove("fnr_current", "1.0", "end")

    def _index_to_char_offset(self, index: str) -> int:
        try:
            content = self._textbox.get("1.0", "end")
            lines = content.split("\n")
            line_n, col_n = index.split(".")
            line_n, col_n = int(line_n) - 1, int(col_n)
            offset = sum(len(lines[i]) + 1 for i in range(line_n))
            return offset + col_n
        except Exception:
            return 0

    def _speed_down(self) -> None:
        if self._speed_idx > 0:
            self._speed_idx -= 1
            self._apply_speed()

    def _speed_up(self) -> None:
        if self._speed_idx < len(self._speed_rates) - 1:
            self._speed_idx += 1
            self._apply_speed()

    def _apply_speed(self) -> None:
        rate = self._speed_rates[self._speed_idx]
        label = f"{rate:.2g}×"   # "0.5×", "1×", "1.25×", etc.
        self._speed_label.configure(text=label)
        if self._player:
            self._player.set_rate(rate)

    # ── Waveform ──────────────────────────────────────────────────────────────

    def _load_waveform(self, audio_path: str) -> None:
        """Extract amplitude peaks from audio in a background thread."""
        self._waveform_request_id += 1
        req_id = self._waveform_request_id
        self._waveform_peaks = []
        self._waveform_duration = 0.0

        # Show the frame with a loading label while we compute
        self._waveform_frame.pack(fill="x", padx=14, pady=(0, 4))
        self._waveform_canvas.delete("all")
        w = self._waveform_canvas.winfo_width() or 600
        self._waveform_canvas.create_text(
            w // 2, 24, text="Loading waveform…",
            fill="#446688", font=("Courier New", 10),
        )

        def worker():
            peaks, duration = self._extract_waveform_peaks(audio_path)
            self.after(0, lambda: self._on_waveform_loaded(req_id, peaks, duration))

        threading.Thread(target=worker, daemon=True).start()

    def _extract_waveform_peaks(self, audio_path: str) -> tuple[list[float], float]:
        """Use FFmpeg to extract RMS amplitude buckets. Returns (peaks, duration_sec)."""
        import subprocess, json as _json
        NUM_BUCKETS = 600   # one bucket per pixel at ~600px width

        # Step 1: get duration
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(probe.stdout.strip())
        except Exception:
            return [], 0.0

        if duration <= 0:
            return [], 0.0

        # Step 2: extract audio samples as raw PCM, compute RMS per bucket
        try:
            # Read as 8kHz mono s16le — enough resolution for a waveform display
            result = subprocess.run(
                ["ffmpeg", "-i", audio_path,
                 "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                capture_output=True, timeout=60,
            )
            raw = result.stdout
        except Exception:
            return [], duration

        if not raw:
            return [], duration

        import struct, math
        sample_count = len(raw) // 2
        if sample_count == 0:
            return [], duration

        bucket_size = max(1, sample_count // NUM_BUCKETS)
        peaks = []
        for i in range(0, sample_count - bucket_size, bucket_size):
            chunk = struct.unpack_from(f"{bucket_size}h", raw, i * 2)
            rms = math.sqrt(sum(s * s for s in chunk) / bucket_size)
            peaks.append(rms)

        # Normalise to 0.0–1.0
        max_val = max(peaks) if peaks else 1.0
        if max_val > 0:
            peaks = [p / max_val for p in peaks]

        return peaks, duration

    def _on_waveform_loaded(self, req_id: int, peaks: list[float], duration: float) -> None:
        if req_id != self._waveform_request_id:
            return
        self._waveform_peaks = peaks
        self._waveform_duration = duration
        self._waveform_frame.pack(fill="x", padx=14, pady=(0, 4))
        self._draw_waveform()

    def _draw_waveform(self) -> None:
        """Render peaks onto the canvas. Called on resize and after load."""
        canvas = self._waveform_canvas
        canvas.delete("all")
        w = canvas.winfo_width() or 600
        h = 48
        peaks = self._waveform_peaks

        if not peaks:
            return

        # Background
        canvas.create_rectangle(0, 0, w, h, fill="#0D1420", outline="")

        # Draw waveform bars
        bar_w = max(1, w / len(peaks))
        mid = h / 2
        for i, amp in enumerate(peaks):
            x = i * bar_w
            bar_h = max(1, amp * (h / 2 - 2))
            # Colour: bright teal for speech, dark blue for silence
            color = "#1E6A8A" if amp > 0.05 else "#0D2030"
            canvas.create_rectangle(
                x, mid - bar_h, x + bar_w - 0.5, mid + bar_h,
                fill=color, outline="",
            )

        # Playhead
        self._draw_waveform_playhead()

    def _draw_waveform_playhead(self) -> None:
        """Draw (or redraw) the white playhead line at the current position."""
        canvas = self._waveform_canvas
        canvas.delete("playhead")
        if not self._waveform_duration or not self._player:
            return
        pos = self._player.position_seconds
        w = canvas.winfo_width() or 600
        x = int((pos / self._waveform_duration) * w)
        canvas.create_line(x, 0, x, 48, fill="white", width=1, tags="playhead")

    def _on_waveform_click(self, event) -> None:
        """Seek to the clicked position in the waveform."""
        if not self._waveform_duration or not self._player:
            return
        w = self._waveform_canvas.winfo_width() or 600
        ratio = max(0.0, min(1.0, event.x / w))
        target = ratio * self._waveform_duration
        self._player.jump_to(target)
        self.set_status(f"Jumped to {self._format_seconds(target)}", "#7DD8E8")
        self._schedule_position_update()
        self._start_sync_timer()
        self._draw_waveform_playhead()

    def _on_waveform_resize(self, event) -> None:
        """Redraw waveform when the canvas is resized."""
        if self._waveform_peaks:
            self._draw_waveform()

    # ── End waveform ──────────────────────────────────────────────────────────

    def _skip_to_next_speech(self) -> None:
        """Jump past the next gap of silence >= _gap_threshold seconds.

        Scans forward from the current playback position in the word map,
        finds the first gap where next_word.start - prev_word.end >= threshold,
        and jumps to the start of the word after that gap.
        """
        if not self._player or not self._player.is_loaded or not self._word_map:
            return

        pos_sec = self._player.position_seconds

        # Find the word map index closest to current position
        current_idx = max(0, self._current_word_idx)

        # Walk forward looking for a gap
        target_sec: float | None = None
        mapped = [w for w in self._word_map if w["char_start"] >= 0]

        for i in range(current_idx, len(mapped) - 1):
            this_word = mapped[i]
            next_word = mapped[i + 1]
            # Only consider gaps that start after the current playhead
            if this_word["end"] < pos_sec:
                continue
            gap = next_word["start"] - this_word["end"]
            if gap >= self._gap_threshold:
                target_sec = next_word["start"]
                break

        if target_sec is not None:
            self._player.jump_to(target_sec)
            self.set_status(
                f"Skipped gap — jumped to {self._format_seconds(target_sec)}",
                "#7DD8E8",
            )
            self._schedule_position_update()
            self._start_sync_timer()
        else:
            self.set_status("No gap found ahead.", "#FFAA44")

    def _play_audio(self):
        if self._player and self._player.play():
            self.set_status("Playing audio", "#7DD8E8")
            self._update_audio_state("Audio playing", "#7DD8E8")
            self._schedule_position_update()
            self._start_sync_timer()

    def _pause_audio(self):
        if self._player and self._player.is_loaded:
            self._player.pause()
            self._stop_sync_timer()
            self._textbox._textbox.tag_remove("current_word", "1.0", "end")
            self.set_status("Audio paused", "#AAAAAA")
            self._update_audio_state("Audio paused", "#AAAAAA")

    def _stop_audio(self):
        if self._player and self._player.is_loaded:
            self._player.stop()
            self._stop_sync_timer()
            self._textbox._textbox.tag_remove("current_word", "1.0", "end")
            self._current_word_idx = -1
            self.set_status("Audio stopped", "#AAAAAA")
            self._update_audio_state("Audio stopped", "#AAAAAA")
            self._position_label.configure(text="00:00 / 00:00")

    def _start_sync_timer(self) -> None:
        self._stop_sync_timer()
        self._sync_timer_id = self.after(250, self._sync_playback)

    def _stop_sync_timer(self) -> None:
        if self._sync_timer_id:
            try:
                self.after_cancel(self._sync_timer_id)
            except Exception:
                pass
            self._sync_timer_id = None

    def _sync_playback(self) -> None:
        try:
            if not self._player or not self._player.is_loaded:
                self._sync_timer_id = None
                return
            if self._player.is_playing:
                pos_sec = self._player.position_seconds

                # ── Fast path: still inside the current word ──────────────
                if 0 <= self._current_word_idx < len(self._word_map):
                    cur = self._word_map[self._current_word_idx]
                    if cur["start"] <= pos_sec <= cur["end"]:
                        self._sync_timer_id = self.after(100, self._sync_playback)
                        return

                # ── Forward window scan (normal playback) ─────────────────
                # Start from the last known position; scan at most 20 words
                # ahead, which covers ~5-10 seconds of typical speech.
                start_idx = max(0, self._current_word_idx)
                found_idx, found_item = -1, None

                for idx in range(start_idx, min(start_idx + 20, len(self._word_map))):
                    item = self._word_map[idx]
                    if item["start"] > pos_sec + 2.0:
                        break
                    if item["start"] <= pos_sec <= item["end"]:
                        found_idx, found_item = idx, item
                        break

                # ── Fallback full scan (after jump / seek) ────────────────
                if found_idx == -1:
                    for idx, item in enumerate(self._word_map):
                        if item["start"] <= pos_sec <= item["end"]:
                            found_idx, found_item = idx, item
                            break

                # ── Update highlight only when word changes ───────────────
                # During gaps (found_idx == -1), keep the previous highlight
                # visible — blanking the screen during pauses is distracting.
                if found_idx != -1 and found_idx != self._current_word_idx:
                    self._current_word_idx = found_idx
                    widget = self._textbox._textbox
                    widget.tag_remove("current_word", "1.0", "end")
                    if found_item["char_start"] >= 0:
                        start_tk = f"1.0+{found_item['char_start']}c"
                        end_tk   = f"1.0+{found_item['char_end']}c"
                        widget.tag_add("current_word", start_tk, end_tk)
                        if not self._user_is_editing and not self._is_position_visible(start_tk):
                            widget.see(start_tk)

                # Keep waveform playhead in sync
                if self._waveform_peaks:
                    self._draw_waveform_playhead()

                self._sync_timer_id = self.after(100, self._sync_playback)
            else:
                self._sync_timer_id = None
        except Exception:
            self._sync_timer_id = None

    def _is_position_visible(self, tk_index: str) -> bool:
        """Return True if the given text index is currently visible in the viewport."""
        try:
            widget = self._textbox._textbox
            top_line = int(widget.index("@0,0").split(".")[0])
            bottom_line = int(
                widget.index(f"@{widget.winfo_width()},{widget.winfo_height()}").split(".")[0]
            )
            target_line = int(widget.index(tk_index).split(".")[0])
            return top_line <= target_line <= bottom_line
        except Exception:
            return False

    def _schedule_position_update(self):
        if self._position_job is not None:
            try:
                self.after_cancel(self._position_job)
            except Exception:
                pass
        self._position_job = self.after(500, self._update_position_label)

    def _update_position_label(self):
        self._position_job = None
        if self._player and self._player.is_loaded:
            pos = self._player.position_seconds
            dur = self._player.duration_seconds
            self._position_label.configure(
                text=f"{self._format_seconds(pos)} / {self._format_seconds(dur)}"
            )
            if self._player.is_playing:
                self._schedule_position_update()

    def _format_seconds(self, seconds: float) -> str:
        total = max(0, int(seconds))
        return f"{total // 60:02d}:{total % 60:02d}"

    def _open_transcript_file(self):
        active_path = self._active_transcript_path()
        if active_path and os.path.isfile(active_path):
            try:
                os.startfile(active_path)
                return
            except OSError:
                pass
        self._browse_transcript_file()

    def _open_output_folder(self):
        folder = self._current_folder_path
        if folder and os.path.isdir(folder):
            subprocess.Popen(f'explorer "{folder}"')

    def _copy_all(self):
        content = self._textbox.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self._copy_btn.configure(text="Copied")
            self.after(2000, lambda: self._copy_btn.configure(text=" Copy All"))

    def _copy_debug_bundle(self):
        bundle = _build_debug_bundle_text(self._active_transcript_path(), self._case_root)
        if not bundle.strip():
            self.set_status("No debug bundle data available.", "#FFAA44")
            return
        self.clipboard_clear()
        self.clipboard_append(bundle)
        self._copy_debug_btn.configure(text="Copied")
        self.after(2000, lambda: self._copy_debug_btn.configure(text="Copy Debug Bundle"))
        self.set_status("Debug bundle copied to clipboard.", "#44FF44")

    def _save_transcript(self):
        save_path = self._save_target_path()
        if not save_path:
            return
        try:
            content = self._canonical_text or self._textbox.get("1.0", "end")
            with open(save_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._save_btn.configure(text="Saved")
            self.after(2000, lambda: self._save_btn.configure(text=" Save"))
        except Exception as exc:
            self._path_label.configure(text=f"Save failed: {exc}", text_color="#CC4444")

    def _export_review_docx(self):
        active_path = self._active_transcript_path()
        if not active_path or not os.path.isfile(active_path):
            messagebox.showerror(
                "No transcript",
                "Load a transcript before exporting a confidence review.",
            )
            return
        if not self._words:
            return
        self._export_review_btn.configure(state="disabled", text="Exporting…")

        def _safe_log(msg: str) -> None:
            self.after(0, self.append_log, msg)

        def worker():
            try:
                path = export_confidence_docx(
                    active_path,
                    self._words,
                    progress_callback=_safe_log,
                )
                self.after(0, lambda: self._on_review_docx_done(path, None))
            except Exception as exc:
                self.after(0, lambda: self._on_review_docx_done(None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_review_docx_done(self, path: str | None, error: Exception | None):
        self._export_review_btn.configure(state="normal", text="Export Review DOCX")
        if error:
            self.set_status(f"Review export failed: {error}", "#CC4444")
            return
        self._review_docx_path = path
        self._open_review_btn.configure(state="normal")
        self.set_status("Review DOCX exported", "#44FF44")
        self.append_log(f"Saved confidence review DOCX: {os.path.basename(path)}")

    def _open_review_docx(self):
        if self._review_docx_path and os.path.isfile(self._review_docx_path):
            os.startfile(self._review_docx_path)

    def _set_format_processing_state(self, is_processing: bool) -> None:
        self._format_running = is_processing
        if is_processing:
            if self._format_btn is not None:
                self._format_btn.configure(state="disabled", text="Formatting…")
            self._run_corrections_btn.configure(state="disabled")
            self._ai_correct_btn.configure(state="disabled")
        else:
            if self._format_btn is not None:
                self._format_btn.configure(
                    state="normal" if self._current_path else "disabled",
                    text="Format Transcript",
                )
            self._run_corrections_btn.configure(
                state="normal" if self._current_path else "disabled",
                text="⚙ Run Corrections",
            )
            self._ai_correct_btn.configure(
                state="normal" if self._current_path else "disabled",
                text="✨ AI Correct",
            )

    def _start_format_transcript(self) -> None:
        if self._format_running:
            return
        active_path = self._active_transcript_path()
        if not active_path or not os.path.isfile(active_path):
            messagebox.showerror("No transcript", "Load a transcript before formatting.")
            return
        if not active_path.lower().endswith(".txt"):
            messagebox.showerror("Unsupported Source", "Format Transcript requires a .txt transcript.")
            return

        self._set_format_processing_state(True)
        self.append_log("Starting formatting pipeline...")
        self.set_status("Starting formatting pipeline...", "#4499FF")

        threading.Thread(target=self._run_format_pipeline, daemon=True).start()

    def _run_format_pipeline(self) -> None:
        try:
            from config import ANTHROPIC_API_KEY
            from core.correction_runner import (
                _build_job_config_from_ufm,
                _load_job_config_for_transcript,
                run_correction_job,
            )
            from core.docx_formatter import format_transcript_to_docx
            from spec_engine.ai_corrector import run_ai_correction

            source = self._active_transcript_path() or ""
            job_config_data = _load_job_config_for_transcript(source)
            ufm = job_config_data.get("ufm_fields", {}) if isinstance(job_config_data, dict) else {}
            if not ufm.get("speaker_map_verified"):
                raise ValueError("Speaker mapping must be verified before formatting.")

            self.after(0, self.append_log, "Applying corrections...")
            correction_result: dict = {}

            def _capture_done(result: dict) -> None:
                correction_result.update(result)

            run_correction_job(
                source,
                progress_callback=lambda msg: self.after(0, self.append_log, msg),
                done_callback=_capture_done,
            )

            if not correction_result.get("success"):
                raise RuntimeError(correction_result.get("error", "Correction pipeline failed"))

            corrected_path = correction_result.get("corrected_path") or source
            final_text = correction_result.get("corrected_text", "")

            self.after(
                0,
                self.append_log,
                "Deterministic corrections complete. Use 'AI Correct' in the Corrections tab to run the AI pass.",
            )

            self.after(0, self.append_log, "Formatting document...")
            output_path = format_transcript_to_docx(
                corrected_path,
                progress_callback=lambda msg: self.after(0, self.append_log, msg),
            )

            self.after(0, self._on_format_done, corrected_path, final_text, output_path, None)
        except Exception as exc:
            self.after(0, self._on_format_done, None, None, None, str(exc))

    def _on_format_done(
        self,
        corrected_path: str | None,
        final_text: str | None,
        output_path: str | None,
        error: str | None,
    ) -> None:
        self._set_format_processing_state(False)

        if error:
            self.set_status(f"Formatting failed: {error[:80]}", "#CC4444")
            self.append_log(f"ERROR: {error}")
            messagebox.showerror("Format Transcript Failed", error)
            return

        if corrected_path and final_text is not None:
            if self._original_text is None:
                self._original_text = self._canonical_text or self._textbox.get("1.0", "end-1c")
            self._corrected_path = corrected_path
            self._processed_text = final_text
            self._formatted_docx_path = output_path
            self._update_path_label()
            try:
                cursor_pos = self._textbox._textbox.index("insert")
            except Exception:
                cursor_pos = "1.0"
            self._apply_text_update(self._processed_text)
            try:
                self._textbox._textbox.mark_set("insert", cursor_pos)
                self._textbox._textbox.see(cursor_pos)
            except Exception:
                pass
            self._load_low_confidence_words(corrected_path)
            self._load_word_data(corrected_path)

        self.append_log("Formatting complete")
        if output_path:
            self.append_log(f"Formatted DOCX: {os.path.basename(output_path)}")
            self.set_status("Transcript formatted successfully", "#44FF44")
            messagebox.showinfo("Format Complete", f"Transcript formatted:\n{output_path}")

    def _run_corrections_pipeline(self) -> None:
        """Run deterministic corrections, then AI correction when configured.

        Runs in a background thread. On completion the corrected text is
        applied directly into the textbox via _apply_text_update() so that
        confidence highlighting and word-map sync stay intact.
        """
        source = self._active_transcript_path()
        if not source:
            return

        self._run_corrections_btn.configure(state="disabled", text="Correcting…")
        self._ai_correct_btn.configure(state="disabled")
        self.set_status("Running corrections pipeline…", "#4499FF")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

        def worker():
            from core.correction_runner import run_correction_job
            run_correction_job(
                source,
                progress_callback=lambda msg: self.after(0, self.append_log, msg),
                done_callback=lambda result: self.after(0, self._on_corrections_done, result),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_corrections_done(self, result: dict) -> None:
        """Called on the main thread when the corrections pipeline finishes."""
        if not result.get("success"):
            self._run_corrections_btn.configure(state="normal", text="⚙ Run Corrections")
            self._ai_correct_btn.configure(state="normal", text="✨ AI Correct")
            err = result.get("error", "unknown error")
            self.set_status(f"Corrections failed: {err[:80]}", "#CC4444")
            self.append_log(f"ERROR: {err}")
            return

        corrected_text = result.get("corrected_text", "")
        if not corrected_text.strip():
            self._run_corrections_btn.configure(state="normal", text="⚙ Run Corrections")
            self._ai_correct_btn.configure(state="normal", text="✨ AI Correct")
            self.set_status("Corrections ran but returned no text.", "#FFAA44")
            return

        # Apply corrected text in-place — rebuilds word map and highlights.
        # Preserve the cursor position so the viewport doesn't jump to the top.
        try:
            cursor_pos = self._textbox._textbox.index("insert")
        except Exception:
            cursor_pos = "1.0"
        if self._original_text is None:
            self._original_text = self._canonical_text or self._textbox.get("1.0", "end-1c")
        self._processed_text = corrected_text
        self._apply_text_update(self._processed_text)
        try:
            self._textbox._textbox.mark_set("insert", cursor_pos)
            self._textbox._textbox.see(cursor_pos)
        except Exception:
            pass

        corrected_path = result.get("corrected_path")
        if corrected_path:
            self._corrected_path = corrected_path
            self._update_path_label()
            self._load_word_data(corrected_path)

        count = result.get("correction_count", 0)
        flags = result.get("flag_count", 0)
        draft_mode = bool(result.get("draft_mode", False))
        self.append_log(
            f"Done: {count} correction(s), {flags} scopist flag(s). "
            f"File: {corrected_path or self._current_path}"
        )

        try:
            from config import ANTHROPIC_API_KEY
        except Exception:
            ANTHROPIC_API_KEY = ""
        ai_available = bool((ANTHROPIC_API_KEY or "").strip())

        self._run_corrections_btn.configure(state="normal", text="⚙ Run Corrections")
        self._ai_correct_btn.configure(state="normal", text="✨ AI Correct")
        self.set_status(
            (
                f"{'Draft' if draft_mode else '✓'} corrections applied — {count} correction(s)  |  {flags} scopist flag(s)."
                + (
                    "  Speaker mapping is not confirmed yet."
                    if draft_mode
                    else (
                        "  Click ✨ AI Correct to run the optional Claude pass."
                        if ai_available
                        else "  (AI Correct disabled: ANTHROPIC_API_KEY not set.)"
                    )
                )
            ),
            "#CCAA44" if draft_mode else "#44FF44",
        )

    def _on_ai_correct_clicked(self) -> None:
        """Header button: run Claude AI correction on the current transcript."""
        if self._ai_running:
            return
        if not self._current_path or not (self._canonical_text or "").strip():
            self.set_status("Load a transcript before running AI correction.", "#FFAA44")
            return

        try:
            from config import ANTHROPIC_API_KEY
        except Exception:
            ANTHROPIC_API_KEY = ""
        if not (ANTHROPIC_API_KEY or "").strip():
            self.set_status(
                "AI correction requires ANTHROPIC_API_KEY in your .env file.",
                "#CC4444",
            )
            return

        proceed = messagebox.askyesno(
            "Run AI Correction?",
            "Send the current transcript to Claude for a context-aware pass "
            "(homophones, proper nouns, scopist flags)?\n\n"
            "Cost is roughly $0.30 per hour of deposition. Verbatim words "
            "(uh, um, yeah, etc.) are protected and will not be changed.",
        )
        if not proceed:
            return

        self._ai_correct_btn.configure(state="disabled", text="AI Correcting…")
        self._run_corrections_btn.configure(state="disabled")
        self.set_status("Running AI correction pass…", "#4499FF")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

        self._start_ai_correction(self._canonical_text)

    def _start_ai_correction(self, corrected_text: str) -> None:
        """Launch the Claude correction pass from the Transcript tab."""
        if self._ai_running:
            return

        if not corrected_text.strip():
            self._run_corrections_btn.configure(state="normal", text="⚙ Run Corrections")
            self._ai_correct_btn.configure(state="normal", text="✨ AI Correct")
            self.set_status("No corrected transcript text available for AI pass.", "#FFAA44")
            return

        self._ai_running = True
        threading.Thread(
            target=self._run_ai_job,
            args=(corrected_text,),
            daemon=True,
        ).start()

    def _run_ai_job(self, corrected_text: str) -> None:
        from spec_engine.ai_corrector import run_ai_correction

        try:
            from core.correction_runner import (
                _build_job_config_from_ufm,
                _load_job_config_for_transcript,
            )

            source = self._active_transcript_path() or ""
            job_config_data = _load_job_config_for_transcript(source)
            job_config = _build_job_config_from_ufm(job_config_data) if job_config_data else None
        except Exception:
            job_config = None

        try:
            result_text = run_ai_correction(
                transcript_text=corrected_text,
                job_config=job_config or {},
                progress_callback=lambda msg: self.after(0, self.append_log, msg),
            )
            self.after(0, self._on_ai_done, result_text, None)
        except Exception as exc:
            self.after(0, self._on_ai_done, None, str(exc))

    def _on_ai_done(self, result_text: str | None, error: str | None) -> None:
        """Apply the AI pass result back into the Transcript tab."""
        self._ai_running = False
        self._run_corrections_btn.configure(state="normal", text="⚙ Run Corrections")
        self._ai_correct_btn.configure(state="normal", text="✨ AI Correct")

        if result_text and not error:
            try:
                cursor_pos = self._textbox._textbox.index("insert")
            except Exception:
                cursor_pos = "1.0"
            self._apply_text_update(result_text)
            self._processed_text = result_text
            try:
                self._textbox._textbox.mark_set("insert", cursor_pos)
                self._textbox._textbox.see(cursor_pos)
            except Exception:
                pass

            save_path = self._save_target_path()
            if save_path:
                with open(save_path, "w", encoding="utf-8") as fh:
                    fh.write(result_text)
                self._load_word_data(save_path)

            self.set_status("✓ AI correction complete — transcript updated.", "#44FF44")
            self.append_log("AI correction applied to transcript viewer.")
            self.append_log("Click Save to confirm the AI-corrected transcript on disk.")
            return

        self.set_status(f"AI correction failed: {(error or 'unknown')[:80]}", "#CC4444")
        self.append_log(f"ERROR: {error}")

    def destroy(self):
        self._stop_sync_timer()
        if self._position_job is not None:
            try:
                self.after_cancel(self._position_job)
            except Exception:
                pass
            self._position_job = None
        if self._player is not None:
            self._player.release()
            self._player = None
        super().destroy()

    def _on_textbox_modified(self, event=None) -> None:
        """Keep _canonical_text in sync with edits and schedule word map rebuild."""
        self._textbox._textbox.edit_modified(False)
        updated_text = self._textbox.get("1.0", "end-1c")
        if updated_text != self._canonical_text:
            start_char, end_char = self._find_changed_range(self._canonical_text, updated_text)
            self._mark_reviewed_range(start_char, end_char, "corrected")
        self._canonical_text = updated_text
        if self._processed_text is not None and self._corrected_path:
            self._processed_text = updated_text
        self._apply_confidence_highlights()
        self._update_confidence_summary()
        # Debounce word map rebuild: wait 800ms after the user stops typing,
        # then realign confidence highlights to the updated text.
        if hasattr(self, "_remap_job") and self._remap_job is not None:
            try:
                self.after_cancel(self._remap_job)
            except Exception:
                pass
        self._remap_job = self.after(800, self._rebuild_word_map_after_edit)

    def _rebuild_word_map_after_edit(self) -> None:
        """Rebuild the word map 800ms after the user stops typing.

        Keeps confidence highlights aligned to the current text without
        rebuilding on every keystroke. Only fires if word data is available.
        """
        self._remap_job = None
        if self._words:
            self._build_word_map(self._words)
        else:
            self._apply_confidence_highlights()

    def _toggle_edit_mode(self) -> None:
        """Retired — editing is now always active. Stub retained for safety."""
        pass

    def _insert_speaker_break(self) -> None:
        """Split the transcript at the cursor and insert a new speaker label on a new line."""
        label = self._speaker_break_entry.get().strip()
        if not label:
            self.set_status("Enter a speaker label first (e.g.  Speaker 4)", "#FFAA44")
            return

        widget = self._textbox._textbox
        try:
            cursor_idx = widget.index("insert")
        except Exception:
            self.set_status("Click inside the transcript to place the cursor first.", "#FFAA44")
            return

        insert_text = f"\n{label}: "
        widget.insert(cursor_idx, insert_text)

        new_cursor = f"{cursor_idx}+{len(insert_text)}c"
        widget.mark_set("insert", new_cursor)
        widget.see(new_cursor)

        self._canonical_text = self._textbox.get("1.0", "end-1c")
        self.set_status(f"Inserted  {label}:  — type the spoken text now.", "#44FF44")
