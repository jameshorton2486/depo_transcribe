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
import subprocess
import threading
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
        self._position_job = None

        self._words: list[dict] = []
        self._word_data_request_id = 0

        self._highlight_var = ctk.BooleanVar(value=True)
        self._build_ui()
        self._init_player()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 4))

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
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=14, pady=(0, 2))

        divider_top = ctk.CTkFrame(self, height=1, fg_color="#293243")
        divider_top.pack(fill="x", padx=14, pady=(0, 6))

        self._path_label = ctk.CTkLabel(
            self,
            text="No transcript loaded.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._path_label.pack(fill="x", padx=14, pady=(0, 4))

        player_row = ctk.CTkFrame(self, fg_color="transparent")
        player_row.pack(fill="x", padx=14, pady=(0, 4))

        self._play_btn = ctk.CTkButton(player_row, text="Play", width=72, command=self._play_audio)
        self._play_btn.pack(side="left", padx=(0, 4))

        self._pause_btn = ctk.CTkButton(player_row, text="Pause", width=72, command=self._pause_audio)
        self._pause_btn.pack(side="left", padx=(0, 4))

        self._stop_btn = ctk.CTkButton(player_row, text="Stop", width=72, command=self._stop_audio)
        self._stop_btn.pack(side="left", padx=(0, 8))

        self._position_label = ctk.CTkLabel(
            player_row,
            text="00:00 / 00:00",
            width=110,
            anchor="w",
            font=ctk.CTkFont(size=11),
        )
        self._position_label.pack(side="left")

        self._audio_label = ctk.CTkLabel(
            player_row,
            text="No audio loaded",
            anchor="w",
            font=ctk.CTkFont(size=11),
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

        conf_row = ctk.CTkFrame(self, fg_color="transparent")
        conf_row.pack(fill="x", padx=14, pady=(0, 4))

        self._conf_label = ctk.CTkLabel(
            conf_row,
            text="Confidence: no word-level data loaded",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
        )
        self._conf_label.pack(side="left")

        self._highlight_toggle = ctk.CTkCheckBox(
            conf_row,
            text="Highlight low-confidence words",
            variable=self._highlight_var,
            command=self._refresh_confidence_highlights,
            font=ctk.CTkFont(size=10),
        )
        self._highlight_toggle.pack(side="right")

        divider_bottom = ctk.CTkFrame(self, height=1, fg_color="#293243")
        divider_bottom.pack(fill="x", padx=14, pady=(0, 6))

        self._textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier New", size=13),
            wrap="word",
            state="disabled",
        )
        self._textbox.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self._textbox._textbox.bind("<<Modified>>", self._on_textbox_modified)
        self._textbox._textbox.bind("<Button-1>", self._on_textbox_click)

        self._log_box = ctk.CTkTextbox(
            self,
            height=56,
            font=ctk.CTkFont(family="Courier New", size=10),
            state="disabled",
        )
        self._log_box.pack(fill="x", padx=14, pady=(0, 6))

        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(0, 10))

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
            try:
                self.winfo_toplevel().corrections_tab.notify_transcript_loaded(filepath)
            except AttributeError:
                pass
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
        search_pos = 0
        for raw in words:
            word_text = str(raw.get("word") or raw.get("text") or "").strip()
            if not word_text:
                continue
            idx = content.lower().find(word_text.lower(), search_pos)
            if idx == -1:
                self._word_map.append(
                    {
                        "word": word_text,
                        "start": float(raw.get("start", 0.0) or 0.0),
                        "end": float(raw.get("end", 0.0) or 0.0),
                        "confidence": float(raw.get("confidence", 1.0) or 1.0),
                        "char_start": -1,
                        "char_end": -1,
                    }
                )
                continue
            self._word_map.append(
                {
                    "word": word_text,
                    "start": float(raw.get("start", 0.0) or 0.0),
                    "end": float(raw.get("end", 0.0) or 0.0),
                    "confidence": float(raw.get("confidence", 1.0) or 1.0),
                    "char_start": idx,
                    "char_end": idx + len(word_text),
                }
            )
            search_pos = idx + len(word_text)

        widget = self._textbox._textbox
        widget.tag_config("current_word", background="#2A4A6A", foreground="white")
        widget.tag_config("conf_low", foreground="#FF8C00")
        widget.tag_config("conf_mid", foreground="#CCCC00")
        self._apply_confidence_highlights()

        flagged = sum(1 for item in self._word_map if item["confidence"] < 0.8)
        total = len(self._word_map)
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
                current = None
                for idx, item in enumerate(self._word_map):
                    if item["start"] <= pos_sec <= item["end"]:
                        current = (idx, item)
                        break
                if current and current[0] != self._current_word_idx:
                    idx, item = current
                    self._current_word_idx = idx
                    widget = self._textbox._textbox
                    widget.tag_remove("current_word", "1.0", "end")
                    if item["char_start"] >= 0:
                        start_tk = f"1.0+{item['char_start']}c"
                        end_tk = f"1.0+{item['char_end']}c"
                        widget.tag_add("current_word", start_tk, end_tk)
                        widget.see(start_tk)
                self._sync_timer_id = self.after(250, self._sync_playback)
            else:
                self._sync_timer_id = None
        except Exception:
            self._sync_timer_id = None

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
            self._edit_mode_btn.configure(
                text="Exit Edit Mode",
                fg_color="#1558C0",
                border_color="#1558C0",
                text_color="white",
            )
            self._stop_sync_timer()
            self._textbox._textbox.tag_remove("current_word", "1.0", "end")
            self.set_status(
                "Edit Mode — type corrections directly. Click 'Exit Edit Mode' when done.",
                "#4499FF",
            )
        else:
            self._canonical_text = self._textbox.get("1.0", "end-1c")
            self._textbox.configure(state="disabled")
            self._edit_mode_btn.configure(
                text="Edit Mode",
                fg_color="transparent",
                border_color="#334",
                text_color="#8ab",
            )
            self.set_status("Read Mode — click any word to seek audio.", "gray")
            if self._words:
                self._build_word_map(self._words)
