"""
Headless tests for ui._components.make_status_pill.

Status pills are colored badges used for counts like "Flagged: 5". Each
test instantiates a hidden CTk root, builds a pill, and inspects the
returned frame's color attributes against the palette tokens defined in
ui._components.
"""

import customtkinter as ctk
import pytest

from ui._components import (
    PILL_AMBER_BG,
    PILL_AMBER_BORDER,
    PILL_AMBER_TEXT,
    PILL_BLUE_BG,
    PILL_BLUE_BORDER,
    PILL_BLUE_TEXT,
    make_status_pill,
)


@pytest.fixture(scope="module")
def root():
    # Module-scoped: creating/destroying a CTk root per-test in the same
    # pytest session can intermittently fail to locate tk.tcl on Windows.
    # One root for all tests in this module sidesteps that.
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


def test_amber_variant_uses_amber_palette(root):
    pill = make_status_pill(root, "Flagged: 5", variant="amber")
    assert pill.cget("fg_color") == PILL_AMBER_BG


def test_amber_variant_border_matches_palette(root):
    pill = make_status_pill(root, "Flagged: 5", variant="amber")
    assert pill.cget("border_color") == PILL_AMBER_BORDER


def test_blue_variant_uses_blue_palette(root):
    pill = make_status_pill(root, "Reviewed: 120", variant="blue")
    assert pill.cget("fg_color") == PILL_BLUE_BG


def test_blue_variant_border_matches_palette(root):
    pill = make_status_pill(root, "Reviewed: 120", variant="blue")
    assert pill.cget("border_color") == PILL_BLUE_BORDER


def test_label_text_matches_caller_input(root):
    pill = make_status_pill(root, "Flagged: 5", variant="amber")
    label = pill.winfo_children()[0]
    assert label.cget("text") == "Flagged: 5"


def test_amber_label_text_color_is_amber(root):
    pill = make_status_pill(root, "Flagged: 5", variant="amber")
    label = pill.winfo_children()[0]
    assert label.cget("text_color") == PILL_AMBER_TEXT


def test_blue_label_text_color_is_blue(root):
    pill = make_status_pill(root, "Reviewed: 120", variant="blue")
    label = pill.winfo_children()[0]
    assert label.cget("text_color") == PILL_BLUE_TEXT


def test_unknown_variant_raises_keyerror(root):
    with pytest.raises(KeyError):
        make_status_pill(root, "X", variant="emerald")
