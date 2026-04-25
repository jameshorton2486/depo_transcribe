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
