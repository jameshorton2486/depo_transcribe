"""
Layout-invariant tests for the Training tab.

Constructs the full TrainingTab against a withdrawn CTk root and
asserts the externally-visible widget references the callbacks rely on
still exist. Per-panel visual tests live alongside their commits;
broader layout coverage lands with the dedicated layout/state-machine
tests in the final Training-redesign commit.
"""

import customtkinter as ctk
import pytest

from ui._components import PILL_EMERALD_TEXT
from ui.tab_training import TrainingTab


# `root` fixture is supplied by ui/tests/conftest.py at session scope.


@pytest.fixture
def tab(root):
    t = TrainingTab(root)
    yield t
    t.destroy()


# ── Layout scaffolding (commit C) ────────────────────────────────────────────

def test_left_column_is_a_scrollable_frame(tab):
    assert isinstance(tab._left_col, ctk.CTkScrollableFrame)


def test_right_column_is_a_scrollable_frame(tab):
    assert isinstance(tab._right_col, ctk.CTkScrollableFrame)


# ── Step 01 — Pattern Examples (commit D) ────────────────────────────────────

def test_incorrect_box_is_still_a_textbox(tab):
    assert isinstance(tab._incorrect_box, ctk.CTkTextbox)


def test_correct_box_is_still_a_textbox(tab):
    assert isinstance(tab._correct_box, ctk.CTkTextbox)


def test_correct_box_renders_in_emerald(tab):
    # Reinforces the "this is the ground truth" semantic: the corrected
    # textbox's text color must match the emerald accent the right
    # column header also uses.
    assert tab._correct_box.cget("text_color") == PILL_EMERALD_TEXT


def test_clear_callback_empties_both_boxes(tab):
    tab._incorrect_box.insert("1.0", "Coger said hello.")
    tab._correct_box.insert("1.0", "Koger said hello.")
    tab._instruction_entry.insert(0, "name fix")
    tab._on_clear()
    assert tab._incorrect_box.get("1.0", "end").strip() == ""
    assert tab._correct_box.get("1.0", "end").strip() == ""
    assert tab._instruction_entry.get() == ""


# ── Step 02 — Contextual Instruction (commit E) ──────────────────────────────

def test_instruction_entry_is_a_ctk_entry(tab):
    assert isinstance(tab._instruction_entry, ctk.CTkEntry)


def test_generate_button_is_a_ctk_button(tab):
    assert isinstance(tab._generate_btn, ctk.CTkButton)


def test_clear_button_is_a_ctk_button(tab):
    assert isinstance(tab._clear_btn, ctk.CTkButton)


def test_status_label_idle_text_is_ready(tab):
    assert tab._status_label.cget("text") == "Status: Ready"


def test_set_status_idle_resets_to_ready_label(tab):
    tab._set_status("Calling Claude API…")
    assert tab._status_label.cget("text") != "Status: Ready"
    tab._set_status("")
    assert tab._status_label.cget("text") == "Status: Ready"


# ── Step 03 — Generated Rules (commit F) ─────────────────────────────────────

def _exact(rule_id, before, after):
    return {"id": rule_id, "type": "exact_replace", "incorrect": before, "correct": after}


def test_step_03_starts_unpacked(tab):
    # _step_03 is constructed but never pack'd at startup so the
    # tab is empty until the user actually generates rules.
    assert tab._step_03.winfo_manager() == ""


def test_show_step_03_packs_the_card(tab):
    tab._show_step_03()
    assert tab._step_03.winfo_manager() == "pack"
    tab._hide_step_03()  # cleanup for shared tab


def test_hide_step_03_unpacks_and_clears_cards(tab):
    tab._proposed_rules = [_exact("u1", "a", "b")]
    tab._render_proposed_rules()
    tab._show_step_03()
    assert len(tab._proposed_rules_container.winfo_children()) == 1
    tab._hide_step_03()
    assert tab._step_03.winfo_manager() == ""
    assert len(tab._proposed_rules_container.winfo_children()) == 0


def test_render_proposed_rules_creates_one_card_per_rule(tab):
    tab._proposed_rules = [_exact("u1", "a", "b"), _exact("u2", "c", "d")]
    tab._render_proposed_rules()
    assert len(tab._proposed_rules_container.winfo_children()) == 2
    tab._hide_step_03()


def test_render_proposed_rules_replaces_previous_batch(tab):
    tab._proposed_rules = [_exact("u1", "a", "b")]
    tab._render_proposed_rules()
    tab._proposed_rules = [_exact("u2", "c", "d"), _exact("u3", "e", "f")]
    tab._render_proposed_rules()
    # New batch replaces, doesn't accumulate.
    assert len(tab._proposed_rules_container.winfo_children()) == 2
    tab._hide_step_03()


# Pure logic — no UI fixture needed.

def test_rule_before_after_exact_replace_returns_raw_strings():
    assert TrainingTab._rule_before_after(
        {"type": "exact_replace", "incorrect": "Coger", "correct": "Koger"}
    ) == ("Coger", "Koger")


def test_rule_before_after_regex_replace_wraps_pattern_in_slashes():
    assert TrainingTab._rule_before_after(
        {"type": "regex_replace", "pattern": r"\bCog\w+\b", "replacement": "Koger"}
    ) == (r"/\bCog\w+\b/", "Koger")


def test_rule_before_after_unknown_type_returns_empty_strings():
    assert TrainingTab._rule_before_after({"type": "future_kind"}) == ("", "")


# _on_generate_done routes through _show / _hide step 03 based on rule
# count. Both branches must leave the UI in the right shape.

def test_on_generate_done_with_rules_shows_step_03(tab):
    tab._on_generate_done({
        "error": None,
        "rules": [_exact("u1", "a", "b")],
        "flags": [],
    })
    assert tab._step_03.winfo_manager() == "pack"
    tab._hide_step_03()


def test_on_generate_done_with_no_rules_keeps_step_03_hidden(tab):
    tab._on_generate_done({"error": None, "rules": [], "flags": []})
    assert tab._step_03.winfo_manager() == ""


def test_on_generate_done_with_error_keeps_step_03_hidden(tab):
    tab._on_generate_done({"error": "API failed", "rules": [], "flags": []})
    assert tab._step_03.winfo_manager() == ""


def test_on_clear_hides_step_03(tab):
    tab._proposed_rules = [_exact("u1", "a", "b")]
    tab._render_proposed_rules()
    tab._show_step_03()
    tab._on_clear()
    assert tab._step_03.winfo_manager() == ""
