"""
ui/tab_templates.py

Templates tab — selects + populates UFM templates and applies the
post-processor format box.

Implements TEMPLATE_EXTRACTION_REPORT §11. Pure UI layer:
- Reads reporter profiles from data/reporter_profiles/
- Reads template metadata from ufm_engine/templates/manifest.json
- Reads case data (NOD-derived ufm_fields) from job_config.json
- Persists per-job selections to source_docs/template_selections.json
- Calls ufm_engine.populator.populate.populate to fill .docx
- Calls ufm_engine.post_processor.format_box.apply_format_box to finish

Does not modify pipeline/, clean_format/, or job_config.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from app_logging import get_logger
from ui._components import (
    BG_CARD,
    BTN_PRIMARY_AMBER,
    BTN_PRIMARY_AMBER_HOVER,
    BTN_SAFE_GREEN,
    BTN_SAFE_GREEN_HOVER,
    BTN_UTILITY_BLUE,
    BTN_UTILITY_BLUE_HOVER,
    CARD_BORDER_COLOR,
    TEXT_DIM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    make_section_header,
)

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = PROJECT_ROOT / "data" / "reporter_profiles"
MANIFEST_PATH = PROJECT_ROOT / "ufm_engine" / "templates" / "manifest.json"
TEMPLATES_FIGURES = PROJECT_ROOT / "ufm_engine" / "templates" / "figures"


def _is_field_present(value) -> bool:
    """A field is 'present' if it is not None and not empty after str/strip."""
    if value is None:
        return False
    return bool(str(value).strip())


SELECTIONS_VERSION = 1

GROUP_LABELS = {
    "title": "Title pages",
    "appearances": "Appearances",
    "index": "Index",
    "witness_setup": "Witness setup",
    "signature": "Changes / Notary",
    "certification": "Reporter's Certification",
}

# Manual fields users will commonly need to fill that aren't in the NOD.
# Order matters — rendered in this order.
MANUAL_FIELDS = [
    ("custodial_attorney_name", "Custodial Attorney"),
    ("cost_amount", "Cost Amount ($)"),
    ("cost_payor_party", "Cost Payor Party"),
    ("transcript_submitted_date", "Transcript Submitted Date"),
    ("transcript_returned_date", "Transcript Return-By Date"),
    ("served_on_date", "Served-On Date"),
    ("certification_date", "Certification Date"),
    ("instance_party", "Witness At Instance Of"),
]


class TemplatesTab(ctk.CTkFrame):
    """Templates tab — see module docstring."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._case_folder: Optional[Path] = None
        self._manifest = self._load_manifest()
        self._profiles = self._load_profiles()
        self._job_config: dict = {}

        # state vars created lazily during _build_*
        self._template_checkboxes: dict[str, ctk.CTkCheckBox] = {}
        self._template_vars: dict[str, ctk.BooleanVar] = {}
        self._block_toggle_vars: dict[str, ctk.BooleanVar] = {}
        self._block_toggle_widgets: dict[str, ctk.CTkCheckBox] = {}
        self._manual_field_entries: dict[str, ctk.CTkEntry] = {}

        self._reporter_var = ctk.StringVar()
        self._apply_format_box_var = ctk.BooleanVar(value=True)
        self._apply_line_numbers_var = ctk.BooleanVar(value=True)
        self._render_firm_footer_var = ctk.BooleanVar(value=True)

        self._build_layout()

        if self._profiles:
            first = next(iter(self._profiles.values()))
            self._reporter_var.set(first["display_name"])
            self._on_reporter_changed()

    # ── Loading helpers ──────────────────────────────────────────────────────

    def _load_manifest(self) -> dict:
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("[Templates] failed to load manifest: %s", e)
            return {"version": 0, "templates": []}

    def _load_profiles(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not PROFILES_DIR.is_dir():
            return out
        for f in sorted(PROFILES_DIR.glob("*.json")):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
                out[p["display_name"]] = p
            except Exception as e:
                logger.error("[Templates] failed to load profile %s: %s", f, e)
        return out

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_layout(self):
        # Single scrollable column. Right-side action panel stays anchored.
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=8)

        self._build_case_folder_bar(main)
        self._build_reporter_section(main)
        self._build_template_section(main)
        self._build_block_toggles_section(main)
        self._build_manual_fields_section(main)
        self._build_finishing_section(main)
        self._build_actions_section(main)
        self._build_status_section(main)

    def _build_case_folder_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=BG_CARD,
                           border_color=CARD_BORDER_COLOR, border_width=1,
                           corner_radius=10)
        bar.pack(fill="x", pady=(0, 12))

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(inner, text="Case folder:", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        self._case_folder_label = ctk.CTkLabel(
            inner, text="(none — pick a case folder)",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11),
            anchor="w", justify="left",
        )
        self._case_folder_label.pack(side="left", padx=(8, 8), fill="x", expand=True)

        ctk.CTkButton(
            inner, text="Browse…",
            width=100, height=28,
            fg_color=BTN_UTILITY_BLUE, hover_color=BTN_UTILITY_BLUE_HOVER,
            command=self._on_browse_case_folder,
        ).pack(side="right")

    def _build_reporter_section(self, parent):
        make_section_header(parent, "Reporter").pack(fill="x", pady=(0, 4))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))

        names = list(self._profiles.keys())
        if not names:
            names = ["(no profiles found)"]
        self._reporter_dropdown = ctk.CTkOptionMenu(
            row, values=names, variable=self._reporter_var,
            command=lambda _v: self._on_reporter_changed(),
            width=360,
        )
        self._reporter_dropdown.pack(side="left")

        self._reporter_summary = ctk.CTkLabel(
            parent, text="", font=ctk.CTkFont(family="Courier New", size=10),
            text_color=TEXT_SECONDARY, anchor="w", justify="left",
        )
        self._reporter_summary.pack(fill="x", pady=(0, 12))

    def _build_template_section(self, parent):
        make_section_header(parent, "Templates").pack(fill="x", pady=(0, 4))

        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 4))

        ctk.CTkButton(
            controls, text="Select required",
            width=130, height=26,
            fg_color=BTN_UTILITY_BLUE, hover_color=BTN_UTILITY_BLUE_HOVER,
            command=self._select_required_templates,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            controls, text="Clear",
            width=80, height=26,
            fg_color="transparent", border_width=1,
            border_color=CARD_BORDER_COLOR, text_color=TEXT_SECONDARY,
            hover_color=CARD_BORDER_COLOR,
            command=self._clear_template_selections,
        ).pack(side="left")

        body = ctk.CTkFrame(
            parent, fg_color=BG_CARD,
            border_color=CARD_BORDER_COLOR, border_width=1,
            corner_radius=10,
        )
        body.pack(fill="x", pady=(0, 12))

        # Group templates by category
        by_group: dict[str, list[dict]] = {}
        for t in self._manifest.get("templates", []):
            by_group.setdefault(t["category"], []).append(t)

        for group_id, label in GROUP_LABELS.items():
            items = by_group.get(group_id)
            if not items:
                continue
            ctk.CTkLabel(
                body, text=label,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=TEXT_PRIMARY, anchor="w",
            ).pack(fill="x", padx=12, pady=(8, 2))
            for t in items:
                var = ctk.BooleanVar(value=bool(t.get("default_selected", False)))
                self._template_vars[t["id"]] = var
                cb = ctk.CTkCheckBox(
                    body,
                    text=t["display_name"],
                    variable=var,
                    command=self._on_template_toggle_changed,
                    text_color=TEXT_SECONDARY,
                    font=ctk.CTkFont(size=11),
                )
                cb.pack(fill="x", padx=24, pady=1, anchor="w")
                self._template_checkboxes[t["id"]] = cb

    def _build_block_toggles_section(self, parent):
        make_section_header(parent, "Conditional Blocks").pack(fill="x", pady=(0, 4))

        self._blocks_body = ctk.CTkFrame(
            parent, fg_color=BG_CARD,
            border_color=CARD_BORDER_COLOR, border_width=1,
            corner_radius=10,
        )
        self._blocks_body.pack(fill="x", pady=(0, 12))

        self._blocks_empty_label = ctk.CTkLabel(
            self._blocks_body,
            text="(no toggleable blocks for selected templates)",
            text_color=TEXT_DIM, font=ctk.CTkFont(size=10, slant="italic"),
        )
        self._blocks_empty_label.pack(padx=12, pady=10, anchor="w")

        self._refresh_block_toggles()

    def _build_manual_fields_section(self, parent):
        make_section_header(parent, "Manual Fields").pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            parent,
            text="Fields not derived from the NOD. Leave blank to use the placeholder.",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=10),
            anchor="w", justify="left",
        ).pack(fill="x", pady=(0, 4))

        body = ctk.CTkFrame(
            parent, fg_color=BG_CARD,
            border_color=CARD_BORDER_COLOR, border_width=1,
            corner_radius=10,
        )
        body.pack(fill="x", pady=(0, 12))

        for tag, label in MANUAL_FIELDS:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=label, width=200, anchor="w",
                         text_color=TEXT_SECONDARY,
                         font=ctk.CTkFont(size=11)).pack(side="left")
            entry = ctk.CTkEntry(row, width=320, height=24,
                                  font=ctk.CTkFont(family="Courier New", size=11))
            entry.pack(side="left", fill="x", expand=True)
            self._manual_field_entries[tag] = entry

    def _build_finishing_section(self, parent):
        make_section_header(parent, "Finishing Options").pack(fill="x", pady=(0, 4))

        body = ctk.CTkFrame(
            parent, fg_color=BG_CARD,
            border_color=CARD_BORDER_COLOR, border_width=1,
            corner_radius=10,
        )
        body.pack(fill="x", pady=(0, 12))

        ctk.CTkCheckBox(
            body, text="Apply UFM format box (Pipeline B)",
            variable=self._apply_format_box_var,
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(8, 2), anchor="w")

        ctk.CTkCheckBox(
            body, text="Apply line numbers in gutter",
            variable=self._apply_line_numbers_var,
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=2, anchor="w")

        ctk.CTkCheckBox(
            body, text="Render firm-name footer",
            variable=self._render_firm_footer_var,
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(2, 8), anchor="w")

    def _build_actions_section(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(4, 6))

        ctk.CTkButton(
            row, text="Generate populated documents",
            width=240, height=36,
            fg_color=BTN_PRIMARY_AMBER, hover_color=BTN_PRIMARY_AMBER_HOVER,
            command=self._on_generate,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row, text="Apply UFM Format Box",
            width=200, height=36,
            fg_color=BTN_SAFE_GREEN, hover_color=BTN_SAFE_GREEN_HOVER,
            command=self._on_apply_format_box,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row, text="Open output folder",
            width=160, height=36,
            fg_color=BTN_UTILITY_BLUE, hover_color=BTN_UTILITY_BLUE_HOVER,
            command=self._on_open_output_folder,
        ).pack(side="left")

    def _build_status_section(self, parent):
        self._status_label = ctk.CTkLabel(
            parent, text="",
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11),
            anchor="w", justify="left", wraplength=900,
        )
        self._status_label.pack(fill="x", pady=(4, 8))

    # ── Reporter helpers ─────────────────────────────────────────────────────

    def _active_profile(self) -> Optional[dict]:
        return self._profiles.get(self._reporter_var.get())

    def _on_reporter_changed(self):
        p = self._active_profile()
        if p is None:
            self._reporter_summary.configure(text="(no profile)")
            return
        lines = [
            f"  Reporter: {p.get('reporter_name', '')}",
            f"  CSR: {p.get('csr_number', '')} (exp {p.get('csr_expiration', '')})",
            f"  Credentials: {p.get('credentials') or '—'}",
            f"  Firm: {p.get('firm_name') or '—'}"
            + (f" (Reg {p['firm_registration_number']})"
               if p.get("firm_registration_number") else ""),
            f"  Address: {p.get('address_line1', '')}, "
                f"{p.get('city', '')}, {p.get('state', '')} {p.get('zip', '')}",
            f"  Phone: {p.get('phone') or '—'}",
            f"  Email: {p.get('email') or '—'}",
        ]
        self._reporter_summary.configure(text="\n".join(lines))

    # ── Template selection helpers ───────────────────────────────────────────

    def _on_template_toggle_changed(self):
        self._refresh_block_toggles()

    def _select_required_templates(self):
        for t in self._manifest.get("templates", []):
            self._template_vars[t["id"]].set(bool(t.get("default_selected", False)))
        self._refresh_block_toggles()

    def _clear_template_selections(self):
        for v in self._template_vars.values():
            v.set(False)
        self._refresh_block_toggles()

    def _selected_template_ids(self) -> list[str]:
        return [tid for tid, v in self._template_vars.items() if v.get()]

    def _refresh_block_toggles(self):
        # Clear old widgets but keep the variable map (so user state persists).
        for w in list(self._blocks_body.winfo_children()):
            w.destroy()
        self._block_toggle_widgets.clear()

        block_ids: list[tuple[str, str]] = []  # (block_tag, defining_template)
        seen: set[str] = set()
        for t in self._manifest.get("templates", []):
            if not self._template_vars.get(t["id"], ctk.BooleanVar(value=False)).get():
                continue
            for b in t.get("conditional_blocks", []):
                if b in seen:
                    continue
                seen.add(b)
                block_ids.append((b, t["display_name"]))

        if not block_ids:
            ctk.CTkLabel(
                self._blocks_body,
                text="(no toggleable blocks for selected templates)",
                text_color=TEXT_DIM,
                font=ctk.CTkFont(size=10, slant="italic"),
            ).pack(padx=12, pady=10, anchor="w")
            return

        for tag, defining in block_ids:
            var = self._block_toggle_vars.get(tag)
            if var is None:
                # Default sourced from manifest. A block tag absent from the
                # defining template's default_blocks map defaults to True
                # (block kept and unwrapped). Policy lives in the manifest;
                # the UI only consumes it.
                default_on = self._manifest_block_default(tag)
                var = ctk.BooleanVar(value=default_on)
                self._block_toggle_vars[tag] = var
            cb = ctk.CTkCheckBox(
                self._blocks_body,
                text=f"{tag}    [{defining}]",
                variable=var,
                text_color=TEXT_SECONDARY,
                font=ctk.CTkFont(family="Courier New", size=10),
            )
            cb.pack(fill="x", padx=12, pady=1, anchor="w")
            self._block_toggle_widgets[tag] = cb

    def _manifest_block_default(self, block_tag: str) -> bool:
        """Resolve the default state of a conditional block.

        A block tag may appear in more than one template's
        conditional_blocks list. We resolve to the first selected template
        that defines a default for the tag; if no selected template
        explicitly declares a default, the tag defaults to True.
        """
        for t in self._manifest.get("templates", []):
            if not self._template_vars.get(t["id"], ctk.BooleanVar(value=False)).get():
                continue
            defaults = t.get("default_blocks") or {}
            if block_tag in defaults:
                return bool(defaults[block_tag])
        return True

    # ── Case folder ──────────────────────────────────────────────────────────

    def _on_browse_case_folder(self):
        path = filedialog.askdirectory(title="Pick the case folder")
        if not path:
            return
        self._set_case_folder(Path(path))

    def _set_case_folder(self, path: Path):
        self._case_folder = path
        self._case_folder_label.configure(
            text=str(path), text_color=TEXT_PRIMARY,
        )
        self._load_job_config_for_case()
        self._load_template_selections_for_case()

    def _load_job_config_for_case(self):
        self._job_config = {}
        if self._case_folder is None:
            return
        # Use the project's canonical loader so we follow the same path conventions.
        try:
            from core.job_config_manager import load_job_config
            self._job_config = load_job_config(str(self._case_folder)) or {}
            ufm = self._job_config.get("ufm_fields") or {}
            self._set_status(
                f"Loaded job_config.json — {len(ufm)} ufm_fields available."
                if ufm else "Loaded job_config.json (no ufm_fields yet).",
            )
        except Exception as e:
            logger.error("[Templates] load_job_config failed: %s", e)
            self._set_status(f"Could not read job_config.json: {e}", error=True)

    # ── Selections persistence ───────────────────────────────────────────────

    def _selections_path(self) -> Optional[Path]:
        if self._case_folder is None:
            return None
        return self._case_folder / "source_docs" / "template_selections.json"

    def _load_template_selections_for_case(self):
        path = self._selections_path()
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[Templates] could not read %s: %s", path, e)
            return

        prof_id = data.get("reporter_profile_id")
        for display_name, p in self._profiles.items():
            if p.get("id") == prof_id:
                self._reporter_var.set(display_name)
                self._on_reporter_changed()
                break

        selected = set(data.get("selected_templates", []))
        for tid, var in self._template_vars.items():
            var.set(tid in selected)

        for tag, val in (data.get("block_toggles") or {}).items():
            if tag not in self._block_toggle_vars:
                self._block_toggle_vars[tag] = ctk.BooleanVar(value=bool(val))
            else:
                self._block_toggle_vars[tag].set(bool(val))

        finishing = data.get("finishing_options") or {}
        self._apply_format_box_var.set(bool(finishing.get("apply_format_box", True)))
        self._apply_line_numbers_var.set(bool(finishing.get("apply_line_numbers", True)))
        self._render_firm_footer_var.set(bool(finishing.get("render_firm_footer", True)))

        for tag, val in (data.get("manual_fields") or {}).items():
            entry = self._manual_field_entries.get(tag)
            if entry is not None and val is not None:
                entry.delete(0, "end")
                entry.insert(0, str(val))

        self._refresh_block_toggles()

    def _save_template_selections(self):
        path = self._selections_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        prof = self._active_profile()
        data = {
            "version": SELECTIONS_VERSION,
            "reporter_profile_id": prof["id"] if prof else None,
            "selected_templates": self._selected_template_ids(),
            "block_toggles": {k: v.get() for k, v in self._block_toggle_vars.items()},
            "manual_fields": {k: e.get().strip() for k, e in self._manual_field_entries.items() if e.get().strip()},
            "finishing_options": {
                "apply_format_box": self._apply_format_box_var.get(),
                "apply_line_numbers": self._apply_line_numbers_var.get(),
                "render_firm_footer": self._render_firm_footer_var.get(),
            },
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Field resolution ─────────────────────────────────────────────────────

    def _resolved_fields(self) -> dict:
        """Merge ufm_fields + reporter_profile + manual fields. Manual wins over NOD;
        reporter wins over NOD on collision (case state vs reporter state). NOD wins
        over reporter only for fields the NOD owns. We accept that case-vs-reporter
        `state` collides — most templates use the case state. The reporter signature
        block re-uses the same `state` field so a TX case + TX reporter coincide.
        """
        merged: dict = {}
        merged.update(self._job_config.get("ufm_fields") or {})
        prof = self._active_profile()
        if prof:
            for k, v in prof.items():
                if k in {"id", "display_name", "chassis_default"}:
                    continue
                if v is not None:
                    merged[k] = v
        for tag, entry in self._manual_field_entries.items():
            val = entry.get().strip()
            if val:
                merged[tag] = val
        return merged

    def _validate_required_fields(
        self, selected: list[str], fields: dict
    ) -> dict[str, list[str]]:
        """Return {template_id: [missing_tag, ...]} for any selected template
        whose declared required_fields are absent or empty in `fields`.

        Templates without a `required_fields` entry in the manifest are
        treated as having no requirements and never appear in the result.
        """
        manifest_by_id = {
            t["id"]: t for t in self._manifest.get("templates", [])
        }
        result: dict[str, list[str]] = {}
        for tid in selected:
            entry = manifest_by_id.get(tid)
            if not entry:
                continue
            required = entry.get("required_fields") or []
            missing = [
                tag for tag in required
                if not _is_field_present(fields.get(tag))
            ]
            if missing:
                result[tid] = missing
        return result

    # ── Generate / Apply / Open ──────────────────────────────────────────────

    def _output_dir(self, sub: str) -> Optional[Path]:
        if self._case_folder is None:
            return None
        d = self._case_folder / "output" / sub
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _on_generate(self):
        if self._case_folder is None:
            self._set_status("Pick a case folder first.", error=True)
            return
        selected = self._selected_template_ids()
        if not selected:
            self._set_status("No templates selected.", error=True)
            return

        self._save_template_selections()
        fields = self._resolved_fields()
        toggles = {k: v.get() for k, v in self._block_toggle_vars.items()}

        missing = self._validate_required_fields(selected, fields)
        if missing:
            lines = [f"  • {tid}: {', '.join(tags)}" for tid, tags in missing.items()]
            self._set_status(
                f"{len(missing)} template(s) have missing required fields:\n"
                + "\n".join(lines)
                + "\nFill the fields or remove the template, then retry.",
                error=True,
            )
            return

        draft_dir = self._output_dir("draft")
        self._set_status(f"Generating {len(selected)} template(s)…")
        thread = threading.Thread(
            target=self._run_generate,
            args=(selected, fields, toggles, draft_dir),
            daemon=True,
        )
        thread.start()

    def _run_generate(self, selected, fields, toggles, draft_dir: Path):
        from ufm_engine.populator.populate import populate
        results = []
        for tid in selected:
            template = TEMPLATES_FIGURES / f"{tid}.docx"
            out = draft_dir / f"{tid}.docx"
            try:
                populate(template, out, fields=fields, block_toggles=toggles)
                results.append((tid, True, None))
            except Exception as e:
                logger.exception("populate %s failed", tid)
                results.append((tid, False, str(e)))
        ok = sum(1 for _, success, _ in results if success)
        msg = f"Generated {ok}/{len(results)} into {draft_dir}"
        errors = [f"{tid}: {err}" for tid, success, err in results if not success]
        if errors:
            msg += "\nErrors:\n  " + "\n  ".join(errors)
        self.after(0, lambda: self._set_status(msg, error=bool(errors)))

    def _on_apply_format_box(self):
        if self._case_folder is None:
            self._set_status("Pick a case folder first.", error=True)
            return
        draft_dir = self._output_dir("draft")
        if draft_dir is None or not any(draft_dir.glob("*.docx")):
            self._set_status("No populated documents to finish — run Generate first.",
                              error=True)
            return
        if not self._apply_format_box_var.get():
            self._set_status("Apply UFM format box is unchecked — nothing to do.",
                              error=True)
            return

        final_dir = self._output_dir("final")
        prof = self._active_profile()
        firm_name = prof.get("firm_name") if prof else None
        render_footer = self._render_firm_footer_var.get() and bool(firm_name)
        apply_line_numbers = self._apply_line_numbers_var.get()

        self._set_status("Applying UFM format box…")
        thread = threading.Thread(
            target=self._run_apply_format_box,
            args=(draft_dir, final_dir, apply_line_numbers, render_footer, firm_name),
            daemon=True,
        )
        thread.start()

    def _run_apply_format_box(self, draft_dir: Path, final_dir: Path,
                              apply_line_numbers: bool, render_footer: bool,
                              firm_name: Optional[str]):
        from ufm_engine.post_processor.format_box import apply_format_box
        results = []
        for src in sorted(draft_dir.glob("*.docx")):
            dest = final_dir / src.name
            try:
                apply_format_box(
                    input_path=src, output_path=dest,
                    apply_line_numbers=apply_line_numbers,
                    render_firm_footer=render_footer,
                    firm_name=firm_name,
                )
                results.append((src.name, True, None))
            except Exception as e:
                logger.exception("apply_format_box %s failed", src.name)
                results.append((src.name, False, str(e)))
        ok = sum(1 for _, success, _ in results if success)
        msg = f"Finished {ok}/{len(results)} into {final_dir}"
        errors = [f"{name}: {err}" for name, success, err in results if not success]
        if errors:
            msg += "\nErrors:\n  " + "\n  ".join(errors)
        self.after(0, lambda: self._set_status(msg, error=bool(errors)))

    def _on_open_output_folder(self):
        if self._case_folder is None:
            self._set_status("Pick a case folder first.", error=True)
            return
        target = self._case_folder / "output"
        target.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(target))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as e:
            self._set_status(f"Could not open folder: {e}", error=True)

    # ── Status ───────────────────────────────────────────────────────────────

    def _set_status(self, text: str, *, error: bool = False):
        color = "#FF6B6B" if error else TEXT_SECONDARY
        self._status_label.configure(text=text, text_color=color)

    # ── Public API for the Transcribe tab to push a case folder over ─────────

    def set_case_folder(self, path: str):
        """Allow the Transcribe tab (or external code) to push the active case."""
        self._set_case_folder(Path(path))
