"""
core/field_mapping.py

Canonical mapping between ufm_fields keys (as written to job_config.json)
and the normalized field names used by surviving runtime code.

WHY THIS FILE EXISTS
--------------------
Several ufm_fields keys do not share the same name as their corresponding
JobConfig attribute.  Without a single reference, those mismatches are
invisible and easy to break silently during refactoring.

This file makes every mismatch explicit and intentional.

HOW IT IS USED
--------------
Legacy correction-path builders iterated UFM_TO_CFG_SCALAR to assign
all scalar (string) fields in one loop.

WHAT IS NOT IN THIS FILE
-------------------------
Fields that require type coercion (list wrapping, bool conversion,
CounselInfo construction, int key conversion) cannot be expressed as a
simple string → string mapping.  Those are handled with explicit code in
that legacy builder with comments that
reference this file.

Complex fields (handled explicitly by higher-level assembly code):
  "defendant_name"      → cfg.defendant_names       (str  → list[str])
  "video_required"      → cfg.is_videotaped          (str  → bool)
  "plaintiff_counsel"   → cfg.plaintiff_counsel      (list → list[CounselInfo])
  "defense_counsel"     → cfg.defense_counsel        (list → list[CounselInfo])
  "confirmed_spellings" → cfg.confirmed_spellings    (top-level key, not ufm_fields)
  "speaker_map"         → cfg.speaker_map            (str keys → int keys)
"""

# ── Scalar field mapping ──────────────────────────────────────────────────────
# Key   = exact string key inside job_config.json["ufm_fields"]
# Value = normalized target field name
#
# All mismatches are marked with "# key mismatch" so they are easy to audit.

UFM_TO_CFG_SCALAR: dict[str, str] = {
    # Case identifiers
    "cause_number":      "cause_number",
    "case_style":        "case_style",
    "plaintiff_name":    "plaintiff_name",

    # Court
    "court_type":        "court_type",
    "county":            "county",
    "state":             "state",
    "judicial_district": "judicial_district",

    # Deposition logistics
    "depo_date":         "depo_date",
    "depo_time_start":   "depo_start_time",     # key mismatch — intentional
    "depo_location":     "location",            # key mismatch — intentional
    "depo_method":       "method",              # key mismatch — intentional

    # Witness
    "witness_name":      "witness_name",

    # Reporter
    "reporter_name":     "reporter_name",
    "csr_number":        "reporter_csr",        # key mismatch — intentional
    "reporter_agency":   "reporter_firm",       # key mismatch — intentional
}
