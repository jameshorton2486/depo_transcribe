import os
import subprocess

import customtkinter as ctk


class TranscriptTab(ctk.CTkFrame):
    """
    Displays the completed transcript inside the application.
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._current_path = None
        self._last_transcript_path = None
        self._last_folder_path = None
        self._build_ui()

    def _build_ui(self):
        self._log_box = ctk.CTkTextbox(
            self,
            height=120,
            font=ctk.CTkFont(family="Courier New", size=12),
            fg_color="#0D1117",
            state="disabled",
        )
        self._log_box.pack(fill="x", padx=16, pady=(12, 4))

        self._status_label = ctk.CTkLabel(
            self,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=16, pady=(0, 4))

        self._create_btn = ctk.CTkButton(
            self,
            text=" CREATE TRANSCRIPT",
            height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#C8860A",
            hover_color="#A06A08",
            command=self._start_transcription,
        )
        self._create_btn.pack(fill="x", padx=16, pady=(4, 8))

        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(0, 8))

        self._open_folder_btn = ctk.CTkButton(
            action_row,
            text="Open Output Folder",
            width=160,
            state="disabled",
            command=self._open_output_folder,
        )
        self._open_folder_btn.pack(side="left", padx=(0, 4))

        self._open_transcript_btn = ctk.CTkButton(
            action_row,
            text="Open Transcript",
            width=150,
            state="disabled",
            command=self._open_transcript_file,
        )
        self._open_transcript_btn.pack(side="left")

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(
            header,
            text="Transcript",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")

        self._open_btn = ctk.CTkButton(
            header,
            text="📂 Open File",
            width=110,
            command=self._browse_transcript_file,
        )
        self._open_btn.pack(side="right", padx=(4, 0))

        self._copy_btn = ctk.CTkButton(
            header,
            text="📋 Copy All",
            width=110,
            command=self._copy_all,
            state="disabled",
        )
        self._copy_btn.pack(side="right", padx=(4, 0))

        self._save_btn = ctk.CTkButton(
            header,
            text="💾 Save",
            width=90,
            command=self._save_transcript,
            state="disabled",
        )
        self._save_btn.pack(side="right", padx=(4, 0))

        self._path_label = ctk.CTkLabel(
            self,
            text="No transcript loaded.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._path_label.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(
            self,
            text="TRANSCRIPT PREVIEW",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(4, 2))

        self._textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier New", size=13),
            wrap="word",
            state="disabled",
        )
        self._textbox.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def append_log(self, message: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def set_status(self, text: str, color: str = "gray"):
        self._status_label.configure(text=text, text_color=color)

    def load_transcript(self, filepath: str):
        if not filepath or not os.path.isfile(filepath):
            return

        try:
            content = self._read_transcript(filepath)
            self._current_path = filepath
            self._last_transcript_path = filepath
            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")
            self._textbox.insert("1.0", content)
            self._textbox.configure(state="disabled")
            self._path_label.configure(text=f"Loaded: {filepath}", text_color="gray")
            self._copy_btn.configure(state="normal")
            self._save_btn.configure(state="normal")
            self._open_transcript_btn.configure(state="normal")
            self._open_folder_btn.configure(
                state="normal" if self._last_folder_path and os.path.isdir(self._last_folder_path) else "disabled"
            )
        except Exception as exc:
            self.set_status(f"Failed to load transcript: {exc}", "#CC4444")
            self._path_label.configure(text=f"Failed to load: {exc}", text_color="#CC4444")

    def set_transcription_running(self):
        self._create_btn.configure(state="disabled", text=" Transcribing...")
        self._open_folder_btn.configure(state="disabled")
        self._open_transcript_btn.configure(state="disabled")
        self._copy_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self.clear_log()
        self.set_status("Starting...", "white")
        self._path_label.configure(text="No transcript loaded.", text_color="gray")
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")

    def set_transcription_complete(self, transcript_path: str, folder_path: str):
        self._last_transcript_path = transcript_path
        self._last_folder_path = folder_path
        self.load_transcript(transcript_path)
        self._create_btn.configure(state="normal", text=" CREATE TRANSCRIPT")
        self.set_status("Transcription complete.", "#44FF44")

    def set_transcription_failed(self, error_message: str):
        self._create_btn.configure(state="normal", text=" CREATE TRANSCRIPT")
        self.set_status("Failed", "#FF4444")
        self.append_log(f"Transcription failed: {error_message}")

    def _read_transcript(self, filepath: str) -> str:
        if filepath.lower().endswith(".docx"):
            from docx import Document

            doc = Document(filepath)
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)

        with open(filepath, "r", encoding="utf-8") as handle:
            return handle.read()

    def _browse_transcript_file(self):
        from tkinter import filedialog

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

    def _start_transcription(self):
        app = self.winfo_toplevel()
        app.transcribe_tab.start_transcription()

    def _open_output_folder(self):
        if self._last_folder_path and os.path.isdir(self._last_folder_path):
            subprocess.Popen(f'explorer "{self._last_folder_path}"')

    def _open_transcript_file(self):
        if self._last_transcript_path and os.path.isfile(self._last_transcript_path):
            subprocess.Popen(["notepad.exe", self._last_transcript_path])

    def _copy_all(self):
        content = self._textbox.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self._copy_btn.configure(text="Copied")
            self.after(2000, lambda: self._copy_btn.configure(text="📋 Copy All"))

    def _save_transcript(self):
        if not self._current_path:
            return

        try:
            content = self._textbox.get("1.0", "end")
            with open(self._current_path, "w", encoding="utf-8") as handle:
                handle.write(content)
            self._save_btn.configure(text="Saved")
            self.after(2000, lambda: self._save_btn.configure(text="💾 Save"))
        except Exception as exc:
            self._path_label.configure(text=f"Save failed: {exc}", text_color="#CC4444")
