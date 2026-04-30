# UI Design Rules

Status: ACTIVE
Precedence: `CLAUDE.md` remains authoritative for architecture and invariants. This file defines UI presentation tokens only.

## Purpose

This document defines the baseline visual rules for controls in the desktop UI so labels, button sizing, colors, and text-input dimensions stay consistent across tabs.

## Universal Rules

1. **Use shared tokens from `ui/_components.py`** for colors, button sizing, and typography instead of inline one-off values.
2. **Primary and utility action labels use one typography baseline**:
   - `BTN_FONT_SIZE = 13`
   - `BTN_FONT_WEIGHT = "bold"`
3. **Standard action-button height** is `BTN_HEIGHT_STANDARD = 32`.
4. **Standard single-line text-input height** is `TEXTBOX_HEIGHT_STANDARD = 32` (for CTkEntry / single-line fields unless a control explicitly requires a different height).
5. **Action color semantics are fixed by intent**:
   - Primary: `BTN_PRIMARY_AMBER`
   - Safe/commit: `BTN_SAFE_GREEN`
   - AI: `BTN_AI_PURPLE`
   - Utility/file-pickers: `BTN_UTILITY_BLUE`
   - Secondary outline: `BTN_OUTLINE_BORDER` + transparent fill
6. **Card visual consistency**:
   - `CARD_BORDER_COLOR`, `CARD_BORDER_WIDTH`
   - `CARD_GAP_PY`, `CARD_INNER_PADX`, `CARD_INNER_PADY`
7. **Surface/text hierarchy** should use existing tokens where possible:
   - Surfaces: `BG_BASE`, `BG_CARD`, `BG_TRANSCRIPT`
   - Text: `TEXT_PRIMARY`, `TEXT_SECONDARY`, `TEXT_MUTED`, `TEXT_DIM`

## Implementation Note

When updating UI, prefer adding/updating a token in `ui/_components.py` first, then consuming it where needed. This keeps future visual changes centralized and low-risk.
