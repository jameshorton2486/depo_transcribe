import os

import customtkinter as ctk


class TranscriptTab(ctk.CTkFrame):
    """
    Displays the completed transcript inside the application.
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._current_path = None
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            header,
            text="Transcript",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")

        self._open_btn = ctk.CTkButton(
            header,
            text="📂 Open File",
            width=110,
            command=self._open_transcript_file,
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

        self._textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier New", size=13),
            wrap="word",
            state="disabled",
        )
        self._textbox.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def load_transcript(self, filepath: str):
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
            self._path_label.configure(text=f"Failed to load: {exc}", text_color="#CC4444")

    def _read_transcript(self, filepath: str) -> str:
        if filepath.lower().endswith(".docx"):
            from docx import Document

            doc = Document(filepath)
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)

        with open(filepath, "r", encoding="utf-8") as handle:
            return handle.read()

    def _open_transcript_file(self):
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
