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
