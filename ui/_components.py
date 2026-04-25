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
