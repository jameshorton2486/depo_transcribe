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
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.confidence_docx_exporter import export_confidence_docx
from core.vlc_player import VLCPlayer
from core.word_data_loader import get_flagged_summary, get_confidence_tier, load_words_for_transcript


class TranscriptTab(ctk.CTkFrame):
    """Transcript review workspace with audio sync and confidence markup."""

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._current_path: str | None = None
        self._current_folder_path: str | None = None
        self._audio_path: str | None = None
        self._review_docx_path: str | None = None
        self._canonical_text: str = ""
        self._word_map: list[dict] = []
        self._sync_timer_id: str | None = None
        self._edit_mode: bool = False
        self._current_word_idx: int = -1

        self._player: VLCPlayer | None = None
        self._player_ready = False
        self._speed_rates = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        self._speed_idx = 2   # index into _speed_rates; 2 = 1.0x (default)
        self._gap_threshold = 2.0   # seconds of silence that qualify as a skippable gap
        self._waveform_peaks: list[float] = []   # normalised 0.0–1.0 amplitude per bucket
        self._waveform_duration: float = 0.0
        self._waveform_request_id: int = 0
        self._position_job = None

        self._words: list[dict] = []
        self._word_data_request_id = 0
        self._low_confidence_words: list[dict] = []

        self._highlight_var = ctk.BooleanVar(value=True)
        self._build_ui()
        self._init_player()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(4, 2))

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

        self._edit_mode_btn = ctk.CTkButton(
            header,
            text="Edit Mode",
            width=110,
            fg_color="transparent",
            border_width=1,
            border_color="#334",
            text_color="#8ab",
            command=self._toggle_edit_mode,
        )
        self._edit_mode_btn.pack(side="right", padx=(4, 0))

        self._copy_btn = ctk.CTkButton(
            header,
            text=" Copy All",
            width=110,
            command=self._copy_all,
            state="disabled",
        )
        self._copy_btn.pack(side="right", padx=(4, 0))

        self._save_btn = ctk.CTkButton(
            header,
            text=" Save",
            width=90,
            command=self._save_transcript,
            state="disabled",
        )
        self._save_btn.pack(side="right", padx=(4, 0))

        self._status_label = ctk.CTkLabel(
            self,
            text="Ready",
            font=ctk.CTkFont(size=13),
            text_color="gray",
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=14, pady=(0, 2))

        divider_top = ctk.CTkFrame(self, height=1, fg_color="#293243")
        divider_top.pack(fill="x", padx=14, pady=(0, 3))

        self._path_label = ctk.CTkLabel(
            self,
            text="No transcript loaded.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
            anchor="w",
        )
        self._path_label.pack(fill="x", padx=14, pady=(0, 2))

        player_row = ctk.CTkFrame(self, fg_color="transparent")
        player_row.pack(fill="x", padx=14, pady=(0, 2))

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
        self._waveform_frame = ctk.CTkFrame(self, fg_color="#0D1420", corner_radius=4)
        self._waveform_frame.pack(fill="x", padx=14, pady=(0, 2))
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

        conf_row = ctk.CTkFrame(self, fg_color="transparent")
        conf_row.pack(fill="x", padx=14, pady=(0, 2))

        self._conf_label = ctk.CTkLabel(
            conf_row,
            text="Confidence: no word-level data loaded",
            font=ctk.CTkFont(size=13),
            text_color="gray",
            anchor="w",
        )
        self._conf_label.pack(side="left")

        self._highlight_toggle = ctk.CTkCheckBox(
            conf_row,
            text="Highlight low-confidence words",
            variable=self._highlight_var,
            command=self._refresh_confidence_highlights,
            font=ctk.CTkFont(size=13),
        )
        self._highlight_toggle.pack(side="right")

        divider_bottom = ctk.CTkFrame(self, height=1, fg_color="#293243")
        divider_bottom.pack(fill="x", padx=14, pady=(0, 3))

        self._low_conf_frame = ctk.CTkFrame(self, fg_color="#101826")
        self._low_conf_frame.pack(fill="x", padx=14, pady=(0, 3))

        low_conf_header = ctk.CTkFrame(self._low_conf_frame, fg_color="transparent")
        low_conf_header.pack(fill="x", padx=8, pady=(6, 2))

        self._low_conf_title = ctk.CTkLabel(
            low_conf_header,
            text="Low-Confidence Review: no transcript loaded",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#CCAA44",
            anchor="w",
        )
        self._low_conf_title.pack(side="left")

        self._low_conf_box = ctk.CTkTextbox(
            self._low_conf_frame,
            height=56,
            font=ctk.CTkFont(family="Courier New", size=13),
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

        # ── Edit Mode toolbar (hidden until Edit Mode activated) ─────────────
        self._edit_toolbar = ctk.CTkFrame(self, fg_color="#0D1B2A", corner_radius=4)
        # Not packed yet — shown when Edit Mode is toggled on

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

        self._textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier New", size=13),
            wrap="word",
            state="disabled",
            undo=True,
        )
        self._textbox.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self._textbox._textbox.bind("<<Modified>>", self._on_textbox_modified)
        self._textbox._textbox.bind("<Button-1>", self._on_textbox_click)
        self._textbox._textbox.bind("<Double-Button-1>", self._on_textbox_double_click)
        self.winfo_toplevel().bind("<Control-h>", lambda _: self._toggle_find_replace())
        self.winfo_toplevel().bind("<Escape>", lambda _: self._close_find_replace())

        # ── Right-click context menu ──────────────────────────────────────
        def _make_context_menu(event):
            widget = self._textbox._textbox
            try:
                inner_x = event.x_root - widget.winfo_rootx()
                inner_y = event.y_root - widget.winfo_rooty()
                click_index = widget.index(f"@{inner_x},{inner_y}")
                char_offset = self._index_to_char_offset(click_index)
            except Exception as exc:
                print(f"[RightClick] coord error: {exc}")
                return

            clicked_item = None
            if self._word_map:
                best_dist = float("inf")
                for item in self._word_map:
                    if item["char_start"] < 0:
                        continue
                    if item["char_start"] <= char_offset <= item["char_end"]:
                        clicked_item = item
                        break
                    dist = min(
                        abs(char_offset - item["char_start"]),
                        abs(char_offset - item["char_end"])
                    )
                    if dist < best_dist:
                        best_dist = dist
                        clicked_item = item

            menu = tk.Menu(widget, tearoff=0, font=("Segoe UI", 12))

            if clicked_item:
                _word = clicked_item["word"]
                _item = dict(clicked_item)

                menu.add_command(
                    label=f'Replace  "{_word}"…',
                    command=lambda: self._ctx_replace_one(_item),
                )
                menu.add_command(
                    label=f'Replace ALL  "{_word}"…',
                    command=lambda: self._ctx_replace_all(_word),
                )
                menu.add_separator()
                if not self._edit_mode:
                    menu.add_command(
                        label=f'Seek audio →  "{_word}"',
                        command=lambda: self._on_word_clicked(float(_item["start"])),
                    )
                menu.add_separator()

            menu.add_command(label="Find & Replace  (Ctrl+H)", command=self._toggle_find_replace)

            try:
                menu.tk_popup(event.x_root, event.y_root)
            except Exception as exc:
                print(f"[RightClick] popup error: {exc}")
            finally:
                menu.grab_release()

        def _show_context_menu(event):
            _make_context_menu(event)
            return "break"

        self._textbox._textbox.bind("<Button-3>", _show_context_menu)
        self._textbox.bind("<Button-3>", _show_context_menu, add=True)

        self._log_box = ctk.CTkTextbox(
            self,
            height=40,
            font=ctk.CTkFont(family="Courier New", size=13),
            state="disabled",
        )
        self._log_box.pack(fill="x", padx=14, pady=(0, 3))

        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(0, 4))

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
        else:
            self._audio_label.configure(
                text="VLC unavailable (install python-vlc to enable playback)",
                text_color="#CC8844",
            )
        if self._audio_path:
            self.set_audio_file(self._audio_path)

    def append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def set_status(self, text: str, color: str = "gray"):
        self._status_label.configure(text=text, text_color=color)

    def set_transcription_running(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self.set_status("Transcription running…", "white")
        self._open_folder_btn.configure(state="disabled")
        self._open_transcript_btn.configure(state="disabled")
        self._export_review_btn.configure(state="disabled")
        self._open_review_btn.configure(state="disabled")
        self._copy_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._run_corrections_btn.configure(state="disabled")
        self._path_label.configure(text="Processing…", text_color="gray")

    def set_transcription_complete(self, transcript_path: str, folder_path: str):
        self._current_folder_path = folder_path
        self.set_status("✓ Transcription complete", "#44FF44")
        self._open_folder_btn.configure(state="normal")
        self._open_transcript_btn.configure(state="normal")
        self.load_transcript(transcript_path)
        try:
            self.winfo_toplevel().corrections_tab.set_source(transcript_path)
        except AttributeError:
            pass

    def set_transcription_failed(self, error_msg: str):
        self.set_status(f"Failed: {error_msg[:80]}", "#FF4444")

    def load_transcript(self, filepath: str):
        if not filepath or not os.path.isfile(filepath):
            return
        try:
            content = self._read_transcript(filepath)
            self._current_path = filepath
            self._review_docx_path = None
            self._open_review_btn.configure(state="disabled")
            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")
            self._textbox.insert("1.0", content)
            self._canonical_text = content
            self._textbox.edit_modified(False)
            self._textbox._textbox.edit_modified(False)
            self._textbox.configure(state="disabled")
            self._edit_mode = False
            self._edit_mode_btn.configure(
                text="Edit Mode",
                fg_color="transparent",
                border_color="#334",
                text_color="#8ab",
            )
            self._path_label.configure(text=f"Loaded: {filepath}", text_color="gray")
            self._copy_btn.configure(state="normal")
            self._save_btn.configure(state="normal")
            self._run_corrections_btn.configure(state="normal")
            try:
                self.winfo_toplevel().corrections_tab.notify_transcript_loaded(filepath)
            except AttributeError:
                pass
            self._load_low_confidence_words(filepath)
            self._load_word_data(filepath)
        except Exception as exc:
            self._path_label.configure(text=f"Failed to load: {exc}", text_color="#CC4444")

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
        self._low_confidence_words = list(words or [])
        self._low_conf_box.configure(state="normal")
        self._low_conf_box.delete("1.0", "end")

        if not self._low_confidence_words:
            self._low_conf_title.configure(
                text="Low-Confidence Review: none stored for this transcript",
                text_color="#7DAACC",
            )
            self._low_conf_box.insert(
                "1.0",
                "No low-confidence words were stored in source_docs/job_config.json "
                "for this transcript.",
            )
            self._low_conf_box.configure(state="disabled")
            return

        self._low_conf_title.configure(
            text=f"Low-Confidence Review: {len(self._low_confidence_words)} words below threshold",
            text_color="#CCAA44",
        )
        lines = []
        for item in self._low_confidence_words[:20]:
            word = str(item.get("word", "") or "")
            confidence = float(item.get("confidence", 0.0) or 0.0)
            start = float(item.get("start", 0.0) or 0.0)
            lines.append(f"{word:20s}  {confidence:.2f}  @ {start:.1f}s")
        if len(self._low_confidence_words) > 20:
            lines.append(f"... and {len(self._low_confidence_words) - 20} more")

        self._low_conf_box.insert("1.0", "\n".join(lines))
        self._low_conf_box.configure(state="disabled")
        self.append_log(f"Loaded {len(self._low_confidence_words)} low-confidence words")

    def _on_word_data_loaded(self, request_id: int, filepath: str, words: list[dict]):
        if request_id != self._word_data_request_id or filepath != self._current_path:
            return
        self._words = words
        if words:
            self._build_word_map(words)
            self._render_with_confidence(words)
            self._export_review_btn.configure(state="normal")
        else:
            self._word_map = []
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
        summary = get_flagged_summary(self._words)
        flagged_color = "#FFAA44" if summary["flagged"] else "#7DD8E8"
        self._conf_label.configure(
            text=(
                f"Confidence: {summary['total']} words  |  "
                f"flagged {summary['flagged']}  |  "
                f"low {summary['low']}  |  critical {summary['critical']}"
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
        if not words:
            self._update_confidence_summary()
            return

        content = self._textbox.get("1.0", "end")
        content_lower = content.lower()
        search_pos = 0

        for raw in words:
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
                })
                continue

            self._word_map.append({
                "word":       word_text,
                "start":      float(raw.get("start", 0.0) or 0.0),
                "end":        float(raw.get("end",   0.0) or 0.0),
                "confidence": float(raw.get("confidence", 1.0) or 1.0),
                "char_start": found_start,
                "char_end":   found_start + len(word_text),
            })
            search_pos = found_start + len(word_text)

        widget = self._textbox._textbox
        widget.tag_config("current_word", background="#2A4A6A", foreground="white")
        widget.tag_config("conf_low",     foreground="#FF8C00")
        widget.tag_config("conf_mid",     foreground="#CCCC00")
        self._apply_confidence_highlights()

        flagged = sum(1 for item in self._word_map if item["confidence"] < 0.8)
        total   = len(self._word_map)
        self._conf_label.configure(
            text=f"Confidence: {total} words — {flagged} flagged below 80%",
            text_color="#CC9900" if flagged else "#44AA44",
        )

    def _apply_confidence_tags(self, word_list) -> None:
        self._apply_confidence_highlights()

    def _apply_confidence_highlights(self) -> None:
        widget = self._textbox._textbox
        widget.tag_remove("conf_low", "1.0", "end")
        widget.tag_remove("conf_mid", "1.0", "end")
        if not self._highlight_var.get():
            return
        for item in self._word_map:
            if item["char_start"] < 0:
                continue
            start_idx = f"1.0+{item['char_start']}c"
            end_idx = f"1.0+{item['char_end']}c"
            if item["confidence"] < 0.80:
                widget.tag_add("conf_low", start_idx, end_idx)
            elif item["confidence"] < 0.90:
                widget.tag_add("conf_mid", start_idx, end_idx)

    def _refresh_confidence_highlights(self) -> None:
        self._apply_confidence_highlights()

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
            return

        name = os.path.basename(audio_path)
        if not self._player_ready:
            self._audio_label.configure(text=f"Pending VLC init: {name}", text_color="#7DD8E8")
            return
        if not self._player or not self._player.is_available:
            self._audio_label.configure(text=f"Audio unavailable: {name}", text_color="#CC8844")
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
            self._schedule_position_update()
            self._load_waveform(audio_path)
        else:
            self._audio_label.configure(text=f"Could not load audio: {os.path.basename(audio_path)}", text_color="#CC4444")

    def _on_word_clicked(self, start_time: float):
        if self._player and self._player.jump_to(start_time):
            self.set_status(f"Jumped to {self._format_seconds(start_time)}", "#7DD8E8")
            self._schedule_position_update()
            self._start_sync_timer()

    def _on_textbox_click(self, event) -> None:
        if self._edit_mode or not self._word_map:
            return
        try:
            click_index = self._textbox._textbox.index(f"@{event.x},{event.y}")
        except Exception:
            return
        char_offset = self._index_to_char_offset(click_index)
        best = None
        best_dist = float("inf")
        for item in self._word_map:
            if item["char_start"] < 0:
                continue
            if item["char_start"] <= char_offset <= item["char_end"]:
                best = item
                break
            dist = min(abs(char_offset - item["char_start"]), abs(char_offset - item["char_end"]))
            if dist < best_dist:
                best_dist = dist
                best = item
        if best:
            self._on_word_clicked(float(best["start"]))

    def _on_textbox_double_click(self, event) -> str:
        """Double-click a word to open an inline correction popup."""
        if self._edit_mode or not self._word_map:
            return "break"
        # Defer so tkinter finishes its own double-click event chain first
        self.after(10, lambda: self._show_word_correction_popup(event.x, event.y))
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
        inner.config(state="disabled")

        # Update this word's map entry
        self._word_map[target_idx]["word"] = new_word
        self._word_map[target_idx]["char_end"] = target["char_start"] + new_len
        self._word_map[target_idx]["confidence"] = 1.0

        # Shift all subsequent entries
        for j in range(target_idx + 1, len(self._word_map)):
            if self._word_map[j]["char_start"] >= 0:
                self._word_map[j]["char_start"] += delta
                self._word_map[j]["char_end"] += delta

        self._canonical_text = self._textbox.get("1.0", "end-1c")
        self._apply_confidence_highlights()

        flagged = sum(1 for w in self._word_map if w["confidence"] < 0.8)
        total = len(self._word_map)
        self._conf_label.configure(
            text=f"Confidence: {total} words — {flagged} flagged below 80%",
            text_color="#CC9900" if flagged else "#44AA44",
        )
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
            self._apply_text_update(updated)
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
            self._apply_text_update(updated)
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
            self._apply_text_update(updated)
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
            self._apply_text_update(updated)
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

    def _apply_text_update(self, updated_content: str) -> None:
        """Apply a text change to both the textbox and canonical text, then rebuild word map."""
        self._canonical_text = updated_content
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", updated_content)
        if not self._edit_mode:
            self._textbox.configure(state="disabled")
        if self._words:
            self._build_word_map(self._words)
        else:
            self._word_map = []
        self._waveform_peaks = []
        self._waveform_duration = 0.0
        self._waveform_canvas.delete("all")
        self._waveform_frame.pack_forget()
        # Always clear any lingering text selection
        self._textbox._textbox.tag_remove("sel", "1.0", "end")
        self.set_status("Change applied — click Save to write to disk.", "#FFCC44")

    # ── Find & Replace ────────────────────────────────────────────────────

    def _toggle_find_replace(self) -> None:
        """Show or hide the Find & Replace bar."""
        if self._fnr_bar.winfo_ismapped():
            self._close_find_replace()
        else:
            self._fnr_bar.pack(fill="x", padx=0, pady=0, before=self._textbox)
            self._find_entry.focus()
            self._find_entry.select_range(0, "end")
            self._fnr_toggle_btn.configure(
                fg_color="#1558C0", border_color="#1558C0", text_color="white"
            )
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
            self._schedule_position_update()
            self._start_sync_timer()

    def _pause_audio(self):
        if self._player and self._player.is_loaded:
            self._player.pause()
            self._stop_sync_timer()
            self._textbox._textbox.tag_remove("current_word", "1.0", "end")
            self.set_status("Audio paused", "#AAAAAA")

    def _stop_audio(self):
        if self._player and self._player.is_loaded:
            self._player.stop()
            self._stop_sync_timer()
            self._textbox._textbox.tag_remove("current_word", "1.0", "end")
            self._current_word_idx = -1
            self.set_status("Audio stopped", "#AAAAAA")
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
                        if not self._is_position_visible(start_tk):
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
        if self._current_path and os.path.isfile(self._current_path):
            try:
                os.startfile(self._current_path)
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

    def _save_transcript(self):
        if not self._current_path:
            return
        try:
            content = self._canonical_text or self._textbox.get("1.0", "end")
            with open(self._current_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._save_btn.configure(text="Saved")
            self.after(2000, lambda: self._save_btn.configure(text=" Save"))
        except Exception as exc:
            self._path_label.configure(text=f"Save failed: {exc}", text_color="#CC4444")

    def _export_review_docx(self):
        if not self._current_path or not os.path.isfile(self._current_path):
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
                    self._current_path,
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

    def _run_corrections_pipeline(self) -> None:
        """Run the deterministic corrections pipeline on the current transcript.

        Runs in a background thread. On completion the corrected text is
        applied directly into the textbox via _apply_text_update() so that
        confidence highlighting and word-map sync stay intact.
        """
        if not self._current_path:
            return

        self._run_corrections_btn.configure(state="disabled", text="Correcting…")
        self.set_status("Running corrections pipeline…", "#4499FF")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

        def worker():
            from core.correction_runner import run_correction_job
            run_correction_job(
                self._current_path,
                progress_callback=lambda msg: self.after(0, self.append_log, msg),
                done_callback=lambda result: self.after(0, self._on_corrections_done, result),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_corrections_done(self, result: dict) -> None:
        """Called on the main thread when the corrections pipeline finishes."""
        self._run_corrections_btn.configure(state="normal", text="⚙ Run Corrections")

        if not result.get("success"):
            err = result.get("error", "unknown error")
            self.set_status(f"Corrections failed: {err[:80]}", "#CC4444")
            self.append_log(f"ERROR: {err}")
            return

        corrected_text = result.get("corrected_text", "")
        if not corrected_text.strip():
            self.set_status("Corrections ran but returned no text.", "#FFAA44")
            return

        # Apply corrected text in-place — rebuilds word map and highlights.
        # Preserve the cursor position so the viewport doesn't jump to the top.
        try:
            cursor_pos = self._textbox._textbox.index("insert")
        except Exception:
            cursor_pos = "1.0"
        self._apply_text_update(corrected_text)
        try:
            self._textbox._textbox.mark_set("insert", cursor_pos)
            self._textbox._textbox.see(cursor_pos)
        except Exception:
            pass

        # Point the current path at the written _corrected.txt file so that
        # Save and subsequent operations target the corrected version.
        corrected_path = result.get("corrected_path")
        if corrected_path:
            self._current_path = corrected_path
            self._path_label.configure(text=f"Loaded: {corrected_path}", text_color="gray")

        count = result.get("correction_count", 0)
        flags = result.get("flag_count", 0)
        self.set_status(
            f"✓ Corrections applied — {count} correction(s)  |  {flags} scopist flag(s)."
            "  Click Save to write to disk.",
            "#44FF44",
        )
        self.append_log(
            f"Done: {count} correction(s), {flags} scopist flag(s). "
            f"File: {corrected_path or self._current_path}"
        )

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
        """Keep _canonical_text in sync with manual edits in the textbox."""
        self._textbox._textbox.edit_modified(False)
        if self._edit_mode:
            self._canonical_text = self._textbox.get("1.0", "end-1c")

    def _toggle_edit_mode(self) -> None:
        self._edit_mode = not self._edit_mode
        if self._edit_mode:
            self._textbox.configure(state="normal")
            self._textbox._textbox.edit_reset()  # fresh undo stack for this session
            self._edit_toolbar.pack(fill="x", padx=14, pady=(0, 4), before=self._textbox)
            self._speaker_break_entry.delete(0, "end")
            self._edit_mode_btn.configure(
                text="Exit Edit Mode",
                fg_color="#1558C0",
                border_color="#1558C0",
                text_color="white",
            )
            self._stop_sync_timer()
            self._textbox._textbox.tag_remove("current_word", "1.0", "end")
            # Undo/redo — active only inside Edit Mode
            self._textbox._textbox.bind(
                "<Control-z>",
                lambda _: self._textbox._textbox.edit_undo() or "break",
            )
            self._textbox._textbox.bind(
                "<Control-Z>",
                lambda _: self._textbox._textbox.edit_undo() or "break",
            )
            self._textbox._textbox.bind(
                "<Control-y>",
                lambda _: self._textbox._textbox.edit_redo() or "break",
            )
            self.set_status(
                "Edit Mode — type freely: corrections, Enter for new lines, paste text.  "
                "Ctrl+Z = undo  ·  Ctrl+Y = redo  ·  Click 'Exit Edit Mode' when done.",
                "#4499FF",
            )
        else:
            self._canonical_text = self._textbox.get("1.0", "end-1c")
            self._textbox.configure(state="disabled")
            self._edit_toolbar.pack_forget()
            self._edit_mode_btn.configure(
                text="Edit Mode",
                fg_color="transparent",
                border_color="#334",
                text_color="#8ab",
            )
            # Remove undo/redo bindings when leaving Edit Mode
            self._textbox._textbox.unbind("<Control-z>")
            self._textbox._textbox.unbind("<Control-Z>")
            self._textbox._textbox.unbind("<Control-y>")
            self.set_status("Read Mode — click to seek audio · double-click any word to correct it.", "gray")
            if self._words:
                self._build_word_map(self._words)

    def _insert_speaker_break(self) -> None:
        """Split the transcript at the cursor and insert a new speaker label on a new line."""
        if not self._edit_mode:
            return

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
