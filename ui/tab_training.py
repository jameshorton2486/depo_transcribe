"""
ui/tab_training.py

Training Engine tab — teaches the correction system new rules from examples.
"""

from __future__ import annotations

import os
import threading

import customtkinter as ctk

from ui._components import (
    BTN_AI_PURPLE,
    BTN_AI_PURPLE_HOVER,
    BTN_OUTLINE_BORDER,
    BTN_OUTLINE_TEXT,
    BTN_SAFE_GREEN,
    BTN_SAFE_GREEN_HOVER,
    PILL_EMERALD_TEXT,
    SECTION_HEADER_ACCENT,
    TEXT_DIM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    make_card_with_accent,
    make_numbered_chip,
    make_rule_card,
    make_status_pill,
)


class TrainingTab(ctk.CTkFrame):
    # 'Analyze & Generate Rules' is an AI action (calls Claude API) -
    # the spec assigns AI/optional actions to BTN_AI_PURPLE.
    # 'Approve & Save' is a safe-primary commit action -
    # the spec assigns those to BTN_SAFE_GREEN.
    # Local _TEAL/_AMBER/_GREEN_HOV constants kept for any non-button
    # uses that may exist elsewhere in this file.
    _TEAL = BTN_AI_PURPLE
    _TEAL_HOVER = BTN_AI_PURPLE_HOVER
    _AMBER = "#B8860B"
    _AMBER_HOVER = "#9A7209"
    _GREEN = BTN_SAFE_GREEN
    _GREEN_HOV = BTN_SAFE_GREEN_HOVER

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._proposed_rules: list[dict] = []
        self._generating: bool = False
        self._build_ui()

    def _build_ui(self):
        # Header sits above the columns, full width.
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkLabel(
            header,
            text="Training Engine",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Teach the system to recognize and correct transcript patterns automatically.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", pady=(0, 8))

        # Two-column grid: left scrolls vertically (steps), right is a
        # sticky scrollable panel (Active Library). 2:1 weight with a
        # 360-px minimum on the right so the library never collapses.
        # Responsive stacking under ~1100 px is deferred — the existing
        # window default is wide enough; revisit if it ships narrow.
        columns = ctk.CTkFrame(self, fg_color="transparent")
        columns.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        columns.grid_columnconfigure(0, weight=2)
        columns.grid_columnconfigure(1, weight=1, minsize=360)
        columns.grid_rowconfigure(0, weight=1)

        self._left_col = ctk.CTkScrollableFrame(columns, fg_color="transparent")
        self._left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self._right_col = ctk.CTkScrollableFrame(columns, fg_color="transparent")
        self._right_col.grid(row=0, column=1, sticky="nsew")

        outer = self._left_col

        # ── Step 01 — Pattern Examples ────────────────────────────────────────
        # Card with a top-edge blue accent strip; chip "01" + uppercase
        # title; two side-by-side textboxes for raw vs corrected examples.
        # Right textbox renders in emerald to mirror the "this is the
        # ground truth" semantic.
        step_01 = make_card_with_accent(outer, accent=SECTION_HEADER_ACCENT)
        step_01.pack(fill="x", pady=(0, 12))

        step_01_header = ctk.CTkFrame(step_01.content, fg_color="transparent")
        step_01_header.pack(fill="x", pady=(0, 10))
        make_numbered_chip(
            step_01_header, "01", accent=SECTION_HEADER_ACCENT
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            step_01_header,
            text="PATTERN EXAMPLES",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", anchor="w")

        input_row = ctk.CTkFrame(step_01.content, fg_color="transparent")
        input_row.pack(fill="x")
        input_row.grid_columnconfigure(0, weight=1)
        input_row.grid_columnconfigure(1, weight=1)

        left_panel = ctk.CTkFrame(input_row, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(
            left_panel,
            text="INCORRECT TEXT (DEEPGRAM OUTPUT)",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 4))
        self._incorrect_box = ctk.CTkTextbox(
            left_panel,
            height=160,
            font=ctk.CTkFont(family="Courier New", size=11),
        )
        self._incorrect_box.pack(fill="both", expand=True)

        right_panel = ctk.CTkFrame(input_row, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(
            right_panel,
            text="CORRECTED TEXT (EXPECTED)",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=PILL_EMERALD_TEXT,
        ).pack(anchor="w", pady=(0, 4))
        self._correct_box = ctk.CTkTextbox(
            right_panel,
            height=160,
            font=ctk.CTkFont(family="Courier New", size=11),
            text_color=PILL_EMERALD_TEXT,
        )
        self._correct_box.pack(fill="both", expand=True)

        # ── Step 02 — Contextual Instruction ──────────────────────────────────
        # Combines the prior STEP 2 (entry) and STEP 3 (Analyze + Clear +
        # status) into one card. Entry on top, status row below: status
        # label left, Clear + Analyze right.
        step_02 = make_card_with_accent(outer, accent=SECTION_HEADER_ACCENT)
        step_02.pack(fill="x", pady=(0, 12))

        step_02_header = ctk.CTkFrame(step_02.content, fg_color="transparent")
        step_02_header.pack(fill="x", pady=(0, 10))
        make_numbered_chip(
            step_02_header, "02", accent=SECTION_HEADER_ACCENT
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            step_02_header,
            text="CONTEXTUAL INSTRUCTION",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", anchor="w")

        self._instruction_entry = ctk.CTkEntry(
            step_02.content,
            placeholder_text='e.g. "Always correct subpoena duces tecum spelling"',
            height=40,
        )
        self._instruction_entry.pack(fill="x", pady=(0, 10))

        action_row = ctk.CTkFrame(step_02.content, fg_color="transparent")
        action_row.pack(fill="x")
        # Status label takes the leftmost slot so it reads naturally; the
        # Clear / Analyze buttons cluster on the right per the mockup.
        self._status_label = ctk.CTkLabel(
            action_row,
            text="Status: Ready",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True)
        self._generate_btn = ctk.CTkButton(
            action_row,
            text="⚙  Analyze & Generate Rules",
            fg_color=self._TEAL,
            hover_color=self._TEAL_HOVER,
            height=40,
            width=240,
            command=self._on_generate,
        )
        self._generate_btn.pack(side="right")
        self._clear_btn = ctk.CTkButton(
            action_row,
            text="✕  Clear",
            fg_color="transparent",
            border_width=1,
            text_color=TEXT_MUTED,
            width=90,
            height=40,
            hover_color="#1A1A1A",
            command=self._on_clear,
        )
        self._clear_btn.pack(side="right", padx=(0, 8))

        # ── Step 03 — Generated Rules (conditionally visible) ────────────────
        # Hidden until _on_generate_done returns at least one rule. Shown
        # via _show_step_03(); hidden + cleared via _hide_step_03().
        # The card holds a header (chip 03 + title + Approve & Save) and
        # a container for per-rule cards rendered by make_rule_card.
        self._step_03 = make_card_with_accent(outer, accent=PILL_EMERALD_TEXT)
        # Intentionally NOT packed at construction. _show_step_03 packs it.

        step_03_header = ctk.CTkFrame(self._step_03.content, fg_color="transparent")
        step_03_header.pack(fill="x", pady=(0, 10))
        make_numbered_chip(
            step_03_header, "03", accent=PILL_EMERALD_TEXT
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            step_03_header,
            text="GENERATED RULES",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", anchor="w")
        self._approve_btn = ctk.CTkButton(
            step_03_header,
            text="✓  Approve & Save",
            fg_color=self._GREEN,
            hover_color=self._GREEN_HOV,
            state="disabled",
            width=160,
            height=36,
            command=self._on_approve,
        )
        self._approve_btn.pack(side="right")

        self._proposed_rules_container = ctk.CTkFrame(
            self._step_03.content, fg_color="transparent"
        )
        self._proposed_rules_container.pack(fill="both", expand=True)

        # ── Active Library (right column) ────────────────────────────────────
        # Header row: title + count pill. Body: per-rule cards rendered
        # by make_rule_card(variant="active"). Footer: Open Rules File.
        # Toggle/delete handlers are not wired here; commit H lights them
        # up so commit G is purely a read-path change.
        library = self._right_col

        library_header = ctk.CTkFrame(library, fg_color="transparent")
        library_header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            library_header,
            text="ACTIVE LIBRARY",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._library_count_pill = make_status_pill(
            library_header, "0 rules", variant="blue"
        )
        self._library_count_pill.pack(side="right")

        self._active_rules_container = ctk.CTkFrame(library, fg_color="transparent")
        self._active_rules_container.pack(fill="both", expand=True, pady=(0, 10))

        self._open_rules_btn = ctk.CTkButton(
            library,
            text="Open Rules File",
            fg_color="transparent",
            border_width=1,
            border_color=BTN_OUTLINE_BORDER,
            text_color=BTN_OUTLINE_TEXT,
            height=36,
            hover_color="#1A1A1A",
            command=self._on_open_rules_file,
        )
        self._open_rules_btn.pack(fill="x")

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
        # Hide any prior Step 03 result so the user isn't looking at
        # last run's cards while the new run is in flight.
        self._hide_step_03()
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
        if self._proposed_rules:
            self._render_proposed_rules()
            self._show_step_03()
            self._approve_btn.configure(state="normal")
            count = len(self._proposed_rules)
            self._set_status(
                f"{count} rule{'s' if count != 1 else ''} proposed — review then click Approve & Save.",
                "#44CC88",
            )
        else:
            self._hide_step_03()
            self._set_status("No rules generated — try adding a Rule Instruction.", TEXT_MUTED)

    def _on_approve(self):
        if not self._proposed_rules:
            return

        from spec_engine.user_rule_store import add_rules

        try:
            count = add_rules(self._proposed_rules)
            self._set_status(f"✓ {count} rule{'s' if count != 1 else ''} saved.", "#44FF44")
            self._proposed_rules = []
            self._approve_btn.configure(state="disabled")
            self._hide_step_03()
            self._refresh_active_rules()
        except ValueError as exc:
            self._set_status(f"Save failed: {exc}", "#FF4444")

    @staticmethod
    def _rule_before_after(rule: dict) -> tuple[str, str]:
        # exact_replace shows raw before/after; regex_replace wraps the
        # pattern in slashes so the user can tell it's a regex at a glance.
        if rule.get("type") == "exact_replace":
            return str(rule.get("incorrect", "")), str(rule.get("correct", ""))
        if rule.get("type") == "regex_replace":
            return f"/{rule.get('pattern', '')}/", str(rule.get("replacement", ""))
        return "", ""

    def _render_proposed_rules(self) -> None:
        # Destroy last run's cards before rendering the new batch — the
        # container is reused across runs so widget references would
        # accumulate otherwise.
        for child in self._proposed_rules_container.winfo_children():
            child.destroy()
        for rule in self._proposed_rules:
            before, after = self._rule_before_after(rule)
            card = make_rule_card(
                self._proposed_rules_container,
                rule_id=rule.get("id", "?"),
                before=before,
                after=after,
                match_type=rule.get("type", "exact_replace"),
                variant="proposed",
            )
            card.pack(fill="x", pady=(0, 8))

    def _show_step_03(self) -> None:
        # Step 03 packs after Step 02 in left_col; pack with the same
        # vertical rhythm the other step cards use.
        self._step_03.pack(fill="x", pady=(0, 12))

    def _hide_step_03(self) -> None:
        self._step_03.pack_forget()
        for child in self._proposed_rules_container.winfo_children():
            child.destroy()

    def _on_clear(self):
        self._incorrect_box.delete("1.0", "end")
        self._correct_box.delete("1.0", "end")
        self._instruction_entry.delete(0, "end")
        self._proposed_rules = []
        self._approve_btn.configure(state="disabled")
        self._hide_step_03()
        self._set_status("")

    def _on_open_rules_file(self):
        # os.startfile uses the OS-registered handler (notepad / VS Code /
        # whatever the user has set), which is friendlier than hard-coding
        # notepad.exe. Windows-only — that's fine; the app is Windows-only
        # per CLAUDE.md §2.
        from spec_engine.user_rule_store import RULES_PATH

        if RULES_PATH.exists():
            os.startfile(str(RULES_PATH))
        else:
            self._set_status("No rules file yet — generate and approve rules first.")

    def _refresh_active_rules(self):
        from spec_engine.user_rule_store import load_all_rules

        rules = load_all_rules()

        # Count pill: "0 rules" / "1 rule" / "N rules" reads naturally
        # at any count.
        count = len(rules)
        self._library_count_pill.text_label.configure(
            text=f"{count} rule{'s' if count != 1 else ''}"
        )

        # Destroy previous batch before rendering — same pattern as
        # _render_proposed_rules; per-row widgets must not accumulate.
        for child in self._active_rules_container.winfo_children():
            child.destroy()

        if not rules:
            ctk.CTkLabel(
                self._active_rules_container,
                text="No rules saved yet.",
                text_color=TEXT_DIM,
                font=ctk.CTkFont(size=11),
            ).pack(pady=20)
            return

        for rule in rules:
            before, after = self._rule_before_after(rule)
            card = make_rule_card(
                self._active_rules_container,
                rule_id=rule.get("id", "?"),
                before=before,
                after=after,
                match_type=rule.get("type", "exact_replace"),
                description=rule.get("description", ""),
                variant="active",
                enabled=rule.get("enabled", True),
                # on_toggle / on_delete deliberately not wired in commit G —
                # commit H lights up the API surface from commit A. Until
                # then the dot is decorative and there's no delete button.
            )
            card.pack(fill="x", pady=(0, 6))

    def on_tab_focus(self):
        self._refresh_active_rules()

    def _set_status(self, msg: str, color: str = "gray"):
        # Standardized framing matching the Transcript tab's set_status.
        # Empty input resets to the idle 'Status: Ready' state. Messages
        # already prefixed with a status-like word pass through verbatim.
        text = (msg or "").strip() or "Ready"
        if not text.startswith(("Status:", "Error:", "ERROR:", "Done", "✓", "⚠", "Failed")):
            text = f"Status: {text}"
        self._status_label.configure(text=text, text_color=color)
