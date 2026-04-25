"""
Tests for the Training-tab redesign helpers in ui._components:
make_numbered_chip, make_card_with_accent, make_rule_card.

Each helper is exercised against a real (hidden) CTk root, then
introspected for the attributes the helper exposes. The fixture is
module-scoped because creating and destroying multiple CTk roots in
the same pytest session intermittently fails to find tk.tcl on Windows.
"""

import customtkinter as ctk
import pytest

from ui._components import (
    BG_CARD,
    CARD_BORDER_COLOR,
    CHIP_BG,
    CHIP_BORDER,
    DOT_DISABLED,
    DOT_ENABLED,
    PILL_AMBER_BG,
    PILL_BLUE_BG,
    PILL_EMERALD_TEXT,
    TEXT_DIM,
    TEXT_SECONDARY,
    make_card_with_accent,
    make_numbered_chip,
    make_rule_card,
)


# `root` fixture is supplied by ui/tests/conftest.py at session scope.


# ── make_numbered_chip ───────────────────────────────────────────────────────

def test_chip_label_text_matches_input(root):
    chip = make_numbered_chip(root, "01", accent="#3b82f6")
    assert chip.text_label.cget("text") == "01"


def test_chip_label_text_color_matches_accent(root):
    chip = make_numbered_chip(root, "02", accent="#3b82f6")
    assert chip.text_label.cget("text_color") == "#3b82f6"


def test_chip_uses_chip_bg_token(root):
    chip = make_numbered_chip(root, "01", accent="#3b82f6")
    assert chip.cget("fg_color") == CHIP_BG


def test_chip_uses_chip_border_token(root):
    chip = make_numbered_chip(root, "01", accent="#3b82f6")
    assert chip.cget("border_color") == CHIP_BORDER


def test_chip_emerald_accent_for_step_03(root):
    chip = make_numbered_chip(root, "03", accent=PILL_EMERALD_TEXT)
    assert chip.text_label.cget("text_color") == PILL_EMERALD_TEXT


# ── make_card_with_accent ────────────────────────────────────────────────────

def test_card_uses_card_bg(root):
    card = make_card_with_accent(root, accent="#3b82f6")
    assert card.cget("fg_color") == BG_CARD


def test_card_uses_card_border_color(root):
    card = make_card_with_accent(root, accent="#3b82f6")
    assert card.cget("border_color") == CARD_BORDER_COLOR


def test_card_exposes_content_subframe(root):
    card = make_card_with_accent(root, accent="#3b82f6")
    assert isinstance(card.content, ctk.CTkFrame)


def test_card_content_is_transparent(root):
    card = make_card_with_accent(root, accent="#3b82f6")
    assert card.content.cget("fg_color") == "transparent"


def test_card_accent_strip_color_matches_param(root):
    card = make_card_with_accent(root, accent="#10b981")
    # Accent strip is the first packed child; content frame is second.
    accent_strip = card.winfo_children()[0]
    assert accent_strip.cget("fg_color") == "#10b981"


# ── make_rule_card — proposed variant ────────────────────────────────────────

def test_proposed_card_no_dot(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="Coger",
        after="Koger",
        match_type="exact_replace",
        variant="proposed",
    )
    assert not hasattr(card, "dot")


def test_proposed_card_no_delete_button(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="Coger",
        after="Koger",
        match_type="exact_replace",
        variant="proposed",
    )
    assert not hasattr(card, "delete_btn")


def test_proposed_card_id_label_text_matches(root):
    card = make_rule_card(
        root,
        rule_id="usr_042",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="proposed",
    )
    assert card.id_label.cget("text") == "usr_042"


def test_proposed_card_before_label_uses_secondary_text(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="Coger",
        after="Koger",
        match_type="exact_replace",
        variant="proposed",
    )
    assert card.before_label.cget("text") == "Coger"
    assert card.before_label.cget("text_color") == TEXT_SECONDARY


def test_proposed_card_after_label_uses_emerald(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="Coger",
        after="Koger",
        match_type="exact_replace",
        variant="proposed",
    )
    assert card.after_label.cget("text") == "Koger"
    assert card.after_label.cget("text_color") == PILL_EMERALD_TEXT


def test_proposed_card_id_label_uses_dim_text(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="proposed",
    )
    assert card.id_label.cget("text_color") == TEXT_DIM


# ── make_rule_card — match-type badges ───────────────────────────────────────

def test_exact_replace_renders_blue_badge(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="Coger",
        after="Koger",
        match_type="exact_replace",
        variant="proposed",
    )
    assert card.badge.text_label.cget("text") == "EXACT MATCH"
    assert card.badge.cget("fg_color") == PILL_BLUE_BG


def test_regex_replace_renders_amber_badge(root):
    card = make_rule_card(
        root,
        rule_id="usr_002",
        before=r"\bCog(?:er|ar)\b",
        after="Koger",
        match_type="regex_replace",
        variant="proposed",
    )
    assert card.badge.text_label.cget("text") == "REGEX"
    assert card.badge.cget("fg_color") == PILL_AMBER_BG


def test_unknown_match_type_raises_keyerror(root):
    with pytest.raises(KeyError):
        make_rule_card(
            root,
            rule_id="usr_001",
            before="x",
            after="y",
            match_type="fuzzy_replace",  # not implemented in the rule store
            variant="proposed",
        )


# ── make_rule_card — active variant ──────────────────────────────────────────

def test_active_card_enabled_dot_is_emerald(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="active",
        enabled=True,
    )
    assert card.dot.cget("fg_color") == DOT_ENABLED


def test_active_card_disabled_dot_is_slate(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="active",
        enabled=False,
    )
    assert card.dot.cget("fg_color") == DOT_DISABLED


def test_active_card_with_on_delete_shows_delete_button(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="active",
        enabled=True,
        on_delete=lambda _id: None,
    )
    assert hasattr(card, "delete_btn")
    assert card.delete_btn.cget("text") == "✗"  # the ✗ glyph


def test_active_card_without_on_delete_omits_delete_button(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="active",
        enabled=True,
    )
    assert not hasattr(card, "delete_btn")


def test_active_card_delete_button_invokes_callback_with_rule_id(root):
    received = []
    card = make_rule_card(
        root,
        rule_id="usr_042",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="active",
        enabled=True,
        on_delete=lambda rid: received.append(rid),
    )
    card.delete_btn.invoke()
    assert received == ["usr_042"]


def test_active_card_dot_with_on_toggle_binds_button1_on_inner_canvas(root):
    # CTkFrame.bind delegates to its inner _canvas widget. We can't reliably
    # event_generate against a withdrawn root, but we can verify the binding
    # is registered — that's a stable contract.
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="active",
        enabled=True,
        on_toggle=lambda *_a: None,
    )
    bindings = card.dot._canvas.bind()
    assert "<Button-1>" in bindings


def test_active_card_dot_without_on_toggle_does_not_bind_button1(root):
    card = make_rule_card(
        root,
        rule_id="usr_001",
        before="x",
        after="y",
        match_type="exact_replace",
        variant="active",
        enabled=True,
    )
    bindings = card.dot._canvas.bind()
    assert "<Button-1>" not in bindings
