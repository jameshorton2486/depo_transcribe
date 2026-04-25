"""
ui/tab_corrections.py

Corrections tab — run the deterministic correction pipeline on a completed
transcript and review the results in-app.

Workflow:
  1. Source transcript is auto-loaded from the Transcript tab's current file,
     or the reporter can browse to any .txt transcript manually.
  2. "Run Corrections Pipeline" launches core/correction_runner.py in a
     background thread.
  3. Results are displayed in two panels:
       Left  — corrected transcript text (auto-loaded into viewer)
       Right — corrections log (pattern counts + scopist flags)
  4. Save buttons write _corrected.txt and _corrections.json to the
     same Deepgram/ folder as the source.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app_logging import get_logger
from ui._components import (
    BTN_AI_PURPLE,
    BTN_AI_PURPLE_HOVER,
    BTN_UTILITY_BLUE,
    BTN_UTILITY_BLUE_HOVER,
)

logger = get_logger(__name__)

_TEAL = "#0F5A6A"
_TEAL_HOVER = "#0A3A4A"
_GREEN = "#1F5A2A"
_GREEN_HOV = "#155020"
_AMBER = "#B8860B"
_AMBER_HOV = "#9A7209"
_FLAG_COLOR = "#CC9900"


class CorrectionsTab(ctk.CTkFrame):
    """Full corrections pipeline UI — source selection, run, results."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._source_path: str | None = None
        self._corrected_path: str | None = None
        self._corrections_path: str | None = None
        self._docx_path: str | None = None
        self._ai_running: bool = False
        self._ai_text: str = ''
        self._running: bool = False
        self._docx_running: bool = False
        self._source_text: str = ''        # raw text captured at correction time (for diff)

        self._build_ui()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        # ── Source panel ───────────────────────────────────────────────────────
        src_card = ctk.CTkFrame(outer, border_width=1, border_color="#1A3A4A")
        src_card.pack(fill="x", pady=(0, 6))

        src_inner = ctk.CTkFrame(src_card, fg_color="transparent")
        src_inner.pack(fill="x", padx=8, pady=6)

        src_hdr = ctk.CTkFrame(src_inner, fg_color="transparent")
        src_hdr.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            src_hdr, text="Transcript Source",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#7DD8E8",
        ).pack(side="left")

        ctk.CTkLabel(
            src_hdr,
            text="Select a transcript to run corrections on",
            font=ctk.CTkFont(size=10), text_color="#2a4a5a",
        ).pack(side="left", padx=(10, 0))

        # File path row
        src_file_row = ctk.CTkFrame(src_inner, fg_color="transparent")
        src_file_row.pack(fill="x", pady=(0, 4))

        self._source_entry = ctk.CTkEntry(
            src_file_row,
            placeholder_text="Browse to a transcript .txt file, or click 'Use Current'",
            state="disabled",
        )
        self._source_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            src_file_row, text="Browse…", width=80,
            fg_color=BTN_UTILITY_BLUE, hover_color=BTN_UTILITY_BLUE_HOVER,
            command=self._browse_source,
        ).pack(side="right", padx=(0, 4))

        self._use_current_btn = ctk.CTkButton(
            src_file_row, text="Use Current", width=100,
            fg_color=_TEAL, hover_color=_TEAL_HOVER,
            state="disabled",
            command=self._use_current_transcript,
        )
        self._use_current_btn.pack(side="right")

        # Case meta row (populated after source is set)
        self._src_meta_label = ctk.CTkLabel(
            src_inner, text="No source selected",
            font=ctk.CTkFont(size=10), text_color="#334455", anchor="w",
        )
        self._src_meta_label.pack(anchor="w")

        # ── Run row ────────────────────────────────────────────────────────────
        run_row = ctk.CTkFrame(outer, fg_color="transparent")
        run_row.pack(fill="x", pady=(0, 6))

        self._ai_btn = ctk.CTkButton(
            run_row,
            text="AI Correct",
            width=110,
            height=36,
            fg_color=BTN_AI_PURPLE,
            hover_color=BTN_AI_PURPLE_HOVER,
            state="disabled",
            command=self._start_ai_correction,
        )
        self._ai_btn.pack(side="left", padx=(0, 8))

        self._run_btn = ctk.CTkButton(
            run_row,
            text="Run Corrections Pipeline",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=_GREEN, hover_color=_GREEN_HOV,
            state="disabled",
            command=self._start_correction,
        )
        self._run_btn.pack(side="left", padx=(0, 8))

        self._run_status = ctk.CTkLabel(
            run_row, text="",
            font=ctk.CTkFont(size=11, family="Courier New"),
            text_color="#44aa66", anchor="w",
        )
        self._run_status.pack(side="left", fill="x", expand=True)

        # ── Stats row (hidden until results arrive) ────────────────────────────
        self._stats_frame = ctk.CTkFrame(outer, fg_color="transparent")
        self._stats_frame.pack(fill="x", pady=(0, 6))

        self._stat_corrections = self._make_stat_card(
            self._stats_frame, "0", "Corrections applied", "#44cc88")
        self._stat_flags = self._make_stat_card(
            self._stats_frame, "0", "Scopist flags", _FLAG_COLOR)
        self._stat_blocks = self._make_stat_card(
            self._stats_frame, "0", "Blocks processed", "#4488cc")
        self._stat_spellings = self._make_stat_card(
            self._stats_frame, "0", "Spelling corrections", "#8866cc")

        for card in (self._stat_corrections, self._stat_flags,
                     self._stat_blocks, self._stat_spellings):
            card.pack(side="left", expand=True, fill="x", padx=(0, 4))

        # ── Results: two-panel grid ────────────────────────────────────────────
        results_outer = ctk.CTkFrame(outer, fg_color="transparent")
        results_outer.pack(fill="both", expand=True, pady=(0, 6))

        results_outer.columnconfigure(0, weight=1)
        results_outer.columnconfigure(1, weight=1)

        # Left panel — corrected transcript
        left_panel = ctk.CTkFrame(
            results_outer, border_width=1, border_color="#252535")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        left_hdr = ctk.CTkFrame(left_panel, fg_color="#1a1a2a")
        left_hdr.pack(fill="x", padx=4, pady=(4, 0))

        ctk.CTkLabel(
            left_hdr, text="Corrected Transcript",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#c0d0e0",
        ).pack(side="left", padx=8, pady=4)

        self._viewer_source_label = ctk.CTkLabel(
            left_hdr,
            text="Showing: no content loaded",
            font=ctk.CTkFont(size=10),
            text_color="#667788",
        )
        self._viewer_source_label.pack(side="left", padx=(4, 0), pady=4)

        self._open_corrected_btn = ctk.CTkButton(
            left_hdr, text="Open File", width=80, height=22,
            fg_color="transparent", border_width=1, border_color="#334",
            text_color="#8ab", font=ctk.CTkFont(size=10),
            state="disabled",
            command=self._open_corrected_file,
        )
        self._open_corrected_btn.pack(side="right", padx=4, pady=4)

        self._copy_corrected_btn = ctk.CTkButton(
            left_hdr, text="Copy All", width=72, height=22,
            fg_color="transparent", border_width=1, border_color="#334",
            text_color="#8ab", font=ctk.CTkFont(size=10),
            state="disabled",
            command=self._copy_corrected,
        )
        self._copy_corrected_btn.pack(side="right", padx=(0, 2), pady=4)

        self._corrected_textbox = ctk.CTkTextbox(
            left_panel,
            font=ctk.CTkFont(family="Courier New", size=11),
            wrap="word",
            state="disabled",
        )
        self._corrected_textbox.pack(
            fill="both", expand=True, padx=4, pady=(4, 4))

        # Right panel — corrections log
        right_panel = ctk.CTkFrame(
            results_outer, border_width=1, border_color="#252535")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        right_hdr = ctk.CTkFrame(right_panel, fg_color="#1a1a2a")
        right_hdr.pack(fill="x", padx=4, pady=(4, 0))

        ctk.CTkLabel(
            right_hdr, text="Corrections Log",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#c0d0e0",
        ).pack(side="left", padx=8, pady=4)

        self._open_json_btn = ctk.CTkButton(
            right_hdr, text="Open JSON", width=82, height=22,
            fg_color="transparent", border_width=1, border_color="#334",
            text_color="#8ab", font=ctk.CTkFont(size=10),
            state="disabled",
            command=self._open_corrections_json,
        )
        self._open_json_btn.pack(side="right", padx=4, pady=4)

        self._log_textbox = ctk.CTkTextbox(
            right_panel,
            font=ctk.CTkFont(family="Courier New", size=10),
            wrap="word",
            state="disabled",
        )
        self._log_textbox.pack(
            fill="both", expand=True, padx=4, pady=(4, 4))

        # ── Footer actions ─────────────────────────────────────────────────────
        foot = ctk.CTkFrame(outer, fg_color="transparent")
        foot.pack(fill="x", pady=(0, 4))

        self._open_folder_btn = ctk.CTkButton(
            foot, text="Open Output Folder", width=160,
            fg_color="transparent", border_width=1, border_color="#334",
            text_color="#8ab", font=ctk.CTkFont(size=11),
            state="disabled",
            command=self._open_folder,
        )
        self._open_folder_btn.pack(side="left", padx=(0, 6))

        self._load_in_transcript_btn = ctk.CTkButton(
            foot, text="Load in Transcript Tab", width=170,
            fg_color="transparent", border_width=1, border_color="#334",
            text_color="#8ab", font=ctk.CTkFont(size=11),
            state="disabled",
            command=self._load_corrected_in_transcript_tab,
        )
        self._load_in_transcript_btn.pack(side="left")

        self._generate_docx_btn = ctk.CTkButton(
            foot, text="Generate DOCX", width=140,
            fg_color="transparent", border_width=1, border_color="#334",
            text_color="#8ab", font=ctk.CTkFont(size=11),
            state="disabled",
            command=self._start_docx_generation,
        )
        self._generate_docx_btn.pack(side="left", padx=(6, 0))

        self._open_docx_btn = ctk.CTkButton(
            foot, text="Open DOCX", width=120,
            fg_color="transparent", border_width=1, border_color="#334",
            text_color="#8ab", font=ctk.CTkFont(size=11),
            state="disabled",
            command=self._open_docx,
        )
        self._open_docx_btn.pack(side="left", padx=(6, 0))

        self._footer_label = ctk.CTkLabel(
            foot, text="",
            font=ctk.CTkFont(size=10), text_color="#334455", anchor="e",
        )
        self._footer_label.pack(side="right")

    # ── Stat card helper ───────────────────────────────────────────────────────

    def _make_stat_card(self, parent, value: str, label: str, color: str):
        card = ctk.CTkFrame(parent, border_width=1, border_color="#252535",
                            corner_radius=6)
        ctk.CTkLabel(card, text=value,
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=color).pack(padx=10, pady=(6, 0))
        ctk.CTkLabel(card, text=label,
                     font=ctk.CTkFont(size=10),
                     text_color="#556").pack(padx=10, pady=(0, 6))
        return card

    def _update_stat(self, card, value: str):
        """Update the number label inside a stat card."""
        for widget in card.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                current = widget.cget("text")
                # First label is the number (large), second is the label (small)
                if current.isdigit() or current == "0":
                    widget.configure(text=value)
                    return

    def _set_viewer_source(self, text: str, color: str = "#667788"):
        """Show where the transcript viewer content came from."""
        self._viewer_source_label.configure(text=text, text_color=color)

    # ── Public API — called from other tabs ────────────────────────────────────

    def notify_transcript_loaded(self, path: str):
        """
        Called by TranscriptTab when a transcript is loaded.
        Enables the 'Use Current' button.
        """
        if path and os.path.isfile(path):
            self._use_current_btn.configure(state="normal")

    def set_source(self, path: str):
        """Set the source transcript path programmatically."""
        self._load_source(path)

    # ── Source selection ───────────────────────────────────────────────────────

    def _browse_source(self):
        path = filedialog.askopenfilename(
            title="Select Transcript to Correct",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if path:
            self._load_source(path)

    def _use_current_transcript(self):
        """Pull the currently loaded transcript from the Transcript tab."""
        try:
            path = self.winfo_toplevel().transcript_tab._current_path
        except AttributeError:
            path = None

        if path and os.path.isfile(path):
            self._load_source(path)
        else:
            messagebox.showinfo(
                "No transcript loaded",
                "Please open a transcript in the Transcript tab first.",
            )

    def _load_source(self, path: str):
        """Set the source path and update the UI."""
        self._source_path = path
        self._docx_path = None
        self._ai_text = ''

        self._source_entry.configure(state="normal")
        self._source_entry.delete(0, "end")
        self._source_entry.insert(0, path)
        self._source_entry.configure(state="disabled")

        # Build meta description from folder path
        parts = os.path.normpath(path).split(os.sep)
        meta_parts = []
        try:
            cause = parts[-4] if len(parts) >= 4 else ""
            name = parts[-3].replace("_", " ").title() if len(parts) >= 3 else ""
            if cause:
                meta_parts.append(f"Case: {cause}")
            if name:
                meta_parts.append(name)
        except Exception:
            pass
        meta_parts.append(os.path.basename(path))
        self._src_meta_label.configure(
            text="  ·  ".join(meta_parts), text_color="#2a5a3a",
        )

        self._run_btn.configure(state="normal")
        self._ai_btn.configure(state="disabled")
        self._generate_docx_btn.configure(state="disabled")
        self._open_docx_btn.configure(state="disabled")
        self._run_status.configure(text="Ready to run corrections.", text_color="gray")
        self._set_viewer_source(
            "Viewer Source: none (load a transcript to see corrections)",
            "#667788",
        )
        logger.info("[CorrectionsTab] Source set: %s", path)

    # ── Run pipeline ───────────────────────────────────────────────────────────

    def _start_correction(self):
        if self._running or not self._source_path:
            return
        self._running = True
        self._run_btn.configure(state="disabled", text="Running…")
        self._run_status.configure(
            text="Starting corrections pipeline…", text_color="white")

        # Clear previous results
        self._corrected_textbox.configure(state="normal")
        self._corrected_textbox.delete("1.0", "end")
        self._corrected_textbox.configure(state="disabled")
        self._set_viewer_source(
            "Viewer Source: running (waiting for current run output)",
            "#8899AA",
        )
        self._log_textbox.configure(state="normal")
        self._log_textbox.delete("1.0", "end")
        self._log_textbox.configure(state="disabled")
        self._docx_path = None
        self._ai_text = ''
        self._ai_btn.configure(state="disabled")
        self._generate_docx_btn.configure(state="disabled")
        self._open_docx_btn.configure(state="disabled")

        for card in (self._stat_corrections, self._stat_flags,
                     self._stat_blocks, self._stat_spellings):
            self._update_stat(card, "…")

        thread = threading.Thread(target=self._run_job, daemon=True)
        thread.start()

    def _run_job(self):
        from core.correction_runner import run_correction_job
        from pathlib import Path

        # Capture raw text now so we can diff after corrections
        try:
            self._source_text = Path(self._source_path).read_text(encoding="utf-8")
        except Exception:
            self._source_text = ''

        run_correction_job(
            transcript_path=self._source_path,
            progress_callback=lambda msg: self.after(0, self._on_progress, msg),
            done_callback=lambda result: self.after(0, self._on_done, result),
        )

    def _on_progress(self, msg: str):
        self._run_status.configure(text=msg, text_color="white")
        self._append_log(f"  {msg}")

    def _on_done(self, result: dict):
        self._running = False
        self._run_btn.configure(state="normal", text="Run Corrections Pipeline")

        if result.get("success"):
            n_corr = result.get("correction_count", 0)
            n_flags = result.get("flag_count", 0)
            corr_path = result.get("corrected_path", "")
            json_path = result.get("corrections_path", "")
            corr_text = result.get("corrected_text", "")

            self._corrected_path = corr_path
            self._corrections_path = json_path

            status = f"✓ {n_corr} corrections applied"
            if n_flags:
                status += f"  ·  {n_flags} scopist flags"
            self._run_status.configure(text=status, text_color="#44FF44")

            # Update stats
            self._update_stat(self._stat_corrections, str(n_corr))
            self._update_stat(self._stat_flags, str(n_flags))

            # Load corrected text into viewer
            self._corrected_textbox.configure(state="normal")
            self._corrected_textbox.delete("1.0", "end")
            if corr_text:
                self._corrected_textbox.insert("1.0", corr_text)
                self._set_viewer_source("Viewer Source: current run output", "#2a7a4a")
            elif corr_path and os.path.isfile(corr_path):
                self._corrected_textbox.insert(
                    "1.0",
                    Path(corr_path).read_text(encoding="utf-8"),
                )
                self._set_viewer_source(
                    f"Viewer Source: saved corrected file ({os.path.basename(corr_path)})",
                    "#B8860B",
                )
                self._append_log(
                    "Viewer source: saved corrected file fallback "
                    "(current run returned no inline corrected_text)."
                )
            else:
                self._set_viewer_source(
                    "Viewer Source: none (no corrected text available)",
                    "#AA5555",
                )
            self._corrected_textbox.configure(state="disabled")

            # Load corrections JSON into log panel
            self._load_corrections_json_into_log(json_path)

            # ── Diff summary ─────────────────────────────────────────────────
            if self._source_text and corr_text:
                try:
                    from core.diff_engine import summary as diff_summary
                    d = diff_summary(self._source_text, corr_text)
                    if d["total_changes"]:
                        self._append_log(
                            f"\n── Diff Summary ──────────────────────────\n"
                            f"  Lines changed:  {d['replaces']}\n"
                            f"  Lines added:    {d['inserts']}\n"
                            f"  Lines removed:  {d['deletes']}\n"
                            f"──────────────────────────────────────────"
                        )
                except Exception as exc:
                    logger.debug("[CorrectionsTab] Diff summary failed: %s", exc)

            # ── Low-confidence words from job_config ──────────────────────────
            if corr_path:
                try:
                    from pathlib import Path as _Path
                    from core.job_config_manager import load_job_config
                    case_root = str(_Path(corr_path).parent.parent)
                    jc = load_job_config(case_root)
                    low_conf = jc.get("low_confidence_words", [])
                    if low_conf:
                        lines = [f"\n── Low-Confidence Words ({len(low_conf)}) ─────"]
                        for w in low_conf[:20]:
                            lines.append(
                                f"  {w['word']:20s}  {w['confidence']:.2f}  "
                                f"@ {w['start']:.1f}s"
                            )
                        if len(low_conf) > 20:
                            lines.append(f"  … and {len(low_conf) - 20} more")
                        lines.append("──────────────────────────────────────────")
                        self._append_log("\n".join(lines))
                        self._update_stat(self._stat_spellings, str(len(low_conf)))
                except Exception as exc:
                    logger.debug("[CorrectionsTab] Low-conf load failed: %s", exc)

            # Enable action buttons
            self._open_corrected_btn.configure(state="normal")
            self._copy_corrected_btn.configure(state="normal")
            self._open_json_btn.configure(state="normal")
            self._open_folder_btn.configure(state="normal")
            self._load_in_transcript_btn.configure(state="normal")
            self._ai_btn.configure(state="normal")
            self._generate_docx_btn.configure(state="normal")
            self._open_docx_btn.configure(state="disabled")

            folder = str(Path(corr_path).parent) if corr_path else ""
            self._footer_label.configure(
                text=f"Saved to: {folder}", text_color="#2a5a3a",
            )

            logger.info(
                "[CorrectionsTab] Complete: %d corrections, %d flags",
                n_corr, n_flags,
            )

        else:
            error = result.get("error", "Unknown error")
            self._run_status.configure(
                text=f"Failed: {error[:80]}", text_color="#FF4444")
            self._set_viewer_source(
                "Viewer Source: none (corrections failed)",
                "#AA5555",
            )
            self._append_log(f"ERROR: {error}")
            for card in (self._stat_corrections, self._stat_flags,
                         self._stat_blocks, self._stat_spellings):
                self._update_stat(card, "—")

    def _start_docx_generation(self):
        if self._docx_running:
            return
        if not self._corrected_path or not os.path.isfile(self._corrected_path):
            messagebox.showerror(
                "No corrected transcript",
                "Run the corrections pipeline before generating a DOCX.",
            )
            return

        self._docx_running = True
        self._generate_docx_btn.configure(state="disabled", text="Generating…")
        self._open_docx_btn.configure(state="disabled")
        self._run_status.configure(text="Generating formatted DOCX…", text_color="white")
        self._append_log("Starting DOCX generation…")
        threading.Thread(target=self._run_docx_job, daemon=True).start()

    def _run_docx_job(self):
        from core.docx_formatter import format_transcript_to_docx

        try:
            output_path = format_transcript_to_docx(
                self._corrected_path,
                progress_callback=lambda msg: self.after(0, self._append_log, msg),
            )
            self.after(0, self._on_docx_done, {"success": True, "docx_path": output_path})
        except Exception as exc:
            logger.exception("[CorrectionsTab] DOCX generation failed: %s", exc)
            self.after(0, self._on_docx_done, {"success": False, "error": str(exc)})

    def _on_docx_done(self, result: dict):
        self._docx_running = False
        self._generate_docx_btn.configure(state="normal", text="Generate DOCX")

        if result.get("success"):
            self._docx_path = result.get("docx_path")
            name = os.path.basename(self._docx_path or "")
            self._run_status.configure(text=f"✓ DOCX ready: {name}", text_color="#44FF44")
            self._open_docx_btn.configure(state="normal")
            self._append_log(f"Saved DOCX: {name}")
        else:
            error = result.get("error", "Unknown error")
            self._run_status.configure(text=f"DOCX failed: {error[:80]}", text_color="#FF4444")
            self._append_log(f"ERROR: {error}")

    # ── AI correction ──────────────────────────────────────────────────────────

    def _start_ai_correction(self):
        """Launch the AI correction pass in a background thread."""
        if self._ai_running:
            return

        corrected_text = self._corrected_textbox.get('1.0', 'end').strip()
        if not corrected_text:
            from tkinter import messagebox
            messagebox.showinfo(
                'No text',
                'Run the corrections pipeline first, then click AI Correct.',
            )
            return

        self._ai_running = True
        self._ai_btn.configure(state='disabled', text='AI Running…')
        self._run_status.configure(
            text='Running AI correction pass (Claude API)…',
            text_color='white',
        )
        self._append_log('Starting AI correction pass…')

        import threading
        threading.Thread(
            target=self._run_ai_job,
            args=(corrected_text,),
            daemon=True,
        ).start()

    def _run_ai_job(self, corrected_text: str):
        from spec_engine.ai_corrector import run_ai_correction

        try:
            source = self._source_path or ''
            from core.correction_runner import _load_job_config_for_transcript, _build_job_config_from_ufm
            job_config_data = _load_job_config_for_transcript(source)
            job_config = _build_job_config_from_ufm(job_config_data) if job_config_data else None
        except Exception:
            job_config = None

        try:
            result_text = run_ai_correction(
                transcript_text=corrected_text,
                job_config=job_config or {},
                progress_callback=lambda msg: self.after(0, self._append_log, msg),
            )
            self.after(0, self._on_ai_done, result_text, None)
        except Exception as exc:
            self.after(0, self._on_ai_done, None, str(exc))

    def _on_ai_done(self, result_text: str | None, error: str | None):
        self._ai_running = False
        self._ai_btn.configure(state='normal', text='AI Correct')

        if result_text and not error:
            self._ai_text = result_text
            if self._corrected_path:
                Path(self._corrected_path).write_text(result_text, encoding="utf-8")
            self._corrected_textbox.configure(state='normal')
            self._corrected_textbox.delete('1.0', 'end')
            self._corrected_textbox.insert('1.0', result_text)
            self._corrected_textbox.configure(state='disabled')
            self._set_viewer_source(
                "Viewer Source: AI-corrected textbox content",
                "#3B6EA5",
            )
            self._run_status.configure(
                text='✓ AI correction complete',
                text_color='#44FF44',
            )
            self._append_log('AI correction applied to transcript viewer.')
            self._append_log(
                'Click "Generate DOCX" to export the AI-corrected version.'
            )
        else:
            self._run_status.configure(
                text=f'AI correction failed: {(error or "unknown")[:60]}',
                text_color='#FF4444',
            )
            self._append_log(f'ERROR: {error}')

    def _load_corrections_json_into_log(self, json_path: str | None):
        """Parse _corrections.json and display a formatted summary."""
        if not json_path or not os.path.isfile(json_path):
            return

        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return

        self._log_textbox.configure(state="normal")
        self._log_textbox.delete("1.0", "end")

        corrections = data.get("corrections", [])
        flag_count = data.get("flag_count", 0)

        # Update block count stat
        block_indices = {c.get("block_index", 0) for c in corrections}
        self._update_stat(self._stat_blocks, str(len(block_indices)))

        # Count patterns
        pattern_counts: dict[str, int] = {}
        spelling_count = 0
        flag_texts: list[str] = []

        for c in corrections:
            pattern = c.get("pattern", "unknown")
            if "confirmed_spelling" in pattern:
                spelling_count += 1
                short = pattern.replace("confirmed_spelling:", "spelling: ")
            elif "SCOPIST" in c.get("corrected", ""):
                flag_texts.append(c.get("corrected", ""))
                continue
            else:
                short = pattern
            pattern_counts[short] = pattern_counts.get(short, 0) + 1

        self._update_stat(self._stat_spellings, str(spelling_count))

        # Write top patterns
        self._log_textbox.insert("end", "TOP CORRECTION PATTERNS\n")
        self._log_textbox.insert("end", "─" * 36 + "\n")
        for pattern, count in sorted(
            pattern_counts.items(), key=lambda x: -x[1]
        )[:15]:
            self._log_textbox.insert(
                "end", f"  {pattern[:30]:<30} {count:>4}×\n")

        # Write scopist flags
        if flag_count or flag_texts:
            self._log_textbox.insert("end", "\nSCOPIST FLAGS\n")
            self._log_textbox.insert("end", "─" * 36 + "\n")
            for i, text in enumerate(flag_texts[:20], 1):
                # Extract the flag description from the inline text
                clean = text.replace("[SCOPIST:", "").replace("]", "").strip()
                self._log_textbox.insert("end", f"  FLAG {i}: {clean[:60]}\n")

        self._log_textbox.configure(state="disabled")

    # ── Log helper ─────────────────────────────────────────────────────────────

    def _append_log(self, msg: str):
        self._log_textbox.configure(state="normal")
        self._log_textbox.insert("end", msg + "\n")
        self._log_textbox.see("end")
        self._log_textbox.configure(state="disabled")

    # ── Action buttons ─────────────────────────────────────────────────────────

    def _open_corrected_file(self):
        if self._corrected_path and os.path.isfile(self._corrected_path):
            import subprocess
            subprocess.Popen(f'explorer /select,"{self._corrected_path}"')

    def _open_corrections_json(self):
        if self._corrections_path and os.path.isfile(self._corrections_path):
            import subprocess
            subprocess.Popen(["notepad.exe", self._corrections_path])

    def _open_folder(self):
        path = self._corrected_path or self._source_path
        if path:
            folder = str(Path(path).parent)
            subprocess.Popen(f'explorer "{folder}"')

    def _copy_corrected(self):
        content = self._corrected_textbox.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)

    def _load_corrected_in_transcript_tab(self):
        """Switch to Transcript tab and load the corrected file there."""
        if not self._corrected_path or not os.path.isfile(self._corrected_path):
            return
        try:
            app = self.winfo_toplevel()
            app.transcript_tab.load_transcript(self._corrected_path)
            app.tab_view.set("Transcript")
        except Exception as exc:
            logger.error("[CorrectionsTab] Could not load in Transcript tab: %s", exc)

    def _open_docx(self):
        if self._docx_path and os.path.isfile(self._docx_path):
            subprocess.Popen(["start", "", self._docx_path], shell=True)
