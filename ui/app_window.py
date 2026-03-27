"""
ui/app_window.py

Main application window for Depo-Pro Transcribe.
Single-screen layout with the Transcribe tab as the only content area.
"""

import customtkinter as ctk
from config import DEEPGRAM_API_KEY
from ui.tab_transcribe import TranscribeTab


class DepoTranscribeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # -- Window setup ----------------------------------------------------------
        self.title("Depo-Pro Transcribe")
        self.geometry("1000x700")
        self.minsize(800, 600)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

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

        # -- Main content area (Transcribe tab) ------------------------------------
        self.transcribe_tab = TranscribeTab(self)
        self.transcribe_tab.pack(fill="both", expand=True, padx=10, pady=10)
