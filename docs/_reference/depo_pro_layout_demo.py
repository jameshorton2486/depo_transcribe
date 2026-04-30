import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog
import time
import threading

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class DepoProApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DEPO-PRO TRANSCRIBE")
        self.geometry("1000x800")
        self.configure(fg_color="#0f172a")
        self.is_processing = False
        self.current_progress = 0
        self.create_header()
        self.create_main_container()
        self.create_footer()

    def create_header(self):
        header = ctk.CTkFrame(self, height=70, corner_radius=0, fg_color="#1e293b", border_width=1, border_color="#334155")
        header.pack(fill="x", side="top")
        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.pack(side="left", padx=20)
        title_label = ctk.CTkLabel(logo_frame, text="DEPO-PRO ", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
        title_label.pack(side="left")
        subtitle_label = ctk.CTkLabel(logo_frame, text="TRANSCRIBE", font=ctk.CTkFont(size=18, weight="bold"), text_color="#60a5fa")
        subtitle_label.pack(side="left")
        version_label = ctk.CTkLabel(header, text="v3.2 PRO", font=ctk.CTkFont(size=10, weight="bold"), text_color="#94a3b8")
        version_label.pack(side="right", padx=20)

    def create_main_container(self):
        self.container = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.container.pack(fill="both", expand=True, padx=40, pady=20)
        self.create_section_title(self.container, "1. SOURCE MEDIA", "#60a5fa")
        source_frame = ctk.CTkFrame(self.container, fg_color="#1e293b", border_width=1, border_color="#334155")
        source_frame.pack(fill="x", pady=(5, 20), ipady=10)
        self.file_path_var = tk.StringVar(value="C:/Users/james/Downloads/04-09-26 Biana Caram MD 01_1.mp3")
        path_entry = ctk.CTkEntry(source_frame, textvariable=self.file_path_var, width=600, height=40, fg_color="#0f172a", border_color="#334155")
        path_entry.pack(side="left", padx=(20, 10), fill="x", expand=True)
        browse_btn = ctk.CTkButton(source_frame, text="Browse", width=100, height=40, font=ctk.CTkFont(weight="bold"))
        browse_btn.pack(side="left", padx=(0, 10))
        batch_btn = ctk.CTkButton(source_frame, text="Batch...", width=100, height=40, fg_color="#334155", hover_color="#475569")
        batch_btn.pack(side="left", padx=(0, 20))
        grid_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        grid_frame.pack(fill="x")
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=2)
        config_col = ctk.CTkFrame(grid_frame, fg_color="transparent")
        config_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.create_section_title(config_col, "2. ENGINE CONFIG", "#c084fc")
        config_card = ctk.CTkFrame(config_col, fg_color="#1e293b", border_width=1, border_color="#334155")
        config_card.pack(fill="both", expand=True, pady=(5, 0), ipady=15)
        ctk.CTkLabel(config_card, text="MODEL", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").pack(anchor="w", padx=20, pady=(15, 0))
        ctk.CTkComboBox(config_card, values=["Nova-3 (Ultra Precision)", "Nova-2 (Fast)", "Whisper-V3"], height=35, fg_color="#0f172a", border_color="#334155").pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(config_card, text="PROCESSING MODE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").pack(anchor="w", padx=20, pady=(15, 0))
        ctk.CTkComboBox(config_card, values=["ENHANCED (Fair Audio)", "STANDARD (Clean Audio)", "ISOLATED"], height=35, fg_color="#0f172a", border_color="#334155").pack(fill="x", padx=20, pady=5)
        info_box = ctk.CTkFrame(config_card, fg_color="#1e293b", border_width=1, border_color="#1d4ed8")
        info_box.pack(fill="x", padx=20, pady=20)
        ctk.CTkLabel(info_box, text="Est. Time: ~4m 30s", font=ctk.CTkFont(size=11), text_color="#93c5fd").pack(pady=5)
        details_col = ctk.CTkFrame(grid_frame, fg_color="transparent")
        details_col.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.create_section_title(details_col, "3. DEPOSITION DETAILS", "#34d399")
        details_card = ctk.CTkFrame(details_col, fg_color="#1e293b", border_width=1, border_color="#334155")
        details_card.pack(fill="both", expand=True, pady=(5, 0), ipady=10)
        meta_grid = ctk.CTkFrame(details_card, fg_color="transparent")
        meta_grid.pack(fill="x", padx=20, pady=10)
        meta_grid.columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(meta_grid, text="CAUSE NUMBER", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(meta_grid, placeholder_text="e.g. CV-2024", height=35, fg_color="#0f172a", border_color="#334155").grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=(0, 10))
        ctk.CTkLabel(meta_grid, text="DEPOSITION DATE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").grid(row=0, column=1, sticky="w")
        ctk.CTkEntry(meta_grid, placeholder_text="MM/DD/YYYY", height=35, fg_color="#0f172a", border_color="#334155").grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=(0, 10))
        ctk.CTkLabel(meta_grid, text="FIRST NAME", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").grid(row=2, column=0, sticky="w")
        ctk.CTkEntry(meta_grid, height=35, fg_color="#0f172a", border_color="#334155").grid(row=3, column=0, sticky="ew", padx=(0, 5), pady=(0, 10))
        ctk.CTkLabel(meta_grid, text="LAST NAME", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").grid(row=2, column=1, sticky="w")
        ctk.CTkEntry(meta_grid, height=35, fg_color="#0f172a", border_color="#334155").grid(row=3, column=1, sticky="ew", padx=(5, 0), pady=(0, 10))
        ctk.CTkLabel(details_card, text="SAVE LOCATION", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").pack(anchor="w", padx=20)
        loc_frame = ctk.CTkFrame(details_card, fg_color="transparent")
        loc_frame.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkEntry(loc_frame, placeholder_text="C:/Output", height=35, fg_color="#0f172a", border_color="#334155").pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(loc_frame, text="Change", width=80, height=35, fg_color="#334155").pack(side="left")
        self.action_hub = ctk.CTkFrame(self.container, fg_color="#1e293b", border_width=1, border_color="#334155")
        self.action_hub.pack(fill="x", pady=20, ipady=15)
        self.status_label = ctk.CTkLabel(self.action_hub, text="Ready to Process", font=ctk.CTkFont(size=16, weight="bold"))
        self.status_label.pack(anchor="w", padx=30, pady=(20, 0))
        self.sub_status = ctk.CTkLabel(self.action_hub, text="All parameters set. Review details before starting.", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        self.sub_status.pack(anchor="w", padx=30)
        self.progress_bar = ctk.CTkProgressBar(self.action_hub, height=10, border_width=0, progress_color="#2563eb")
        self.progress_bar.pack(fill="x", padx=30, pady=20)
        self.progress_bar.set(0)
        self.start_btn = ctk.CTkButton(self.action_hub, text="Start Transcription", height=50, width=250, font=ctk.CTkFont(weight="bold"))
        self.start_btn.pack(pady=(0, 20))
        utils_frame = ctk.CTkFrame(self.action_hub, fg_color="transparent")
        utils_frame.pack(fill="x", padx=30, pady=(10, 10))
        btn_config = {"height": 35, "fg_color": "#0f172a", "border_width": 1, "border_color": "#334155", "text_color": "#cbd5e1"}
        ctk.CTkButton(utils_frame, text="Reporter Notes", **btn_config).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(utils_frame, text="Output Folder", **btn_config).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(utils_frame, text="View Transcript", **btn_config).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(utils_frame, text="Review & Edit", height=35, fg_color="#1e40af", text_color="white", font=ctk.CTkFont(weight="bold")).pack(side="left", expand=True, padx=5)

    def create_section_title(self, parent, text, color):
        lbl = ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12, weight="bold"), text_color=color)
        lbl.pack(anchor="w", pady=(10, 0))

    def create_footer(self):
        footer = ctk.CTkFrame(self, height=30, corner_radius=0, fg_color="#0f172a", border_width=1, border_color="#1e293b")
        footer.pack(fill="x", side="bottom")
        status_dot = ctk.CTkLabel(footer, text="● SYSTEM ONLINE", font=ctk.CTkFont(size=9, weight="bold"), text_color="#10b981")
        status_dot.pack(side="left", padx=20)
        license_lbl = ctk.CTkLabel(footer, text="LICENSE: ENTERPRISE PRO", font=ctk.CTkFont(size=9), text_color="#475569")
        license_lbl.pack(side="right", padx=20)


if __name__ == "__main__":
    app = DepoProApp()
    app.mainloop()
