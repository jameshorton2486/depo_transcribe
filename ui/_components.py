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

BG_BASE = "#0a0c10"        # outermost app background
BG_CARD = "#0f1218"        # card surface (one level above base)
BG_TRANSCRIPT = "#07080c"  # transcript editor (one level below base)


# ── Status pill (badge) tokens ───────────────────────────────────────────────
# Colors for small rounded badges used for counts ("Flagged: 5", "Reviewed:
# 120"). Background and border are precomputed blends of the brand hex over
# BG_BASE — the mockup specifies 10% fill / 20% border; CTk has no alpha so
# we bake the result. Text color reuses the brand hex unchanged so badges
# read as the same family as section headers / speaker labels.

# Amber family (BTN_PRIMARY_AMBER #B8860B blended over BG_BASE)
PILL_AMBER_BG = "#1B180F"      # 10% B8860B
PILL_AMBER_BORDER = "#2D240F"  # 20% B8860B
PILL_AMBER_TEXT = BTN_PRIMARY_AMBER

# Blue family (SECTION_HEADER_ACCENT #3A7FBF blended over BG_BASE)
PILL_BLUE_BG = "#0F1822"       # 10% 3A7FBF
PILL_BLUE_BORDER = "#142333"   # 20% 3A7FBF
PILL_BLUE_TEXT = SECTION_HEADER_ACCENT

# Emerald family (#10B981 blended over BG_BASE) — for the "Done" pill
# that replaces Remaining when the reviewer has confirmed every flag.
# BTN_SAFE_GREEN (#1A6B3A) is too muted for badge text on the dark surface,
# and the prior single-label scheme used #44AA44 inline only; the emerald
# family is genuinely missing from the palette.
PILL_EMERALD_BG = "#0B1D1B"      # 10% 10B981
PILL_EMERALD_BORDER = "#0B2F27"  # 20% 10B981
PILL_EMERALD_TEXT = "#10B981"


_PILL_VARIANTS = {
    "amber": (PILL_AMBER_BG, PILL_AMBER_BORDER, PILL_AMBER_TEXT),
    "blue": (PILL_BLUE_BG, PILL_BLUE_BORDER, PILL_BLUE_TEXT),
    "emerald": (PILL_EMERALD_BG, PILL_EMERALD_BORDER, PILL_EMERALD_TEXT),
}


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
    row = ctk.CTkFrame(parent, fg_color="transparent")
    # 3px-wide colored strip; corner_radius=0 keeps it crisp.
    bar = ctk.CTkFrame(row, width=3, fg_color=accent, corner_radius=0)
    bar.pack(side="left", padx=(0, 6), pady=2, fill="y")
    ctk.CTkLabel(
        row,
        text=text,
        font=ctk.CTkFont(size=font_size, weight="bold"),
        text_color="white",
    ).pack(side="left", anchor="w")
    return row
