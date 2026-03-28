"""
ui/tab_transcript.py

Displays the completed transcript, job log, and status.
Provides append_log / set_status / set_transcription_* methods
called by TranscribeTab during and after a transcription job.
"""

import os

import customtkinter as ctk
from tkinter import filedialog


class TranscriptTab(ctk.CTkFrame):
    """
    Two-panel Transcript tab:
      - Top:    running job log + status label
      - Middle: transcript text viewer (editable after load)
      - Bottom: action buttons (Open Folder, Open Transcript, Copy, Save)
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._current_path: str | None = None
        self._current_folder_path: str | None = None
        self._build_ui()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header row ────────────────────────────────────────────────────────
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

        # ── Status label ──────────────────────────────────────────────────────
        self._status_label = ctk.CTkLabel(
            self,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=14, pady=(0, 2))

        # ── Job log box (shown during transcription) ───────────────────────────
        self._log_box = ctk.CTkTextbox(
            self,
            height=80,
            font=ctk.CTkFont(family="Courier New", size=11),
            state="disabled",
        )
        self._log_box.pack(fill="x", padx=14, pady=(0, 6))

        # ── Path label ────────────────────────────────────────────────────────
        self._path_label = ctk.CTkLabel(
            self,
            text="No transcript loaded.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._path_label.pack(fill="x", padx=14, pady=(0, 4))

        # ── Transcript text box ───────────────────────────────────────────────
        self._textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier New", size=13),
            wrap="word",
            state="disabled",
        )
        self._textbox.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        # ── Output action buttons ─────────────────────────────────────────────
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(0, 10))

        self._open_folder_btn = ctk.CTkButton(
            action_row,
            text="Open Output Folder",
            width=160,
            state="disabled",
            command=self._open_output_folder,
        )
        self._open_folder_btn.pack(side="left", padx=(0, 6))

        self._open_transcript_btn = ctk.CTkButton(
            action_row,
            text="Open Transcript",
            width=140,
            state="disabled",
            command=self._open_transcript_file,
        )
        self._open_transcript_btn.pack(side="left")

    # ── Public API — called by TranscribeTab ──────────────────────────────────

    def append_log(self, msg: str):
        """Append a line to the job log. Safe to call from any thread via after()."""
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def set_status(self, text: str, color: str = "gray"):
        """Update the status label text and colour."""
        self._status_label.configure(text=text, text_color=color)

    def set_transcription_running(self):
        """Called when a transcription job starts."""
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self.set_status("Transcription running…", "white")
        self._open_folder_btn.configure(state="disabled")
        self._open_transcript_btn.configure(state="disabled")
        self._copy_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._path_label.configure(text="Processing…", text_color="gray")

    def set_transcription_complete(self, transcript_path: str, folder_path: str):
        """Called when transcription finishes successfully."""
        self._current_folder_path = folder_path
        self.set_status("✓ Transcription complete", "#44FF44")
        self._open_folder_btn.configure(state="normal")
        self._open_transcript_btn.configure(state="normal")
        self.load_transcript(transcript_path)

    def set_transcription_failed(self, error_msg: str):
        """Called when transcription fails."""
        self.set_status(f"Failed: {error_msg[:80]}", "#FF4444")

    # ── Transcript loading ────────────────────────────────────────────────────

    def load_transcript(self, filepath: str):
        """Load a transcript file into the text box."""
        if not filepath or not os.path.isfile(filepath):
            return
        try:
            content = self._read_transcript(filepath)
            self._current_path = filepath
            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")
            self._textbox.insert("1.0", content)
            self._textbox.configure(state="disabled")
            self._path_label.configure(text=f"Loaded: {filepath}", text_color="gray")
            self._copy_btn.configure(state="normal")
            self._save_btn.configure(state="normal")
        except Exception as exc:
            self._path_label.configure(
                text=f"Failed to load: {exc}", text_color="#CC4444"
            )

    def _read_transcript(self, filepath: str) -> str:
        if filepath.lower().endswith(".docx"):
            from docx import Document
            doc = Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs)
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    # ── Actions ───────────────────────────────────────────────────────────────

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

    def _open_transcript_file(self):
        if self._current_path and os.path.isfile(self._current_path):
            try:
                os.startfile(self._current_path)
                return
            except OSError:
                pass
        self._browse_transcript_file()


    def _open_output_folder(self):
        import subprocess
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
            content = self._textbox.get("1.0", "end")
            with open(self._current_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._save_btn.configure(text="Saved")
            self.after(2000, lambda: self._save_btn.configure(text=" Save"))
        except Exception as exc:
            self._path_label.configure(
                text=f"Save failed: {exc}", text_color="#CC4444"
            )
