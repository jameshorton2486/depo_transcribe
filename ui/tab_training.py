"""
ui/tab_training.py

Training Engine tab — teaches the correction system new rules from examples.
"""

from __future__ import annotations

import subprocess
import threading

import customtkinter as ctk

from ui._components import make_section_header


class TrainingTab(ctk.CTkFrame):
    _TEAL = "#0F5A6A"
    _TEAL_HOVER = "#0A3A4A"
    _AMBER = "#B8860B"
    _AMBER_HOVER = "#9A7209"
    _GREEN = "#1F5A2A"
    _GREEN_HOV = "#155020"

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._proposed_rules: list[dict] = []
        self._generating: bool = False
        self._build_ui()

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        ctk.CTkLabel(
            outer,
            text="Training Engine",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            outer,
            text="Teach the system to recognize and correct transcript patterns automatically.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", pady=(0, 8))

        # ── STEP 1 — paste a before/after example ────────────────────────────
        make_section_header(outer, "STEP 1 — Paste a before/after example").pack(
            anchor="w", pady=(0, 2)
        )

        input_row = ctk.CTkFrame(outer, fg_color="transparent")
        input_row.pack(fill="x", pady=(0, 8))
        input_row.grid_columnconfigure(0, weight=1)
        input_row.grid_columnconfigure(1, weight=1)

        left_panel = ctk.CTkFrame(input_row, border_width=1, border_color="#1A3A4A")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ctk.CTkLabel(
            left_panel,
            text="Incorrect Text",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#7DD8E8",
        ).pack(anchor="w", padx=8, pady=(8, 0))
        ctk.CTkLabel(
            left_panel,
            text="Paste raw Deepgram output",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=8, pady=(0, 6))
        self._incorrect_box = ctk.CTkTextbox(
            left_panel,
            height=130,
            font=ctk.CTkFont(family="Courier New", size=11),
        )
        self._incorrect_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        right_panel = ctk.CTkFrame(input_row, border_width=1, border_color="#1A3A4A")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ctk.CTkLabel(
            right_panel,
            text="Corrected Text",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#7DD8E8",
        ).pack(anchor="w", padx=8, pady=(8, 0))
        ctk.CTkLabel(
            right_panel,
            text="Paste the corrected version",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", padx=8, pady=(0, 6))
        self._correct_box = ctk.CTkTextbox(
            right_panel,
            height=130,
            font=ctk.CTkFont(family="Courier New", size=11),
        )
        self._correct_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ── STEP 2 — add context (optional) ──────────────────────────────────
        make_section_header(outer, "STEP 2 — Add context (optional)").pack(
            anchor="w", pady=(0, 2)
        )
        ctk.CTkLabel(
            outer,
            text="Rule Instruction",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            outer,
            text='Describe the rule — e.g. "Always correct subpoena deuces tecum spelling"',
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(anchor="w", pady=(0, 4))
        self._instruction_entry = ctk.CTkEntry(
            outer,
            placeholder_text="Describe the correction rule in plain English…",
            height=34,
        )
        self._instruction_entry.pack(fill="x", pady=(0, 8))

        # ── STEP 3 — generate ────────────────────────────────────────────────
        make_section_header(outer, "STEP 3 — Generate").pack(
            anchor="w", pady=(0, 2)
        )

        action_row = ctk.CTkFrame(outer, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 8))
        self._generate_btn = ctk.CTkButton(
            action_row,
            text="⚙  Analyze & Generate Rules",
            fg_color=self._TEAL,
            hover_color=self._TEAL_HOVER,
            height=34,
            width=220,
            command=self._on_generate,
        )
        self._generate_btn.pack(side="left", padx=(0, 6))
        self._clear_btn = ctk.CTkButton(
            action_row,
            text="✕  Clear",
            fg_color="transparent",
            border_width=1,
            text_color="#CC4444",
            width=80,
            hover_color="#1A1A1A",
            command=self._on_clear,
        )
        self._clear_btn.pack(side="left")
        self._status_label = ctk.CTkLabel(
            action_row,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True, padx=(12, 0))

        # ── STEP 4 — review and approve ──────────────────────────────────────
        make_section_header(outer, "STEP 4 — Review and approve").pack(
            anchor="w", pady=(0, 2)
        )

        output_header = ctk.CTkFrame(outer, fg_color="transparent")
        output_header.pack(fill="x")
        ctk.CTkLabel(
            output_header,
            text="Generated Rules",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left")
        self._approve_btn = ctk.CTkButton(
            output_header,
            text="✓  Approve & Save",
            fg_color=self._GREEN,
            hover_color=self._GREEN_HOV,
            state="disabled",
            width=160,
            command=self._on_approve,
        )
        self._approve_btn.pack(side="right")

        self._output_box = ctk.CTkTextbox(
            outer,
            height=150,
            font=ctk.CTkFont(family="Courier New", size=10),
            state="disabled",
            fg_color="#0A1020",
        )
        self._output_box.pack(fill="x", pady=(4, 8))
        # Show a friendly empty-state until the user actually generates
        # rules. _set_output_placeholder also restores this whenever the
        # box is cleared (Clear button, no-rules result).
        self._set_output_placeholder()

        divider = ctk.CTkFrame(outer, height=1, fg_color="#252535")
        divider.pack(fill="x", pady=(0, 8))

        active_header = ctk.CTkFrame(outer, fg_color="transparent")
        active_header.pack(fill="x")
        self._rules_count_label = ctk.CTkLabel(
            active_header,
            text="Active Rules — loading…",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self._rules_count_label.pack(side="left")
        self._edit_rules_btn = ctk.CTkButton(
            active_header,
            text="Edit Rules File",
            fg_color="transparent",
            border_width=1,
            width=120,
            hover_color="#1A1A1A",
            command=self._on_edit_rules_file,
        )
        self._edit_rules_btn.pack(side="right")

        self._active_rules_box = ctk.CTkTextbox(
            outer,
            font=ctk.CTkFont(family="Courier New", size=10),
            state="disabled",
            fg_color="#080F1A",
        )
        self._active_rules_box.pack(fill="both", expand=True, pady=(4, 0))

    def _on_generate(self):
        if self._generating:
            return

        incorrect = self._incorrect_box.get("1.0", "end").strip()
        correct = self._correct_box.get("1.0", "end").strip()
        instruction = self._instruction_entry.get().strip()
        if not any((incorrect, correct, instruction)):
            self._set_status("Enter incorrect text, corrected text, or a rule instruction.")
            return

        self._generating = True
        self._generate_btn.configure(state="disabled", text="Analyzing…")
        self._approve_btn.configure(state="disabled")
        self._output_box.configure(state="normal")
        self._output_box.delete("1.0", "end")
        self._output_box.configure(state="disabled")
        self._set_status("Calling Claude API…")
        threading.Thread(
            target=self._run_generate,
            args=(incorrect, correct, instruction),
            daemon=True,
        ).start()

    def _run_generate(self, incorrect: str, correct: str, instruction: str):
        from spec_engine.training_engine import generate_rules

        result = generate_rules(
            incorrect,
            correct,
            instruction,
            progress_callback=lambda message: self.after(0, self._set_status, message),
        )
        self.after(0, self._on_generate_done, result)

    def _on_generate_done(self, result: dict):
        self._generating = False
        self._generate_btn.configure(state="normal", text="⚙  Analyze & Generate Rules")
        if result["error"]:
            self._set_status(f"Error: {result['error']}", "#FF4444")
            return

        self._proposed_rules = result["rules"]
        from spec_engine.training_engine import preview_rules_as_text

        display = preview_rules_as_text(result["rules"], result["flags"])
        self._output_box.configure(state="normal")
        self._output_box.delete("1.0", "end")
        self._output_box.insert("1.0", display)
        self._output_box.configure(state="disabled")

        if self._proposed_rules:
            self._approve_btn.configure(state="normal")
            count = len(self._proposed_rules)
            self._set_status(
                f"{count} rule{'s' if count != 1 else ''} proposed — review then click Approve & Save.",
                "#44CC88",
            )
        else:
            # No rules came back. Restore the placeholder so the box does
            # not leave a misleading "results pending" empty state.
            self._set_output_placeholder()
            self._set_status("No rules generated — try adding a Rule Instruction.", "gray")

    def _on_approve(self):
        if not self._proposed_rules:
            return

        from spec_engine.user_rule_store import add_rules

        try:
            count = add_rules(self._proposed_rules)
            self._set_status(f"✓ {count} rule{'s' if count != 1 else ''} saved.", "#44FF44")
            self._proposed_rules = []
            self._approve_btn.configure(state="disabled")
            self._refresh_active_rules()
        except ValueError as exc:
            self._set_status(f"Save failed: {exc}", "#FF4444")

    _OUTPUT_PLACEHOLDER = (
        'Click "⚙  Analyze & Generate Rules" to see proposed corrections here.\n'
        "You can review and approve them before they are added to the rule store."
    )

    def _set_output_placeholder(self) -> None:
        """Show the Generated Rules empty-state hint inside _output_box."""
        self._output_box.configure(state="normal")
        self._output_box.delete("1.0", "end")
        self._output_box.insert("1.0", self._OUTPUT_PLACEHOLDER)
        self._output_box.configure(state="disabled")

    def _on_clear(self):
        self._incorrect_box.delete("1.0", "end")
        self._correct_box.delete("1.0", "end")
        self._instruction_entry.delete(0, "end")
        self._set_output_placeholder()
        self._proposed_rules = []
        self._approve_btn.configure(state="disabled")
        self._set_status("")

    def _on_edit_rules_file(self):
        from spec_engine.user_rule_store import RULES_PATH

        if RULES_PATH.exists():
            subprocess.Popen(["notepad.exe", str(RULES_PATH)])
        else:
            self._set_status("No rules file yet — generate and approve rules first.")

    def _refresh_active_rules(self):
        from spec_engine.user_rule_store import get_rules_summary, load_all_rules

        rules = load_all_rules()
        self._rules_count_label.configure(text=f"Active Rules — {get_rules_summary()}")
        self._active_rules_box.configure(state="normal")
        self._active_rules_box.delete("1.0", "end")

        if not rules:
            self._active_rules_box.insert("1.0", "No rules saved yet.")
        else:
            lines: list[str] = []
            for rule in rules:
                status = "" if rule.get("enabled", True) else "  (disabled)"
                rule_id = rule.get("id", "?")
                if rule.get("type") == "exact_replace":
                    lines.append(
                        f'{rule_id}{status}  "{rule.get("incorrect", "")}"  →  "{rule.get("correct", "")}"'
                    )
                elif rule.get("type") == "regex_replace":
                    lines.append(
                        f'{rule_id}{status}  /{rule.get("pattern", "")}/  →  "{rule.get("replacement", "")}"'
                    )
                if rule.get("description"):
                    lines.append(f'       {rule["description"]}')
            self._active_rules_box.insert("1.0", "\n".join(lines))

        self._active_rules_box.configure(state="disabled")

    def on_tab_focus(self):
        self._refresh_active_rules()

    def _set_status(self, msg: str, color: str = "gray"):
        self._status_label.configure(text=msg, text_color=color)
