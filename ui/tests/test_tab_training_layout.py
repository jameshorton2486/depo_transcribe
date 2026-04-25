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


# ── Active Library — read path (commit G) ────────────────────────────────────

from ui._components import DOT_DISABLED, DOT_ENABLED


def _exact_with_state(rule_id, before, after, *, enabled=True, description=""):
    rule = {
        "id": rule_id,
        "type": "exact_replace",
        "incorrect": before,
        "correct": after,
        "enabled": enabled,
    }
    if description:
        rule["description"] = description
    return rule


def test_library_count_pill_exists(tab):
    assert hasattr(tab, "_library_count_pill")


def test_active_rules_container_is_a_frame(tab):
    assert isinstance(tab._active_rules_container, ctk.CTkFrame)


def test_open_rules_button_exists(tab):
    assert isinstance(tab._open_rules_btn, ctk.CTkButton)


def test_refresh_active_rules_no_rules_shows_empty_state(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    tab._refresh_active_rules()
    children = tab._active_rules_container.winfo_children()
    # One placeholder label, no cards.
    assert len(children) == 1
    assert isinstance(children[0], ctk.CTkLabel)
    assert "No rules saved yet" in children[0].cget("text")


def test_refresh_active_rules_renders_one_card_per_rule(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [
            _exact_with_state("usr_001", "Coger", "Koger"),
            _exact_with_state("usr_002", "depo", "deposition"),
            _exact_with_state("usr_003", "wittness", "witness"),
        ],
    )
    tab._refresh_active_rules()
    cards = tab._active_rules_container.winfo_children()
    assert len(cards) == 3


def test_refresh_active_rules_count_pill_pluralizes(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state("usr_001", "a", "b")],
    )
    tab._refresh_active_rules()
    assert tab._library_count_pill.text_label.cget("text") == "1 rule"

    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [
            _exact_with_state("usr_001", "a", "b"),
            _exact_with_state("usr_002", "c", "d"),
        ],
    )
    tab._refresh_active_rules()
    assert tab._library_count_pill.text_label.cget("text") == "2 rules"


def test_refresh_active_rules_count_pill_zero(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    tab._refresh_active_rules()
    assert tab._library_count_pill.text_label.cget("text") == "0 rules"


def test_refresh_active_rules_enabled_rule_shows_emerald_dot(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state("usr_001", "a", "b", enabled=True)],
    )
    tab._refresh_active_rules()
    card = tab._active_rules_container.winfo_children()[0]
    assert card.dot.cget("fg_color") == DOT_ENABLED


def test_refresh_active_rules_disabled_rule_shows_slate_dot(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state("usr_001", "a", "b", enabled=False)],
    )
    tab._refresh_active_rules()
    card = tab._active_rules_container.winfo_children()[0]
    assert card.dot.cget("fg_color") == DOT_DISABLED


def test_refresh_active_rules_surfaces_description(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state(
            "usr_001", "a", "b",
            description="Fixes a stenographic homophone",
        )],
    )
    tab._refresh_active_rules()
    card = tab._active_rules_container.winfo_children()[0]
    assert hasattr(card, "description_label")


def test_refresh_active_rules_replaces_previous_batch(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state("usr_001", "a", "b")],
    )
    tab._refresh_active_rules()
    assert len(tab._active_rules_container.winfo_children()) == 1

    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [
            _exact_with_state("usr_002", "c", "d"),
            _exact_with_state("usr_003", "e", "f"),
        ],
    )
    tab._refresh_active_rules()
    # 2 cards, not 1 + 2.
    assert len(tab._active_rules_container.winfo_children()) == 2


# Locks in the external API surface — app_window.py:85 calls
# on_tab_focus(), and on_tab_focus() must continue to refresh the
# library after the textbox-to-cards swap.
def test_on_tab_focus_refreshes_library(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state("usr_007", "x", "y")],
    )
    tab.on_tab_focus()
    assert len(tab._active_rules_container.winfo_children()) == 1
    assert tab._library_count_pill.text_label.cget("text") == "1 rule"


# ── Active Library — toggle + delete (commit H) ──────────────────────────────


def test_active_card_renders_with_delete_button_in_h(tab, monkeypatch):
    # After H, on_delete is passed → make_rule_card renders the X button.
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state("usr_001", "a", "b")],
    )
    tab._refresh_active_rules()
    card = tab._active_rules_container.winfo_children()[0]
    assert hasattr(card, "delete_btn")


def test_active_card_dot_is_clickable_in_h(tab, monkeypatch):
    # After H, on_toggle is passed → the dot has a Button-1 binding.
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: [_exact_with_state("usr_001", "a", "b")],
    )
    tab._refresh_active_rules()
    card = tab._active_rules_container.winfo_children()[0]
    bindings = card.dot._canvas.bind()
    assert "<Button-1>" in bindings


def test_on_toggle_rule_calls_set_rule_enabled_with_inverted_state(tab, monkeypatch):
    received = []
    monkeypatch.setattr(
        "spec_engine.user_rule_store.set_rule_enabled",
        lambda rid, enabled: received.append((rid, enabled)) or True,
    )
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    tab._on_toggle_rule("usr_042", False)
    assert received == [("usr_042", False)]


def test_on_toggle_rule_refreshes_library_on_success(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.set_rule_enabled",
        lambda _id, _enabled: True,
    )
    refreshed = []
    monkeypatch.setattr(
        tab, "_refresh_active_rules",
        lambda: refreshed.append(True),
    )
    tab._on_toggle_rule("usr_001", False)
    assert refreshed == [True]


def test_on_toggle_rule_shows_error_status_on_not_found(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.set_rule_enabled",
        lambda _id, _enabled: False,
    )
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    tab._on_toggle_rule("usr_999", True)
    assert "not found" in tab._status_label.cget("text").lower()


def test_on_delete_rule_confirms_before_calling_delete(tab, monkeypatch):
    delete_calls = []
    monkeypatch.setattr(
        "spec_engine.user_rule_store.delete_rule",
        lambda rid: delete_calls.append(rid) or True,
    )
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *_a, **_k: False
    )
    tab._on_delete_rule("usr_001")
    assert delete_calls == []


def test_on_delete_rule_calls_delete_when_confirmed(tab, monkeypatch):
    delete_calls = []
    monkeypatch.setattr(
        "spec_engine.user_rule_store.delete_rule",
        lambda rid: delete_calls.append(rid) or True,
    )
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *_a, **_k: True
    )
    tab._on_delete_rule("usr_001")
    assert delete_calls == ["usr_001"]


def test_on_delete_rule_refreshes_library_after_success(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.delete_rule", lambda _id: True
    )
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *_a, **_k: True
    )
    refreshed = []
    monkeypatch.setattr(
        tab, "_refresh_active_rules",
        lambda: refreshed.append(True),
    )
    tab._on_delete_rule("usr_001")
    assert refreshed == [True]


def test_on_delete_rule_shows_success_status(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.delete_rule", lambda _id: True
    )
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *_a, **_k: True
    )
    tab._on_delete_rule("usr_042")
    assert "deleted" in tab._status_label.cget("text").lower()
    assert "usr_042" in tab._status_label.cget("text")


def test_on_delete_rule_shows_error_status_when_not_found(tab, monkeypatch):
    monkeypatch.setattr(
        "spec_engine.user_rule_store.delete_rule", lambda _id: False
    )
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules", lambda: []
    )
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *_a, **_k: True
    )
    tab._on_delete_rule("usr_999")
    assert "not found" in tab._status_label.cget("text").lower()
