"""
ui/app_window.py

Main application window for Depo-Pro Transcribe.
Single-screen layout with the Transcribe tab as the only content area.
"""

import customtkinter as ctk
from config import DEEPGRAM_API_KEY
from ui.tab_training import TrainingTab
from ui.tab_transcript import TranscriptTab
from ui.tab_transcribe import TranscribeTab
from ui.tab_corrections import CorrectionsTab


class DepoTranscribeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # -- Window setup ----------------------------------------------------------
        self.title("Depo-Pro Transcribe")
        self.geometry("1000x900")
        self.minsize(900, 800)
        self.state("zoomed")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)

        # -- Dark navy header bar --------------------------------------------------
        header = ctk.CTkFrame(self, height=50, fg_color="#1E3A5F", corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="DEPO-PRO TRANSCRIBE",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white",
        ).pack(side="left", padx=20, pady=10)

        # -- API key warning -------------------------------------------------------
        if not DEEPGRAM_API_KEY or not DEEPGRAM_API_KEY.strip():
            warning = ctk.CTkLabel(
                header,
                text="WARNING: DEEPGRAM_API_KEY not set",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#FF4444",
            )
            warning.pack(side="right", padx=20, pady=10)

        # -- Main content area ------------------------------------------------------
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_view.add("Transcribe")
        self.tab_view.add("Transcript")
        self.tab_view.add("Corrections")
        self.tab_view.add("Training")

        self.transcribe_tab = TranscribeTab(self.tab_view.tab("Transcribe"))
        self.transcribe_tab.pack(fill="both", expand=True)

        self.transcript_tab = TranscriptTab(self.tab_view.tab("Transcript"))
        self.transcript_tab.pack(fill="both", expand=True)

        self.corrections_tab = CorrectionsTab(self.tab_view.tab("Corrections"))
        self.corrections_tab.pack(fill="both", expand=True)

        self.training_tab = TrainingTab(self.tab_view.tab("Training"))
        self.training_tab.pack(fill="both", expand=True)

        self.tab_view.configure(command=self._on_tab_change)

    def _on_tab_change(self):
        if self.tab_view.get() == "Training":
            self.training_tab.on_tab_focus()
