"""
ui/tab_transcribe.py

Main transcription UI — file picker, settings, keyterms, progress, buttons, preview.
Includes IntakeReviewDialog for reviewing/editing AI-extracted case data.
"""

import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app_logging import get_logger
from core.keyterm_extractor import (
    MAX_KEYTERMS,
    extract_keyterms_from_text,
    merge_keyterms,
)

logger = get_logger(__name__)
_DEFAULT_BUTTON_COLOR = ["#3B8ED0", "#1F6AA5"]


# Default output directory
_DEFAULT_BASE_DIR = r"C:\Users\james\Depositions"

# Supported file extensions
_AUDIO_VIDEO_EXTENSIONS = (
    ("Audio / Video files", "*.mp3 *.mp4 *.wav *.m4a *.mov *.avi *.mkv *.flac"),
    ("All files", "*.*"),
)

# ── Row colours for the review dialog ────────────────────────────────────────
_ROW_BG_A = "#1A1A2E"
_ROW_BG_B = "#16213E"
_LABEL_COLOR = "#8888AA"
_ENTRY_FG = "#0F3460"
_ENTRY_BORDER = "#1E3A5F"
_HEADER_BG = "#1E3A5F"
_AMBER = "#B8860B"
_AMBER_DARK = "#2A1A00"


# ═══════════════════════════════════════════════════════════════════════════════
#  IntakeReviewDialog
# ═══════════════════════════════════════════════════════════════════════════════

class IntakeReviewDialog(ctk.CTkToplevel):
    """Modal dialog for reviewing and editing AI-extracted case intake data.
    Field labels map directly to UFM page generator field names."""

    # ── UFM Title Page (Fig. 03) ─────────────────────────────────
    _TITLE_PAGE_FIELDS = [
        ("cause_number", "Cause Number"),
        ("plaintiff_name", "Plaintiff"),
        ("defendant_name", "Defendant"),
        ("case_style", "Case Style"),
        ("court_type", "Court Type"),
        ("county", "County"),
        ("state", "State"),
        ("judicial_district", "Judicial District"),
    ]
    # ── Deposition Details ───────────────────────────────────────
    _DEPO_DETAIL_FIELDS = [
        ("depo_date", "Date of Deposition"),
        ("depo_time_start", "Scheduled Start Time"),
        ("depo_location", "Location"),
        ("depo_method", "Method"),
    ]
    # ── Witness / Deponent ───────────────────────────────────────
    _WITNESS_FIELDS = [
        ("witness_name", "Witness Full Name"),
    ]
    # ── Appearances Page (Fig. 04) — per-attorney ────────────────
    _COUNSEL_FIELDS = [
        ("name", "Attorney Name"),
        ("sbot", "State Bar No. (SBOT)"),
        ("firm", "Firm Name"),
        ("address", "Address"),
        ("phone", "Phone"),
        ("party", "Represents"),
    ]
    # ── Reporter's Certificate (Fig. 05) ─────────────────────────
    _REPORTER_FIELDS = [
        ("reporter_name", "Reporter Name"),
        ("csr_number", "CSR Number"),
        ("reporter_agency", "Agency"),
    ]
    # ── Copy / Billing ───────────────────────────────────────────
    _BILLING_FIELDS = [
        ("ordered_by", "Ordered By"),
        ("ordering_firm", "Ordering Firm"),
    ]

    def __init__(self, parent, case_data: dict):
        super().__init__(parent)
        self._parent = parent
        self._data = case_data
        self._entries: dict[str, ctk.CTkEntry] = {}  # flat key -> entry widget
        self._row_index = 0  # alternating row counter

        self.title("Case Intake \u2014 Review & Edit")
        self.geometry("900x700")
        self.resizable(True, True)
        self.grab_set()

        self._build_header()
        self._build_content()
        self._build_buttons()

    # ── Header ───────────────────────────────────────────────────────────────

    def _build_header(self):
        header = ctk.CTkFrame(self, height=46, fg_color=_HEADER_BG, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="CASE INTAKE REVIEW",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="white",
        ).pack(side="left", padx=16)

        ctk.CTkLabel(
            header, text="Edit any field \u2014 changes apply immediately",
            font=ctk.CTkFont(size=11), text_color="#AABBCC",
        ).pack(side="right", padx=16)

    # ── Scrollable content ───────────────────────────────────────────────────

    def _build_content(self):
        from core.ufm_field_mapper import map_intake_to_ufm

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self._row_index = 0

        # Map extracted data to UFM fields
        self._ufm = map_intake_to_ufm(self._data)

        # ── Title Page (UFM Fig. 03) ─────────────────────────────
        self._add_section_header("TITLE PAGE  (UFM Fig. 03)")
        for key, label in self._TITLE_PAGE_FIELDS:
            self._add_row(key, label, self._ufm.get(key, ""))

        # ── Deposition Details ───────────────────────────────────
        self._add_section_header("DEPOSITION DETAILS")
        for key, label in self._DEPO_DETAIL_FIELDS:
            self._add_row(key, label, self._ufm.get(key, ""))

        # ── Witness / Deponent ───────────────────────────────────
        self._add_section_header("WITNESS / DEPONENT")
        for key, label in self._WITNESS_FIELDS:
            self._add_row(key, label, self._ufm.get(key, ""))

        # ── Appearances Page (UFM Fig. 04) ───────────────────────
        self._add_section_header("APPEARANCES PAGE  (UFM Fig. 04)")

        p_counsel = self._ufm.get("plaintiff_counsel", [])
        for i, atty in enumerate(p_counsel):
            self._add_sub_header(f"Plaintiff Counsel {i + 1}")
            for key, label in self._COUNSEL_FIELDS:
                self._add_row(f"pc.{i}.{key}", label, atty.get(key, ""))

        d_counsel = self._ufm.get("defense_counsel", [])
        for i, atty in enumerate(d_counsel):
            self._add_sub_header(f"Defense Counsel {i + 1}")
            for key, label in self._COUNSEL_FIELDS:
                self._add_row(f"dc.{i}.{key}", label, atty.get(key, ""))

        # ── Reporter's Certificate (UFM Fig. 05) ────────────────
        self._add_section_header("REPORTER'S CERTIFICATE  (UFM Fig. 05)")
        for key, label in self._REPORTER_FIELDS:
            self._add_row(key, label, self._ufm.get(key, ""))

        # ── Copy / Billing ───────────────────────────────────────
        self._add_section_header("COPY / BILLING")
        for key, label in self._BILLING_FIELDS:
            self._add_row(key, label, self._ufm.get(key, ""))

        # ── Discrepancies ────────────────────────────────────────
        discreps = self._data.get("discrepancies", [])
        if discreps:
            self._add_section_header("DISCREPANCIES")
            for d in discreps:
                self._add_discrepancy_block(d)

    def _add_section_header(self, title: str):
        frame = ctk.CTkFrame(self._scroll, fg_color=_HEADER_BG, corner_radius=4, height=32)
        frame.pack(fill="x", pady=(10, 2))
        frame.pack_propagate(False)
        # Amber left border via a small colored frame
        ctk.CTkFrame(frame, width=4, fg_color=_AMBER, corner_radius=0).pack(
            side="left", fill="y"
        )
        ctk.CTkLabel(
            frame, text=title, font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white",
        ).pack(side="left", padx=12)

    def _add_sub_header(self, title: str):
        sep = ctk.CTkFrame(self._scroll, height=1, fg_color="#333355")
        sep.pack(fill="x", pady=(8, 2), padx=8)
        ctk.CTkLabel(
            self._scroll, text=title, font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#CCCCDD",
        ).pack(anchor="w", padx=16, pady=(2, 2))

    def _add_row(self, key: str, label: str, value: str):
        bg = _ROW_BG_A if self._row_index % 2 == 0 else _ROW_BG_B
        self._row_index += 1

        row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=2)
        row.pack(fill="x", padx=4, pady=1)

        ctk.CTkLabel(
            row, text=label, width=220, anchor="w",
            font=ctk.CTkFont(size=11), text_color=_LABEL_COLOR,
        ).pack(side="left", padx=(12, 8), pady=4)

        entry = ctk.CTkEntry(
            row, fg_color=_ENTRY_FG, border_color=_ENTRY_BORDER, border_width=1,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=4)
        entry.insert(0, value or "")
        self._entries[key] = entry

    def _add_discrepancy_block(self, d: dict):
        block = ctk.CTkFrame(
            self._scroll, fg_color=_AMBER_DARK, border_color=_AMBER,
            border_width=1, corner_radius=6,
        )
        block.pack(fill="x", padx=8, pady=4)

        for label_text, key in [
            ("Field", "field"),
            ("Document 1 says", "value_1"),
            ("Document 2 says", "value_2"),
            ("Recommendation", "recommendation"),
        ]:
            row = ctk.CTkFrame(block, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=1)
            ctk.CTkLabel(
                row, text=f"{label_text}:", width=160, anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"), text_color=_AMBER,
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=d.get(key, ""), anchor="w", wraplength=600,
                font=ctk.CTkFont(size=11), text_color="#DDCCAA",
            ).pack(side="left", fill="x", expand=True)

    # ── Bottom buttons ───────────────────────────────────────────────────────

    def _build_buttons(self):
        bar = ctk.CTkFrame(self, fg_color="transparent", height=50)
        bar.pack(fill="x", padx=12, pady=(4, 10))

        # Left — export buttons
        ctk.CTkButton(
            bar, text="Export as PDF", width=130, command=self._export_pdf,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="Export as Word", width=130, command=self._export_word,
        ).pack(side="left")

        # Right — save / cancel
        ctk.CTkButton(
            bar, text="Save Changes", fg_color=_AMBER, hover_color="#9A7209",
            font=ctk.CTkFont(weight="bold"), width=140, command=self._save_changes,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            bar, text="Cancel", width=100,
            fg_color="transparent", border_width=1, border_color="#555555",
            command=self.destroy,
        ).pack(side="right")

    # ── Collect edits ────────────────────────────────────────────────────────

    def _collect_ufm_fields(self) -> dict:
        """Read all entry widgets back into a UFM field dict."""
        ufm = dict(self._ufm)  # start from the mapped version

        # Rebuild counsel lists
        p_counsel = list(ufm.get("plaintiff_counsel", []))
        d_counsel = list(ufm.get("defense_counsel", []))

        for flat_key, entry in self._entries.items():
            val = entry.get()
            parts = flat_key.split(".")

            if parts[0] == "pc":
                idx = int(parts[1])
                while len(p_counsel) <= idx:
                    p_counsel.append({})
                p_counsel[idx][parts[2]] = val
            elif parts[0] == "dc":
                idx = int(parts[1])
                while len(d_counsel) <= idx:
                    d_counsel.append({})
                d_counsel[idx][parts[2]] = val
            else:
                # Top-level UFM field
                ufm[flat_key] = val

        ufm["plaintiff_counsel"] = p_counsel
        ufm["defense_counsel"] = d_counsel
        ufm["discrepancies"] = self._data.get("discrepancies", [])
        return ufm

    # ── Save Changes ─────────────────────────────────────────────────────────

    def _save_changes(self):
        import json as _json

        ufm = self._collect_ufm_fields()

        # Store on parent
        self._parent._ufm_fields = ufm
        self._parent._extracted_case_data = self._data  # keep raw data too

        # Sync filing-path vars from UFM fields
        if ufm.get("cause_number"):
            self._parent._cause_var.set(ufm["cause_number"])
        witness = ufm.get("witness_name", "")
        if witness:
            parts = witness.strip().split()
            if parts:
                self._parent._lastname_var.set(parts[-1])
        if ufm.get("depo_date"):
            self._parent._date_var.set(ufm["depo_date"])

        # Also push into _populate_case_fields for any UI refresh
        self._parent._populate_case_fields(self._data)

        # Save ufm_fields.json to output folder if available
        out_dir = self._parent._last_output_dir
        if out_dir and os.path.isdir(out_dir):
            cause = ufm.get("cause_number", "unknown")
            witness_parts = ufm.get("witness_name", "").split()
            lname = witness_parts[-1] if witness_parts else "unknown"
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ufm_path = Path(out_dir) / f"{cause}_{lname}_{stamp}_ufm_fields.json"
            try:
                with open(ufm_path, "w", encoding="utf-8") as f:
                    _json.dump(ufm, f, indent=2, ensure_ascii=False)
                self._parent._append_log(f"Saved UFM fields: {ufm_path.name}")
            except Exception as exc:
                self._parent._append_log(f"Warning: could not save UFM fields: {exc}")

        self.destroy()

        # Brief green status
        self._parent._status_label.configure(
            text="UFM fields saved \u2014 ready for transcript generation",
            text_color="#44FF44",
        )
        self._parent.after(
            3000,
            lambda: self._parent._status_label.configure(
                text="Ready", text_color="gray"
            ),
        )

    # ── Helper: gather flat rows for export ──────────────────────────────────

    def _gather_sections(self) -> list:
        """Return [(section_title, [(label, value), ...]), ...] for export."""
        ufm = self._collect_ufm_fields()
        sections = []

        # Title Page (UFM Fig. 03)
        rows = [(lbl, ufm.get(k, "")) for k, lbl in self._TITLE_PAGE_FIELDS]
        sections.append(("TITLE PAGE  (UFM Fig. 03)", rows))

        # Deposition Details
        rows = [(lbl, ufm.get(k, "")) for k, lbl in self._DEPO_DETAIL_FIELDS]
        sections.append(("Deposition Details", rows))

        # Witness
        rows = [(lbl, ufm.get(k, "")) for k, lbl in self._WITNESS_FIELDS]
        sections.append(("Witness / Deponent", rows))

        # Appearances Page (UFM Fig. 04) — Plaintiff Counsel
        for i, pc in enumerate(ufm.get("plaintiff_counsel", [])):
            rows = [(lbl, pc.get(k, "")) for k, lbl in self._COUNSEL_FIELDS]
            sections.append((f"APPEARANCES (UFM Fig. 04) \u2014 Plaintiff Counsel {i + 1}", rows))

        # Appearances Page — Defense Counsel
        for i, dc in enumerate(ufm.get("defense_counsel", [])):
            rows = [(lbl, dc.get(k, "")) for k, lbl in self._COUNSEL_FIELDS]
            sections.append((f"APPEARANCES (UFM Fig. 04) \u2014 Defense Counsel {i + 1}", rows))

        # Reporter's Certificate (UFM Fig. 05)
        rows = [(lbl, ufm.get(k, "")) for k, lbl in self._REPORTER_FIELDS]
        sections.append(("REPORTER'S CERTIFICATE  (UFM Fig. 05)", rows))

        # Copy / Billing
        rows = [(lbl, ufm.get(k, "")) for k, lbl in self._BILLING_FIELDS]
        sections.append(("Copy / Billing", rows))

        return sections

    # ── Export PDF ────────────────────────────────────────────────────────────

    def _export_pdf(self):
        data = self._collect_ufm_fields()
        cause = data.get("cause_number", "intake") or "intake"
        witness = data.get("witness_name", "").split()
        lname = witness[-1] if witness else "unknown"
        default_name = f"{cause}_{lname}_intake.pdf"

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF files", "*.pdf")],
        )
        if not path:
            return

        try:
            self._write_pdf(path, data)
            messagebox.showinfo("Exported", f"PDF saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("PDF Export Failed", str(exc))

    def _write_pdf(self, path: str, data: dict):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        doc = SimpleDocTemplate(path, pagesize=letter,
                                leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                                topMargin=0.6 * inch, bottomMargin=0.6 * inch)
        styles = getSampleStyleSheet()
        elements = []

        # Custom styles
        title_style = ParagraphStyle(
            "IntakeTitle", parent=styles["Title"],
            fontSize=18, textColor=colors.HexColor("#1E3A5F"),
            spaceAfter=6,
        )
        section_style = ParagraphStyle(
            "SectionHead", parent=styles["Heading2"],
            fontSize=12, textColor=colors.HexColor("#1E3A5F"),
            spaceBefore=14, spaceAfter=4,
        )
        label_style = ParagraphStyle(
            "FieldLabel", parent=styles["Normal"],
            fontSize=9, textColor=colors.grey,
        )
        value_style = ParagraphStyle(
            "FieldValue", parent=styles["Normal"],
            fontSize=10, textColor=colors.black,
        )
        warn_style = ParagraphStyle(
            "WarnText", parent=styles["Normal"],
            fontSize=9, textColor=colors.HexColor("#B8860B"),
        )

        # Header
        elements.append(Paragraph("SA Legal Solutions \u2014 Court Reporting", styles["Normal"]))
        elements.append(Paragraph(
            f"Generated: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}",
            styles["Normal"],
        ))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("CASE INTAKE SHEET", title_style))
        elements.append(Spacer(1, 8))

        # Sections
        for section_title, rows in self._gather_sections():
            elements.append(Paragraph(section_title, section_style))
            table_data = []
            for label, value in rows:
                table_data.append([
                    Paragraph(label, label_style),
                    Paragraph(value or "\u2014", value_style),
                ])
            if table_data:
                t = Table(table_data, colWidths=[2.2 * inch, 4.8 * inch])
                t.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
                ]))
                elements.append(t)

        # Discrepancies
        discreps = self._data.get("discrepancies", [])
        if discreps:
            elements.append(Paragraph("Discrepancies", section_style))
            for d in discreps:
                field = d.get("field", "")
                flag = f"\u26a0 FLAG: {field}"
                elements.append(Paragraph(flag, warn_style))
                elements.append(Paragraph(
                    f"Doc 1: {d.get('value_1', '')}  |  Doc 2: {d.get('value_2', '')}",
                    styles["Normal"],
                ))
                elements.append(Paragraph(
                    f"Recommendation: {d.get('recommendation', '')}",
                    ParagraphStyle("Italic", parent=styles["Normal"], fontSize=9,
                                   textColor=colors.grey),
                ))
                elements.append(Spacer(1, 6))

        # Footer
        cause_num = data.get("cause_number", "")
        witness_name = data.get("witness_name", "")
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(
            f"{cause_num}  \u00b7  {witness_name}  \u00b7  SA Legal Solutions",
            ParagraphStyle("Footer", parent=styles["Normal"],
                           fontSize=8, textColor=colors.grey, alignment=1),
        ))

        doc.build(elements)

    # ── Export Word ──────────────────────────────────────────────────────────

    def _export_word(self):
        data = self._collect_ufm_fields()
        cause = data.get("cause_number", "intake") or "intake"
        witness = data.get("witness_name", "").split()
        lname = witness[-1] if witness else "unknown"
        default_name = f"{cause}_{lname}_intake.docx"

        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            initialfile=default_name,
            filetypes=[("Word documents", "*.docx")],
        )
        if not path:
            return

        try:
            self._write_docx(path, data)
            messagebox.showinfo("Exported", f"Word document saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Word Export Failed", str(exc))

    def _write_docx(self, path: str, data: dict):
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document()

        # Title
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_p.add_run("CASE INTAKE SHEET")
        run.bold = True
        run.font.size = Pt(16)
        run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)

        def _set_cell_shading(cell, hex_color: str):
            shading = OxmlElement("w:shd")
            shading.set(qn("w:fill"), hex_color)
            shading.set(qn("w:val"), "clear")
            cell._tc.get_or_add_tcPr().append(shading)

        def _remove_cell_borders(cell):
            tc_pr = cell._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for edge in ("top", "left", "bottom", "right"):
                el = OxmlElement(f"w:{edge}")
                el.set(qn("w:val"), "none")
                el.set(qn("w:sz"), "0")
                borders.append(el)
            tc_pr.append(borders)

        # Sections
        for section_title, rows in self._gather_sections():
            # Section heading
            hp = doc.add_paragraph()
            hr = hp.add_run(f"  {section_title}")
            hr.bold = True
            hr.font.size = Pt(12)
            hr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            # Shading on paragraph
            p_pr = hp._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:fill"), "1E3A5F")
            shd.set(qn("w:val"), "clear")
            p_pr.append(shd)

            # Table
            table = doc.add_table(rows=len(rows), cols=2)
            table.columns[0].width = Inches(2.0)
            table.columns[1].width = Inches(4.5)

            for i, (label, value) in enumerate(rows):
                cell_label = table.cell(i, 0)
                cell_value = table.cell(i, 1)

                cell_label.text = label
                cell_value.text = value or "\u2014"

                # Style label
                for p in cell_label.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(10)
                        r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

                # Style value
                for p in cell_value.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(10)

                # Alternating shading + borderless
                shade = "FFFFFF" if i % 2 == 0 else "F5F5F5"
                _set_cell_shading(cell_label, shade)
                _set_cell_shading(cell_value, shade)
                _remove_cell_borders(cell_label)
                _remove_cell_borders(cell_value)

        # Discrepancies
        discreps = self._data.get("discrepancies", [])
        if discreps:
            hp = doc.add_paragraph()
            hr = hp.add_run("  DISCREPANCIES")
            hr.bold = True
            hr.font.size = Pt(12)
            hr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            p_pr = hp._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:fill"), "B8860B")
            shd.set(qn("w:val"), "clear")
            p_pr.append(shd)

            d_table = doc.add_table(rows=len(discreps) + 1, cols=3)
            # Header row
            for ci, hdr in enumerate(["Field", "Conflict", "Recommendation"]):
                cell = d_table.cell(0, ci)
                cell.text = hdr
                _set_cell_shading(cell, "B8860B")
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.bold = True
                        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        r.font.size = Pt(10)

            for ri, d in enumerate(discreps, start=1):
                d_table.cell(ri, 0).text = d.get("field", "")
                d_table.cell(ri, 1).text = (
                    f"Doc 1: {d.get('value_1', '')}\nDoc 2: {d.get('value_2', '')}"
                )
                d_table.cell(ri, 2).text = d.get("recommendation", "")
                for ci in range(3):
                    _set_cell_shading(d_table.cell(ri, ci), "FFF3CD")

        # Footer
        footer_p = doc.add_paragraph()
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fr = footer_p.add_run(
            f"{data.get('cause_number', '')}  \u00b7  "
            f"{data.get('witness_name', '')}  \u00b7  SA Legal Solutions"
        )
        fr.font.size = Pt(8)
        fr.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

        doc.save(path)


# ═══════════════════════════════════════════════════════════════════════════════
#  TranscribeTab
# ═══════════════════════════════════════════════════════════════════════════════

class TranscribeTab(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._selected_file: str = ""
        self._last_transcript_path: str | None = None
        self._current_txt_path: str | None = None
        self._transcript_text: str = ""
        self._last_output_dir: str = ""
        self._running = False
        self._speaker_entries: dict[str, ctk.CTkEntry] = {}
        self._extracted_case_data: dict = {}
        self._ufm_fields: dict = {}
        self._reporter_notes_text: str = ""
        self._current_keyterms: list[str] | None = None
        self._pdf_already_loaded = False
        self._current_case_path: str | None = None

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Scrollable container for the whole tab
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True)

        # ── SECTION 1: Audio File Card ───────────────────────────────────────
        file_card = ctk.CTkFrame(container)
        file_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            file_card,
            text="Audio / Video File",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 0))

        ctk.CTkLabel(
            file_card,
            text="MP3  \u00b7  MP4  \u00b7  WAV  \u00b7  M4A  \u00b7  MOV  \u00b7  AVI  \u00b7  MKV  \u00b7  FLAC",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", padx=12)

        file_row = ctk.CTkFrame(file_card, fg_color="transparent")
        file_row.pack(fill="x", padx=12, pady=(6, 10))

        self._file_entry = ctk.CTkEntry(
            file_row, placeholder_text="No file selected", state="disabled"
        )
        self._file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            file_row, text="Browse\u2026", width=90, command=self._browse_file
        ).pack(side="right")

        # ── SECTION 2: Settings Row ──────────────────────────────────────────
        settings_card = ctk.CTkFrame(container)
        settings_card.pack(fill="x", pady=(0, 10))

        settings_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_row.pack(fill="x", padx=12, pady=10)
        settings_row.columnconfigure((0, 1), weight=1)

        # LEFT — Model
        model_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
        model_frame.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkLabel(model_frame, text="Model", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w"
        )
        self._model_var = ctk.StringVar(value="nova-3")
        self._model_combo = ctk.CTkComboBox(
            model_frame,
            values=["nova-3", "nova-3-medical"],
            variable=self._model_var,
            state="readonly",
        )
        self._model_combo.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            model_frame,
            text="Utterance Split (utt_split)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", pady=(10, 0))
        self._utt_split_var = ctk.DoubleVar(value=1.2)
        self._utt_split_label = ctk.CTkLabel(
            model_frame,
            text="1.20",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        utt_slider = ctk.CTkSlider(
            model_frame,
            from_=0.3,
            to=2.0,
            number_of_steps=17,
            variable=self._utt_split_var,
            command=lambda v: self._utt_split_label.configure(text=f"{float(v):.2f}"),
        )
        utt_slider.pack(fill="x", pady=(4, 0))
        self._utt_split_label.pack(anchor="e")

        # RIGHT — Audio Quality
        quality_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
        quality_frame.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ctk.CTkLabel(
            quality_frame, text="Audio Quality", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w")
        self._quality_var = ctk.StringVar(value="Clean (good/excellent audio)")
        self._quality_combo = ctk.CTkComboBox(
            quality_frame,
            values=[
                "Clean (good/excellent audio)",
                "Default (fair audio)",
                "Aggressive (noisy/poor audio)",
            ],
            variable=self._quality_var,
            state="readonly",
            width=240,
        )
        self._quality_combo.pack(fill="x", pady=(4, 0))

        # ── SECTION 2b: Case Information ─────────────────────────────────────
        case_card = ctk.CTkFrame(container)
        case_card.pack(fill="x", pady=(0, 10))

        case_header_row = ctk.CTkFrame(case_card, fg_color="transparent")
        case_header_row.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(
            case_header_row, text="Case Information",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")

        case_grid = ctk.CTkFrame(case_card, fg_color="transparent")
        case_grid.pack(fill="x", padx=12, pady=(0, 4))
        case_grid.columnconfigure((0, 1), weight=1)

        # Row 0 — Base Save Folder (full width)
        base_frame = ctk.CTkFrame(case_grid, fg_color="transparent")
        base_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=2)

        ctk.CTkLabel(base_frame, text="Base Save Folder", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        base_row = ctk.CTkFrame(base_frame, fg_color="transparent")
        base_row.pack(fill="x", pady=(2, 0))

        self._base_dir_var = ctk.StringVar(value=_DEFAULT_BASE_DIR)
        self._base_dir_entry = ctk.CTkEntry(base_row, textvariable=self._base_dir_var)
        self._base_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._base_dir_var.trace_add("write", lambda *_: self._update_path_preview())

        ctk.CTkButton(
            base_row, text="Browse\u2026", width=80, command=self._browse_base_dir
        ).pack(side="right")

        # Row 1 — Cause Number + Witness Last Name
        cause_frame = ctk.CTkFrame(case_grid, fg_color="transparent")
        cause_frame.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=2)

        cause_label_row = ctk.CTkFrame(cause_frame, fg_color="transparent")
        cause_label_row.pack(fill="x")
        ctk.CTkLabel(cause_label_row, text="Cause Number", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self._cause_badge = ctk.CTkLabel(cause_label_row, text="", font=ctk.CTkFont(size=10), width=0)
        self._cause_badge.pack(side="left", padx=(6, 0))

        self._cause_var = ctk.StringVar()
        ctk.CTkEntry(cause_frame, textvariable=self._cause_var, placeholder_text="e.g. 2025CI19595").pack(fill="x", pady=(2, 0))
        self._cause_var.trace_add("write", self._on_cause_changed)

        name_frame = ctk.CTkFrame(case_grid, fg_color="transparent")
        name_frame.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)

        name_label_row = ctk.CTkFrame(name_frame, fg_color="transparent")
        name_label_row.pack(fill="x")
        ctk.CTkLabel(name_label_row, text="Witness Last Name", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self._witness_badge = ctk.CTkLabel(name_label_row, text="", font=ctk.CTkFont(size=10), width=0)
        self._witness_badge.pack(side="left", padx=(6, 0))

        self._lastname_var = ctk.StringVar()
        ctk.CTkEntry(name_frame, textvariable=self._lastname_var, placeholder_text="e.g. Coger").pack(fill="x", pady=(2, 0))
        self._lastname_var.trace_add("write", self._on_lastname_changed)

        # Row 2 — Witness First Name + Deposition Date
        first_frame = ctk.CTkFrame(case_grid, fg_color="transparent")
        first_frame.grid(row=2, column=0, sticky="ew", padx=(0, 8), pady=2)

        ctk.CTkLabel(first_frame, text="Witness First Name", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self._firstname_var = ctk.StringVar()
        ctk.CTkEntry(first_frame, textvariable=self._firstname_var, placeholder_text="e.g. Matthew").pack(fill="x", pady=(2, 0))
        self._firstname_var.trace_add("write", lambda *_: self._update_path_preview())

        date_frame = ctk.CTkFrame(case_grid, fg_color="transparent")
        date_frame.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=2)

        date_label_row = ctk.CTkFrame(date_frame, fg_color="transparent")
        date_label_row.pack(fill="x")
        ctk.CTkLabel(date_label_row, text="Deposition Date", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self._date_badge = ctk.CTkLabel(date_label_row, text="", font=ctk.CTkFont(size=10), width=0)
        self._date_badge.pack(side="left", padx=(6, 0))

        self._date_var = ctk.StringVar(value=datetime.now().strftime("%m/%d/%Y"))
        ctk.CTkEntry(date_frame, textvariable=self._date_var, placeholder_text="MM/DD/YYYY").pack(fill="x", pady=(2, 0))
        self._date_var.trace_add("write", lambda *_: self._update_path_preview())

        # Extraction status label (shown during PDF extraction)
        self._extract_status_label = ctk.CTkLabel(
            case_card, text="", font=ctk.CTkFont(size=11),
            text_color="gray", wraplength=900, anchor="w", justify="left",
        )
        self._extract_status_label.pack(anchor="w", padx=12, pady=(0, 0))

        # Path preview
        self._path_preview_label = ctk.CTkLabel(
            case_card, text="", font=ctk.CTkFont(size=11),
            text_color="gray", wraplength=900, anchor="w", justify="left",
        )
        self._path_preview_label.pack(anchor="w", padx=12, pady=(4, 10))
        self._update_path_preview()

        # ── SECTION 2c: Keyterms ─────────────────────────────────────────────
        keyterms_card = ctk.CTkFrame(container)
        keyterms_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            keyterms_card,
            text="Keyterms (optional)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 0))

        ctk.CTkLabel(
            keyterms_card,
            text=(
                "Upload a PDF or Reporter Notes to extract keyterms.\n"
                "Deepgram uses these to improve spelling accuracy during transcription."
            ),
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        kt_btn_row = ctk.CTkFrame(keyterms_card, fg_color="transparent")
        kt_btn_row.pack(fill="x", padx=12)

        self._upload_pdf_btn = ctk.CTkButton(
            kt_btn_row, text="+ Upload PDF", width=120,
            command=self._handle_pdf_upload,
        )
        self._upload_pdf_btn.pack(side="left")

        self._upload_reporter_notes_btn = ctk.CTkButton(
            kt_btn_row,
            text="+ Reporter Notes",
            width=140,
            command=self._upload_reporter_notes,
        )
        self._upload_reporter_notes_btn.pack(side="left", padx=(8, 0))

        self._review_btn = ctk.CTkButton(
            kt_btn_row,
            text="\U0001f4cb Review & Edit",
            width=150,
            state="disabled",
            command=self._open_review_dialog,
        )

        self._rescan_btn = ctk.CTkButton(
            kt_btn_row,
            text="\U0001f504 Re-Scan",
            width=90,
            command=self._force_rescan,
        )

        self._review_btn.pack(side="right", padx=(4, 0))
        self._rescan_btn.pack(side="right", padx=(4, 0))

        self._keyterms_count_label = ctk.CTkLabel(
            kt_btn_row, text=f"0/{MAX_KEYTERMS} keyterms", font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self._keyterms_count_label.pack(side="left", padx=(12, 0))

        self._keyterms_box = ctk.CTkTextbox(keyterms_card, height=100)
        self._keyterms_box.pack(fill="x", padx=12, pady=(6, 10))
        self._keyterms_box.insert("1.0", "")
        self._keyterms_box.configure(state="disabled")

        # ── SECTION 3: Progress Area ─────────────────────────────────────────
        progress_card = ctk.CTkFrame(container)
        progress_card.pack(fill="x", pady=(0, 10))

        self._progress_bar = ctk.CTkProgressBar(progress_card)
        self._progress_bar.pack(fill="x", padx=12, pady=(10, 4))
        self._progress_bar.set(0)

        self._status_label = ctk.CTkLabel(
            progress_card,
            text="Ready",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self._status_label.pack(anchor="w", padx=12)

        self._log_box = ctk.CTkTextbox(
            progress_card, height=120, state="disabled", fg_color="#1a1a2e"
        )
        self._log_box.pack(fill="x", padx=12, pady=(4, 10))

        # ── SECTION 4: Buttons ───────────────────────────────────────────────
        button_card = ctk.CTkFrame(container, fg_color="transparent")
        button_card.pack(fill="x", pady=(0, 10))

        self._start_btn = ctk.CTkButton(
            button_card,
            text="\u25b6  CREATE TRANSCRIPT",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#B8860B",
            hover_color="#9A7209",
            height=44,
            command=self._on_start,
        )
        self._start_btn.pack(fill="x", padx=12, pady=(0, 6))

        secondary_row = ctk.CTkFrame(button_card, fg_color="transparent")
        secondary_row.pack(fill="x", padx=12)

        self._open_folder_btn = ctk.CTkButton(
            secondary_row,
            text="Open Output Folder",
            state="disabled",
            command=self._open_output_folder,
        )
        self._open_folder_btn.pack(side="left", padx=(0, 8))

        self._open_file_btn = ctk.CTkButton(
            secondary_row,
            text="Open Transcript",
            state="disabled",
            command=self._open_transcript,
        )
        self._open_file_btn.pack(side="left")

        # ── SECTION 5: Transcript Preview ────────────────────────────────────
        preview_card = ctk.CTkFrame(container)
        preview_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            preview_card,
            text="TRANSCRIPT PREVIEW",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self._preview_box = ctk.CTkTextbox(
            preview_card, height=200, state="disabled"
        )
        self._preview_box.pack(fill="x", padx=12, pady=(0, 10))

        # ── SECTION 6: Speaker Labels (hidden until transcript completes) ────
        self._speaker_card = ctk.CTkFrame(container)
        # Not packed yet — shown by _show_speaker_section() after transcription

        ctk.CTkLabel(
            self._speaker_card,
            text="SPEAKER LABELS \u2014 Rename before saving",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 0))

        ctk.CTkLabel(
            self._speaker_card,
            text="Replace generic labels with correct names throughout the transcript",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        # Dynamic rows — rebuilt each time a transcript completes
        self._speaker_rows_frame = ctk.CTkFrame(
            self._speaker_card, fg_color="transparent"
        )
        self._speaker_rows_frame.pack(fill="x", padx=12)

        self._apply_save_btn = ctk.CTkButton(
            self._speaker_card,
            text="Apply & Save Renamed Transcript",
            fg_color="#B8860B",
            hover_color="#9A7209",
            font=ctk.CTkFont(weight="bold"),
            command=self._apply_and_save_labels,
        )
        self._apply_save_btn.pack(fill="x", padx=12, pady=(8, 10))

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _set_entry_text(entry: ctk.CTkEntry, text: str):
        """Set text on a disabled CTkEntry."""
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, text)
        entry.configure(state="disabled")

    def _append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _update_path_preview(self):
        """Update the live path preview label based on case info fields."""
        from core.file_manager import build_case_path

        cause = self._cause_var.get().strip()
        last = self._lastname_var.get().strip()
        first = self._firstname_var.get().strip()
        date = self._date_var.get().strip()
        base = self._base_dir_var.get().strip()

        if cause and last:
            path = build_case_path(base, cause, last, first, date)
            self._path_preview_label.configure(text=f"Will save to: {path}")
            self._current_case_path = path
        else:
            self._path_preview_label.configure(
                text="Will save to: (fill in Cause Number and Witness Name)"
            )
            self._current_case_path = None

    def _get_current_save_path(self):
        return self._current_case_path or ""

    def _on_cause_changed(self, *_):
        self._update_path_preview()
        if not self._cause_var.get().strip():
            self._reset_case_state()

    def _on_lastname_changed(self, *_):
        self._update_path_preview()
        if not self._lastname_var.get().strip():
            self._reset_case_state()

    def _reset_case_state(self):
        """Reset auto-detected case data when switching to a new case."""
        self._pdf_already_loaded = False
        self._reporter_notes_text = ""
        self._current_keyterms = None
        self._extracted_case_data = {}
        self._current_case_path = None
        self._review_btn.configure(state="disabled")
        self._upload_pdf_btn.configure(
            text="+ Upload PDF",
            fg_color=_DEFAULT_BUTTON_COLOR,
            state="normal",
        )
        self._upload_reporter_notes_btn.configure(
            text="+ Reporter Notes",
            fg_color=_DEFAULT_BUTTON_COLOR,
        )
        for badge in (self._cause_badge, self._witness_badge, self._date_badge):
            badge.configure(text="")
        self._extract_status_label.configure(text="")
        self._update_keyterms_count()
        logger.info("Case state reset.")

    def _force_rescan(self):
        """Force re-detection of PDF and reporter notes from source_docs."""
        self._pdf_already_loaded = False
        self._reporter_notes_text = ""
        self._extracted_case_data = {}
        self._review_btn.configure(state="disabled")
        self._upload_pdf_btn.configure(text="+ Upload PDF", fg_color=_DEFAULT_BUTTON_COLOR)
        self._upload_reporter_notes_btn.configure(text="+ Reporter Notes", fg_color=_DEFAULT_BUTTON_COLOR)
        self._extract_status_label.configure(text="")
        self._update_keyterms_count()
        self._auto_detect_source_docs()

    def _auto_detect_source_docs(self):
        """
        Detect PDF and reporter notes from the resolved case folder.
        Only runs when the case folder exists on disk.
        """
        from core.pdf_extractor import find_case_pdf, find_reporter_notes

        base_path = self._get_current_save_path()
        if not base_path or not os.path.isdir(base_path):
            return

        if not self._pdf_already_loaded:
            pdf_path = find_case_pdf(str(base_path))
            if pdf_path:
                logger.info("[Auto-Detect] PDF found: %s", pdf_path)
                self._upload_pdf_btn.configure(
                    text="PDF Auto-Detected",
                    fg_color="#2A6F3A",
                )
                self._pdf_already_loaded = True
                self._handle_pdf_upload(pdf_path=pdf_path, auto_detected=True)
            else:
                logger.info("[Auto-Detect] No PDF found in source_docs.")

        if not self._reporter_notes_text:
            notes_path = find_reporter_notes(str(base_path))
            if notes_path:
                try:
                    self._load_reporter_notes(notes_path, auto_detected=True)
                    logger.info("[Auto-Detect] Reporter notes found: %s", notes_path)
                except Exception as exc:
                    logger.warning("[Auto-Detect] Could not read reporter notes: %s", exc)
            else:
                logger.info("[Auto-Detect] No reporter notes found in source_docs.")

    def _update_keyterms_count(self):
        raw = self._keyterms_box.get("1.0", "end").strip()
        count = len([line for line in raw.splitlines() if line.strip()])
        suffix = " + notes" if self._reporter_notes_text.strip() else ""
        self._keyterms_count_label.configure(text=f"{count}/{MAX_KEYTERMS} keyterms{suffix}")

    def _append_keyterms(self, terms: list[str]):
        self._keyterms_box.configure(state="normal")
        existing = self._keyterms_box.get("1.0", "end").strip()
        if existing:
            self._keyterms_box.insert("end", "\n")
        self._keyterms_box.insert("end", "\n".join(terms))
        self._keyterms_box.configure(state="disabled")
        self._update_keyterms_count()

    def _populate_case_fields(self, data: dict):
        """Refresh main UI fields from extracted case data."""
        depo = data.get("deposition_details", {})
        if depo.get("cause_number"):
            self._cause_var.set(depo["cause_number"])
        witness = depo.get("witness", "")
        if witness:
            parts = witness.strip().split()
            if parts:
                self._firstname_var.set(parts[0])
                self._lastname_var.set(parts[-1])
        if depo.get("date"):
            self._date_var.set(depo["date"])

    # ── Actions ──────────────────────────────────────────────────────────────

    def _browse_file(self):
        path = filedialog.askopenfilename(filetypes=_AUDIO_VIDEO_EXTENSIONS)
        if path:
            self._reset_case_state()
            self._selected_file = path
            self._set_entry_text(self._file_entry, path)
            self._apply_filename_extraction(path)
            self.after(300, self._auto_detect_source_docs)

    def _apply_filename_extraction(self, filepath: str):
        """Parse the audio filename for date and witness name."""
        from core.pdf_extractor import extract_from_filename

        results = extract_from_filename(filepath)

        _BADGE = {
            "filename": ("\U0001f7e9 Filename", "#44AA66"),
            "failed":   ("\u26a0\ufe0f Manual", "#888888"),
        }

        # Date
        date_val, date_src = results.get("date", (None, "failed"))
        if date_val:
            self._date_var.set(date_val)
            txt, col = _BADGE.get(date_src, _BADGE["failed"])
            self._date_badge.configure(text=txt, text_color=col)

        # Witness Last Name
        witness_val, witness_src = results.get("witness_last", (None, "failed"))
        if witness_val:
            self._lastname_var.set(witness_val)
            txt, col = _BADGE.get(witness_src, _BADGE["failed"])
            self._witness_badge.configure(text=txt, text_color=col)

        witness_first, _ = results.get("witness_first", (None, "failed"))
        if witness_first:
            self._firstname_var.set(witness_first)

        # Cause number is never in filename — prompt PDF upload if empty
        if not self._cause_var.get().strip():
            self._extract_status_label.configure(
                text="Cause number not in filename \u2014 upload a PDF notice or enter manually.",
                text_color="#CCAA44",
            )
            self._cause_badge.configure(text="\u26a0\ufe0f Manual", text_color="#888888")
        else:
            self._extract_status_label.configure(text="")

    def _browse_base_dir(self):
        path = filedialog.askdirectory(initialdir=self._base_dir_var.get())
        if path:
            self._base_dir_var.set(path)

    def _create_case_folders_now(self):
        """Ensure the current case folder structure exists before writing outputs."""
        from core.file_manager import resolve_or_create_case

        if not self._current_case_path:
            return

        _, status = resolve_or_create_case(
            self._base_dir_var.get().strip(),
            self._cause_var.get().strip(),
            self._lastname_var.get().strip(),
            self._firstname_var.get().strip(),
            self._date_var.get().strip(),
        )
        if status["errors"]:
            logger.error("Folder creation errors: %s", status["errors"])
        if status["created"]:
            logger.info("Folders created: %s", status["created"])

    def _open_output_folder(self):
        folder = self._last_output_dir
        if folder and os.path.isdir(folder):
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])

    def _open_transcript(self):
        if self._last_transcript_path and os.path.isfile(self._last_transcript_path):
            app = self.winfo_toplevel()
            app.transcript_tab.load_transcript(self._last_transcript_path)
            app.tab_view.set("Transcript")

    def _handle_pdf_upload(self, pdf_path: str | None = None, auto_detected: bool = False):
        """Load one PDF and extract both case fields and keyterms."""
        filepath = pdf_path or filedialog.askopenfilename(
            title="Select Deposition PDF",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")],
        )
        if not filepath:
            return

        self._last_pdf_path = filepath
        self._pdf_already_loaded = True
        self._upload_pdf_btn.configure(state="disabled", text="Processing\u2026")
        self._extract_status_label.configure(text="Extracting case info and keyterms\u2026", text_color="white")

        def _run():
            from core.pdf_extractor import extract_case_info_from_pdf

            results = extract_case_info_from_pdf(
                filepath,
                progress_callback=lambda msg: self.after(0, self._append_log, msg),
            )
            self.after(0, self._apply_pdf_results, results, auto_detected)

        threading.Thread(target=_run, daemon=True).start()

    def _apply_pdf_results(self, results: dict, auto_detected: bool = False):
        """Populate fields and keyterms from one PDF extraction result."""
        self._upload_pdf_btn.configure(
            state="normal",
            text="PDF Auto-Detected" if auto_detected else "+ Upload PDF",
            fg_color="#2A6F3A" if auto_detected else _DEFAULT_BUTTON_COLOR,
        )

        _BADGE = {
            "filename": ("\U0001f7e9 Filename", "#44AA66"),
            "regex":    ("\U0001f7e6 Regex", "#4488CC"),
            "ai":       ("\U0001f7e3 AI", "#9966CC"),
            "failed":   ("\u26a0\ufe0f Manual", "#888888"),
        }

        scanned = results.get("scanned", False)
        if scanned:
            self._extract_status_label.configure(
                text="This appears to be a scanned PDF. Please enter fields manually.",
                text_color="#CCAA44",
            )
            for badge in (self._cause_badge, self._witness_badge, self._date_badge):
                txt, col = _BADGE["failed"]
                badge.configure(text=txt, text_color=col)
            return

        # Cause Number
        cause_val, cause_src = results.get("cause_number", (None, "failed"))
        if cause_val and not self._cause_var.get().strip():
            self._cause_var.set(cause_val)
        txt, col = _BADGE.get(cause_src, _BADGE["failed"])
        self._cause_badge.configure(text=txt, text_color=col)

        # Witness Last Name
        witness_val, witness_src = results.get("witness_last", (None, "failed"))
        if witness_val and not self._lastname_var.get().strip():
            self._lastname_var.set(witness_val)
        txt, col = _BADGE.get(witness_src, _BADGE["failed"])
        self._witness_badge.configure(text=txt, text_color=col)

        # Date
        date_val, date_src = results.get("date", (None, "failed"))
        if date_val and self._date_var.get().strip() == datetime.now().strftime("%m/%d/%Y"):
            self._date_var.set(date_val)
        txt, col = _BADGE.get(date_src, _BADGE["failed"])
        self._date_badge.configure(text=txt, text_color=col)

        raw_keyterms = results.get("keyterms", [])
        reporter_terms: list[str] = []
        if self._reporter_notes_text:
            reporter_terms = extract_keyterms_from_text(self._reporter_notes_text)

        final_keyterms, _, reporter_fill = merge_keyterms(
            pdf_terms=raw_keyterms,
            reporter_terms=reporter_terms,
            limit=MAX_KEYTERMS,
        )
        self._current_keyterms = final_keyterms or None
        self._keyterms_box.configure(state="normal")
        self._keyterms_box.delete("1.0", "end")
        if final_keyterms:
            self._keyterms_box.insert("1.0", "\n".join(final_keyterms))
        self._keyterms_box.configure(state="disabled")
        self._update_keyterms_count()

        if final_keyterms:
            self._extract_status_label.configure(
                text=(
                    f"Keyterms ready: {len(final_keyterms)}/{MAX_KEYTERMS} "
                    f"({min(len(raw_keyterms), MAX_KEYTERMS)} from PDF"
                    + (f", {len(reporter_fill)} from reporter notes" if reporter_fill else "")
                    + ")"
                ),
                text_color="#44FF44" if len(final_keyterms) >= 10 else "#CCAA44",
            )
            self._append_log(
                f"Prepared {len(final_keyterms)} keyterms from PDF"
                + (f" + {len(reporter_fill)} reporter-note terms" if reporter_fill else "")
            )

        sources = [cause_src, witness_src, date_src]
        filled = sum(1 for s in sources if s != "failed")
        if not final_keyterms:
            self._extract_status_label.configure(
                text=f"Extracted {filled}/3 fields from PDF.",
                text_color="#44FF44" if filled == 3 else "#CCAA44",
            )

    def _open_review_dialog(self):
        self._auto_detect_source_docs()
        IntakeReviewDialog(self, self._extracted_case_data)

    def _load_reporter_notes(self, filepath: str, auto_detected: bool = False):
        with open(filepath, "r", encoding="utf-8") as handle:
            self._reporter_notes_text = handle.read()

        btn_text = "Notes Auto-Detected" if auto_detected else "Notes Loaded"
        self._upload_reporter_notes_btn.configure(
            text=btn_text,
            fg_color="#2A6F3A",
        )
        self._update_keyterms_count()
        self._extract_status_label.configure(
            text=(
                f"Reporter notes auto-detected: {os.path.basename(filepath)}"
                if auto_detected else
                f"Reporter notes loaded: {os.path.basename(filepath)}"
            ),
            text_color="#44FF44",
        )
        self._append_log(
            f"{'Auto-detected' if auto_detected else 'Loaded'} reporter notes: {filepath}"
        )

    def _upload_reporter_notes(self):
        """Open file dialog to select court reporter notes text file."""
        filepath = filedialog.askopenfilename(
            title="Select Court Reporter Notes",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not filepath:
            return

        try:
            self._load_reporter_notes(filepath, auto_detected=False)
        except Exception as exc:
            self._reporter_notes_text = ""
            self._upload_reporter_notes_btn.configure(
                text="Load Failed",
                fg_color="#8B0000",
            )
            self._update_keyterms_count()
            messagebox.showerror("Reporter Notes Error", str(exc))

    # ── Transcription Flow ───────────────────────────────────────────────────

    def _on_start(self):
        # Validate file
        if not self._selected_file or not os.path.isfile(self._selected_file):
            messagebox.showerror("No file selected", "Please select an audio or video file first.")
            return

        self._auto_detect_source_docs()

        # Validate API key
        from config import DEEPGRAM_API_KEY

        if not DEEPGRAM_API_KEY or not DEEPGRAM_API_KEY.strip():
            messagebox.showerror(
                "API Key Missing",
                "DEEPGRAM_API_KEY is not set.\nAdd it to your .env file and restart.",
            )
            return

        # Build final keyterms from primary textbox terms plus optional reporter notes.
        raw_kt = self._keyterms_box.get("1.0", "end").strip()
        raw_pdf_keyterms = [line.strip() for line in raw_kt.splitlines() if line.strip()]

        raw_reporter_keyterms: list[str] = []
        if self._reporter_notes_text.strip():
            raw_reporter_keyterms = extract_keyterms_from_text(self._reporter_notes_text)
            self._append_log(
                f"Extracted {len(raw_reporter_keyterms)} raw reporter-note keyterms"
            )

        final_keyterms, clean_primary, reporter_fill = merge_keyterms(
            pdf_terms=raw_pdf_keyterms,
            reporter_terms=raw_reporter_keyterms,
            limit=MAX_KEYTERMS,
        )
        self._current_keyterms = final_keyterms or None

        self._append_log(
            f"Keyterms ready: {len(final_keyterms)}/{MAX_KEYTERMS} "
            f"({min(len(clean_primary), MAX_KEYTERMS)} primary, {len(reporter_fill)} reporter)"
        )
        self._extract_status_label.configure(
            text=(
                f"Keyterms ready: {len(final_keyterms)}/{MAX_KEYTERMS} "
                f"{min(len(clean_primary), MAX_KEYTERMS)} from PDF/manual"
                + (f", {len(reporter_fill)} from reporter notes" if raw_reporter_keyterms else "")
            ),
            text_color="#44FF44" if len(final_keyterms) >= 10 else "#CCAA44",
        )

        # Disable button
        self._running = True
        self._start_btn.configure(
            text="\u23f3 Transcribing\u2026", state="disabled"
        )
        self._open_folder_btn.configure(state="disabled")
        self._open_file_btn.configure(state="disabled")

        # Clear log and preview
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._preview_box.configure(state="normal")
        self._preview_box.delete("1.0", "end")
        self._preview_box.configure(state="disabled")
        self._progress_bar.set(0)
        self._status_label.configure(text="Starting\u2026", text_color="white")

        # Launch background thread
        thread = threading.Thread(target=self._run_job, daemon=True)
        thread.start()

    def _run_job(self):
        from core.job_runner import run_transcription_job

        self._create_case_folders_now()

        run_transcription_job(
            audio_path=self._selected_file,
            model=self._model_var.get(),
            quality=self._quality_var.get(),
            utt_split=float(self._utt_split_var.get()),
            base_dir=self._base_dir_var.get(),
            cause_number=self._cause_var.get(),
            last_name=self._lastname_var.get(),
            first_name=self._firstname_var.get(),
            date_str=self._date_var.get(),
            keyterms=self._current_keyterms,
            ufm_fields=self._ufm_fields or None,
            progress_callback=self._on_progress,
            log_callback=self._on_log,
            done_callback=self._on_done,
        )

    # ── Callbacks (called from background thread, dispatch via after()) ──────

    def _on_progress(self, percent: float, message: str):
        self.after(0, self._update_progress, percent, message)

    def _on_log(self, message: str):
        self.after(0, self._append_log, message)

    def _on_done(self, result: dict):
        self.after(0, self._finish, result)

    def _update_progress(self, percent: float, message: str):
        self._progress_bar.set(percent / 100.0)
        self._status_label.configure(text=message, text_color="white")

    def _finish(self, result: dict):
        self._running = False
        self._start_btn.configure(
            text="\u25b6  CREATE TRANSCRIPT", state="normal"
        )

        if result.get("success"):
            self._status_label.configure(
                text="Complete \u2713", text_color="#44FF44"
            )
            self._last_transcript_path = result.get("transcript_path")
            self._current_txt_path = result.get("transcript_path")
            self._transcript_text = result.get("transcript_text", "")
            self._last_output_dir = result.get("output_dir", "")
            self._open_folder_btn.configure(state="normal")
            self._open_file_btn.configure(state="normal")

            # Show preview (first 3000 chars)
            self._preview_box.configure(state="normal")
            self._preview_box.delete("1.0", "end")
            self._preview_box.insert("1.0", self._transcript_text[:3000])
            self._preview_box.configure(state="disabled")

            # Show speaker labels section
            self._show_speaker_section()

            if self._last_transcript_path and os.path.isfile(self._last_transcript_path):
                app = self.winfo_toplevel()
                app.transcript_tab.load_transcript(self._last_transcript_path)
                app.tab_view.set("Transcript")

            # Enable review button if case data has been extracted
            if self._extracted_case_data:
                self._review_btn.configure(state="normal")
        else:
            error_msg = result.get("error", "Unknown error")
            self._status_label.configure(text="Failed", text_color="#FF4444")
            messagebox.showerror("Transcription Failed", error_msg)

    # ── Speaker Label Methods ────────────────────────────────────────────────

    def _show_speaker_section(self):
        """Scan transcript for speaker IDs, rebuild rows, and show the card."""
        # Clear previous rows and entries
        for widget in self._speaker_rows_frame.winfo_children():
            widget.destroy()
        self._speaker_entries.clear()

        # Find all unique speaker IDs in the transcript
        speakers = sorted(set(re.findall(r'Speaker (\d+):', self._transcript_text)))

        for sid in speakers:
            row = ctk.CTkFrame(self._speaker_rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row, text=f"Speaker {sid}:", width=100, anchor="w",
                font=ctk.CTkFont(weight="bold"),
            ).pack(side="left", padx=(0, 8))

            entry = ctk.CTkEntry(row, placeholder_text="e.g. THE REPORTER")
            entry.pack(side="left", fill="x", expand=True)
            self._speaker_entries[f"Speaker {sid}"] = entry

        self._speaker_card.pack(fill="x", pady=(0, 10))

    def _apply_and_save_labels(self):
        """Replace speaker labels in transcript, save to file, update preview."""
        if not self._current_txt_path:
            messagebox.showerror("No file", "No transcript file path available.")
            return

        text = self._transcript_text

        for original_label, entry in self._speaker_entries.items():
            replacement = entry.get().strip()
            if replacement:
                text = text.replace(f"{original_label}:", f"{replacement}:")

        # Write renamed transcript to file
        try:
            Path(self._current_txt_path).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Save Failed", str(exc))
            return

        # Update stored text and preview
        self._transcript_text = text
        self._preview_box.configure(state="normal")
        self._preview_box.delete("1.0", "end")
        self._preview_box.insert("1.0", text[:3000])
        self._preview_box.configure(state="disabled")

        self._status_label.configure(
            text="Saved \u2014 labels applied", text_color="#44FF44"
        )
        self._append_log(
            f"Saved renamed transcript: {os.path.basename(self._current_txt_path)}"
        )

    # ── Extraction callback (called externally when AI extraction finishes) ──

    def set_extracted_case_data(self, data: dict):
        """Store AI-extracted case data and enable the review button."""
        self._extracted_case_data = data
        self._review_btn.configure(state="normal")
        self._populate_case_fields(data)
