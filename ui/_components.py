"""
Shared UI components for the Depo-Pro Transcribe tabs.

Single source of truth for visual primitives (section headers, etc.) so
the three tabs stay consistent without each one redefining the style.

USAGE:
    from ui._components import make_section_header

    header = make_section_header(parent, "Existing Transcript")
    header.pack(side="left")           # or fill="x", anchor="w", etc.
"""

from __future__ import annotations

import customtkinter as ctk

# Accent color for the section-header bar. Subtle blue that reads on the
# dark theme without competing with primary buttons (amber, green, purple).
SECTION_HEADER_ACCENT = "#3A7FBF"


# ── Button color semantics (Phase 2 - Commit 7) ──────────────────────────────
# Single source of truth for category buttons across all tabs. Only the
# primary "category" buttons (CREATE TRANSCRIPT, Run Corrections, AI Correct,
# Approve & Save, Browse, etc.) use these constants. Transient state
# indicators (e.g. a "PDF Auto-Detected" success badge) are a different
# semantic and intentionally use their own colors.
#
#   PRIMARY  (amber)   - the most expensive / most dominant action on a tab
#                        Examples: CREATE TRANSCRIPT
#   SAFE     (green)   - approve / commit / mark-reviewed actions
#                        Examples: Run Corrections, Mark Reviewed, Approve & Save
#   AI       (purple)  - AI-driven optional actions (Claude API calls)
#                        Examples: AI Correct, Analyze & Generate Rules
#   UTILITY  (blue)    - file / data intake actions
#                        Examples: Browse, Upload
#   OUTLINE  (gray)    - secondary actions; transparent fill + thin border
#                        Examples: Clear, Re-Scan

BTN_PRIMARY_AMBER = "#B8860B"
BTN_PRIMARY_AMBER_HOVER = "#9A7209"

BTN_SAFE_GREEN = "#1A6B3A"
BTN_SAFE_GREEN_HOVER = "#145230"

BTN_AI_PURPLE = "#6B2A8C"
BTN_AI_PURPLE_HOVER = "#4E1E66"


# ── Shared file-picker filetypes ──────────────────────────────────────────────
# Used by the Transcribe tab's Browse button and any dialog that needs the
# same audio/video selection scope (e.g. multi-file combine dialog). Single
# source of truth so the dialog and the main button can never drift apart.
AUDIO_VIDEO_EXTENSIONS = (
    ("Audio / Video files", "*.mp3 *.mp4 *.wav *.m4a *.mov *.avi *.mkv *.flac"),
    ("All files", "*.*"),
)

BTN_UTILITY_BLUE = "#1558C0"
BTN_UTILITY_BLUE_HOVER = "#0F3E8A"

BTN_OUTLINE_BORDER = "#334455"
BTN_OUTLINE_TEXT = "#8AB"


# ── Card spacing + border (Phase 2 - Commit 8) ───────────────────────────────
# Single source of truth for the "card" surface used on each tab so spacing
# and borders stay consistent. CARD_GAP_PY is the vertical breathing room
# between two stacked cards (= 2/8" at 96 DPI). CARD_INNER_PADX/PADY are the
# padding from the card border to its inner content frame.

CARD_BORDER_COLOR = "#2A3A4A"
CARD_BORDER_WIDTH = 1
CARD_GAP_PY = 24
CARD_INNER_PADX = 12
CARD_INNER_PADY = 10

# Uniform width/height for toolbar action buttons across tabs. Keeps the
# control strip reading as a single row rather than a mix of widths.
TOOLBAR_BTN_W = 160
TOOLBAR_BTN_H = 32


# ── Surface tokens ───────────────────────────────────────────────────────────
# Names for the three dark surface levels used by tabs. Existing widgets
# inherit CTk's default theme background; these tokens are for new widgets
# that need to opt into a specific level (e.g. a card-on-card composition or
# the transcript editor area).

BG_BASE = "#0a0c10"  # outermost app background
BG_CARD = "#0f1218"  # card surface (one level above base)
BG_TRANSCRIPT = "#07080c"  # transcript editor (one level below base)


# ── Status pill (badge) tokens ───────────────────────────────────────────────
# Colors for small rounded badges used for counts ("Flagged: 5", "Reviewed:
# 120"). Background and border are precomputed blends of the brand hex over
# BG_BASE — the mockup specifies 10% fill / 20% border; CTk has no alpha so
# we bake the result. Text color reuses the brand hex unchanged so badges
# read as the same family as section headers / speaker labels.

# Amber family (BTN_PRIMARY_AMBER #B8860B blended over BG_BASE)
PILL_AMBER_BG = "#1B180F"  # 10% B8860B
PILL_AMBER_BORDER = "#2D240F"  # 20% B8860B
PILL_AMBER_TEXT = BTN_PRIMARY_AMBER

# Blue family (SECTION_HEADER_ACCENT #3A7FBF blended over BG_BASE)
PILL_BLUE_BG = "#0F1822"  # 10% 3A7FBF
PILL_BLUE_BORDER = "#142333"  # 20% 3A7FBF
PILL_BLUE_TEXT = SECTION_HEADER_ACCENT

# Emerald family (#10B981 blended over BG_BASE) — for the "Done" pill
# that replaces Remaining when the reviewer has confirmed every flag.
# BTN_SAFE_GREEN (#1A6B3A) is too muted for badge text on the dark surface,
# and the prior single-label scheme used #44AA44 inline only; the emerald
# family is genuinely missing from the palette.
PILL_EMERALD_BG = "#0B1D1B"  # 10% 10B981
PILL_EMERALD_BORDER = "#0B2F27"  # 20% 10B981
PILL_EMERALD_TEXT = "#10B981"


_PILL_VARIANTS = {
    "amber": (PILL_AMBER_BG, PILL_AMBER_BORDER, PILL_AMBER_TEXT),
    "blue": (PILL_BLUE_BG, PILL_BLUE_BORDER, PILL_BLUE_TEXT),
    "emerald": (PILL_EMERALD_BG, PILL_EMERALD_BORDER, PILL_EMERALD_TEXT),
}


# ── Text color hierarchy ─────────────────────────────────────────────────────
# Slate scale used by the Training tab redesign and any new layouts that
# need a four-level text hierarchy. Existing widgets stick with their
# inline hex strings — these tokens are not retroactively applied.

TEXT_PRIMARY = "#E2E8F0"  # slate-200, body text on dark surface
TEXT_SECONDARY = "#94A3B8"  # slate-400, secondary content
TEXT_MUTED = "#64748B"  # slate-500, label text
TEXT_DIM = "#475569"  # slate-600, ID labels, separators


# ── Numbered chip + card-with-accent + rule card tokens ──────────────────────
# Used by the Training tab's step headers and the Active Library / Step 03
# rule rows. CHIP_* describes the small numbered disc; DOT_DISABLED is the
# muted state-dot color that contrasts CARD_BORDER_COLOR (#2A3A4A) so a
# scanner can tell at a glance which library rows are dormant.

CHIP_BG = "#1E293B"  # slate-800 disc fill
CHIP_BORDER = "#334155"  # slate-700 disc border
DOT_DISABLED = "#475569"  # slate-600 — distinct from CARD_BORDER_COLOR
DOT_ENABLED = PILL_EMERALD_TEXT  # alias for the active-rule emerald

# Hover color for the delete button on active library rows. A muted dark
# red — visible enough to read as "destructive" without being shouty.
DELETE_HOVER_BG = "#3D1A1A"


def make_status_pill(
    parent,
    text: str,
    *,
    variant: str = "amber",
) -> ctk.CTkFrame:
    """
    Build a small rounded badge: colored fill + matching 1-px border + bold
    label. Used for counts like "Flagged: 5", "Reviewed: 120". Caller packs
    or grids the returned frame however they need.

    `variant` selects from _PILL_VARIANTS — KeyError if the name is unknown,
    which is intentional so a typo fails loudly rather than silently picking
    a default color.
    """
    bg, border, text_color = _PILL_VARIANTS[variant]
    pill = ctk.CTkFrame(
        parent,
        fg_color=bg,
        border_color=border,
        border_width=1,
        corner_radius=8,
    )
    label = ctk.CTkLabel(
        pill,
        text=text,
        text_color=text_color,
        font=ctk.CTkFont(size=10, weight="bold"),
    )
    label.pack(padx=8, pady=2)
    # Expose so callers can update the text without reaching into
    # winfo_children() — that would break if the helper ever adds
    # secondary children (e.g. an icon).
    pill.text_label = label
    return pill


def make_section_header(
    parent,
    text: str,
    *,
    accent: str = SECTION_HEADER_ACCENT,
    font_size: int = 12,
) -> ctk.CTkFrame:
    """
    Build a uniform section header: a 3px colored left accent bar followed
    by bold text. Caller packs the returned frame however they need
    (fill='x', anchor='w', side='left', etc.) so this helper does not
    impose layout decisions on its parent.

    Returns the outer frame so the caller can position it.
    """
    # Fix the row's height to the label's natural line so the bar (a CTkFrame
    # whose default height is 200) cannot inflate the whole header band.
    # pack_propagate(False) blocks children from re-sizing the row.
    row_height = font_size + 8
    row = ctk.CTkFrame(parent, fg_color="transparent", height=row_height)
    row.pack_propagate(False)
    bar = ctk.CTkFrame(row, width=3, fg_color=accent, corner_radius=0)
    bar.pack(side="left", padx=(0, 6), pady=2, fill="y")
    ctk.CTkLabel(
        row,
        text=text,
        font=ctk.CTkFont(size=font_size, weight="bold"),
        text_color="white",
    ).pack(side="left", anchor="w")
    return row


def make_numbered_chip(
    parent,
    label: str,
    *,
    accent: str,
) -> ctk.CTkFrame:
    """
    Small ~24 px disc chip with a bold uppercase label centered inside
    (e.g. "01", "02", "03"). `accent` is the label text color, typically
    a step-specific accent (blue for Step 01/02, emerald for Step 03).

    The disc itself uses CHIP_BG / CHIP_BORDER so all chips read as the
    same surface family. Caller packs the returned frame.

    The inner label is exposed as `chip.text_label` so callers can update
    the chip text without reaching into winfo_children().
    """
    chip = ctk.CTkFrame(
        parent,
        width=24,
        height=24,
        corner_radius=12,
        fg_color=CHIP_BG,
        border_color=CHIP_BORDER,
        border_width=1,
    )
    chip.pack_propagate(False)
    text_label = ctk.CTkLabel(
        chip,
        text=label,
        text_color=accent,
        font=ctk.CTkFont(size=10, weight="bold"),
    )
    text_label.place(relx=0.5, rely=0.5, anchor="center")
    chip.text_label = text_label
    return chip


def make_card_with_accent(
    parent,
    *,
    accent: str,
) -> ctk.CTkFrame:
    """
    Card surface with rounded corners (BG_CARD fill, CARD_BORDER_COLOR
    border) and a 2-px top-edge accent strip in the given color. Returns
    the outer frame; caller packs widgets into the exposed `.content`
    sub-frame, NOT into the outer frame directly — packing into the
    outer would land them under the accent strip.

    The strip is intentionally 2 px (not 1 px) because CTk's antialiasing
    on the rounded outer frame can swallow a single-pixel strip on some
    DPI scales.
    """
    outer = ctk.CTkFrame(
        parent,
        fg_color=BG_CARD,
        corner_radius=16,
        border_color=CARD_BORDER_COLOR,
        border_width=1,
    )
    accent_strip = ctk.CTkFrame(
        outer,
        height=2,
        fg_color=accent,
        corner_radius=0,
    )
    accent_strip.pack(fill="x", side="top", padx=14, pady=(0, 0))
    content = ctk.CTkFrame(outer, fg_color="transparent")
    content.pack(fill="both", expand=True, padx=14, pady=(8, 12))
    outer.content = content
    return outer


_MATCH_TYPE_BADGES = {
    "exact_replace": ("EXACT MATCH", "blue"),
    "regex_replace": ("REGEX", "amber"),
}


def make_rule_card(
    parent,
    *,
    rule_id: str,
    before: str,
    after: str,
    match_type: str,
    variant: str = "proposed",
    enabled: bool = True,
    description: str = "",
    on_toggle=None,
    on_delete=None,
) -> ctk.CTkFrame:
    """
    Unified rule card consumed by both Step 03 (proposed rules) and the
    Active Library (saved rules). Layout:

        [dot] RULE-ID  [BADGE]                              [✗ delete]
        before-text  →  after-text
        description   (italic, muted; only when non-empty)

    `variant`:
        "proposed"  display only — no dot, no delete button
        "active"    leading state dot (color from `enabled`, clickable
                    if on_toggle is provided), trailing delete X
                    (calls on_delete(rule_id) if provided)

    `description`: optional one-line note rendered below the body row in
    muted italic. Empty string (default) omits the line entirely so
    cards without a description don't have a hanging gap.

    `match_type` must be one of the keys in _MATCH_TYPE_BADGES — KeyError
    on anything else, intentional so a typo or a future fuzzy_replace
    type fails loudly rather than silently picking a default badge.

    Caller packs the returned frame. Selected sub-widgets are exposed as
    attributes (`card.id_label`, `card.badge`, `card.before_label`,
    `card.after_label`, plus `card.dot` / `card.delete_btn` on the
    active variant, plus `card.description_label` when description is
    non-empty) so tests and callers can introspect or update them
    without `winfo_children()` traversal.
    """
    card = ctk.CTkFrame(
        parent,
        fg_color=BG_CARD,
        corner_radius=10,
        border_color=CARD_BORDER_COLOR,
        border_width=1,
    )

    top = ctk.CTkFrame(card, fg_color="transparent")
    top.pack(fill="x", padx=10, pady=(8, 4))

    if variant == "active":
        dot_color = DOT_ENABLED if enabled else DOT_DISABLED
        dot = ctk.CTkFrame(
            top,
            width=8,
            height=8,
            corner_radius=4,
            fg_color=dot_color,
        )
        dot.pack_propagate(False)
        dot.pack(side="left", padx=(0, 8))
        if on_toggle is not None:
            dot.configure(cursor="hand2")
            dot.bind(
                "<Button-1>",
                lambda _e: on_toggle(rule_id, not enabled),
                add=True,
            )
        card.dot = dot

    id_label = ctk.CTkLabel(
        top,
        text=rule_id,
        font=ctk.CTkFont(family="Courier New", size=10),
        text_color=TEXT_DIM,
    )
    id_label.pack(side="left")

    badge_text, badge_variant = _MATCH_TYPE_BADGES[match_type]
    badge = make_status_pill(top, badge_text, variant=badge_variant)
    badge.pack(side="left", padx=(8, 0))

    if variant == "active" and on_delete is not None:
        delete_btn = ctk.CTkButton(
            top,
            text="✗",  # ✗
            width=20,
            height=20,
            fg_color="transparent",
            text_color=TEXT_DIM,
            hover_color=DELETE_HOVER_BG,
            font=ctk.CTkFont(size=14),
            command=lambda: on_delete(rule_id),
        )
        delete_btn.pack(side="right")
        card.delete_btn = delete_btn

    body = ctk.CTkFrame(card, fg_color="transparent")
    body.pack(fill="x", padx=10, pady=(0, 8))

    before_label = ctk.CTkLabel(
        body,
        text=before,
        font=ctk.CTkFont(family="Courier New", size=11, slant="italic"),
        text_color=TEXT_SECONDARY,
        anchor="w",
        justify="left",
    )
    before_label.pack(side="left", fill="x", expand=True)

    arrow_label = ctk.CTkLabel(
        body,
        text="→",  # →
        font=ctk.CTkFont(size=12),
        text_color=TEXT_DIM,
    )
    arrow_label.pack(side="left", padx=8)

    after_label = ctk.CTkLabel(
        body,
        text=after,
        font=ctk.CTkFont(family="Courier New", size=11),
        text_color=PILL_EMERALD_TEXT,
        anchor="w",
        justify="left",
    )
    after_label.pack(side="left", fill="x", expand=True)

    if description:
        desc_label = ctk.CTkLabel(
            card,
            text=description,
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        desc_label.pack(fill="x", padx=10, pady=(0, 8))
        card.description_label = desc_label

    card.id_label = id_label
    card.badge = badge
    card.before_label = before_label
    card.after_label = after_label
    return card
