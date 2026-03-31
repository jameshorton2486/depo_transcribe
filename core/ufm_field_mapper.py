"""
core/ufm_field_mapper.py

Canonical mapping between extracted intake data and UFM document fields.
Converts AI-extracted case intake JSON into the flat field dict used by
the UFM page generators in spec_engine/pages/.
"""

import re
from datetime import datetime


def map_intake_to_ufm(extracted: dict) -> dict:
    """
    Convert extracted intake JSON into a flat UFM field dict
    that matches the JobConfig and UFM page generator field names.

    Input shape (from UI's _extracted_case_data):
      extracted["deposition_details"]  — cause_number, witness, date,
                                         court, case_style, method,
                                         county, state, location,
                                         scheduled_time
      extracted["ordering_attorney"]   — name, firm, address, phone,
                                         email, city_state_zip
      extracted["copy_attorneys"]      — list of attorney dicts
      extracted["all_attorneys"]       — list with role field (may be [])
      extracted["court_reporter"]      — name, csr_number, agency
      extracted["deponents"]           — list of {name, role} dicts

    Returns a dict ready to be passed to JobConfig or saved as
    a ufm_fields.json alongside the transcript.
    """
    depo       = extracted.get("deposition_details", {}) or {}
    ord_atty   = extracted.get("ordering_attorney", {}) or {}
    copy_attys = extracted.get("copy_attorneys", []) or []
    all_attys  = extracted.get("all_attorneys", []) or []
    reporter   = extracted.get("court_reporter", {}) or {}
    deponents  = extracted.get("deponents", []) or []
    video_recorded = bool(extracted.get("video_recorded", False))
    subpoena_dt    = bool(extracted.get("subpoena_duces_tecum", False))

    # Derive deposition type string for UFM title line
    # Fig. 3 line 10: "ORAL AND VIDEOTAPED DEPOSITION OF"
    if video_recorded:
        depo_type = "ORAL AND VIDEOTAPED"
    else:
        depo_type = "ORAL"

    # ── Witness name ─────────────────────────────────────────────
    # Prefer the explicit witness field; fall back to first deponent.
    witness_name = (
        depo.get("witness", "")
        or (deponents[0].get("name", "") if deponents else "")
    )

    # ── Parse date into components ────────────────────────────────
    date_str = depo.get("date", "")
    dt = None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            break
        except ValueError:
            continue

    # ── Parse plaintiff and defendant from case_style ─────────────
    case_style = depo.get("case_style", "")
    plaintiff  = ""
    defendant  = ""
    if " v. " in case_style:
        parts     = case_style.split(" v. ", 1)
        plaintiff = parts[0].strip()
        defendant = parts[1].strip()
    elif " vs. " in case_style.lower():
        idx = case_style.lower().index(" vs. ")
        plaintiff = case_style[:idx].strip()
        defendant = case_style[idx + 5:].strip()

    # ── Parse court into district number and county ───────────────
    court_raw   = depo.get("court", "")
    district_no = ""
    court_type  = "DISTRICT COURT"
    county      = depo.get("county", "")

    m = re.search(r'(\d+)', court_raw)
    if m:
        district_no = m.group(1) + "TH"

    # Extract county from the court string when not in its own field.
    # e.g. "370th Judicial District, Hidalgo County, Texas"
    if not county and court_raw:
        cm = re.search(r'([A-Za-z]+)\s+County', court_raw, re.IGNORECASE)
        if cm:
            county = cm.group(1).title() + " County"

    # ── Build counsel lists ───────────────────────────────────────
    plaintiff_counsel = []
    defense_counsel   = []

    # Primary path: all_attorneys list with role field
    for atty in all_attys:
        role = (atty.get("role", "") or "").lower()
        obj  = {
            "name":    atty.get("name", ""),
            "firm":    atty.get("firm", ""),
            "sbot":    atty.get("bar_no", "") or atty.get("bar_number", ""),
            "address": atty.get("address", ""),
            "phone":   atty.get("phone", ""),
            "email":   atty.get("email", ""),
            "party":   atty.get("party_represented", ""),
        }
        if "plaintiff" in role:
            plaintiff_counsel.append(obj)
        elif "defense" in role or "defendant" in role:
            defense_counsel.append(obj)

    # Fallback: ordering attorney → plaintiff counsel.
    # In Texas plaintiff depositions the ordering attorney
    # represents the defendant (who notices the deposition).
    # Use ordering attorney as defendant/examining counsel.
    if not plaintiff_counsel and ord_atty.get("name"):
        plaintiff_counsel.append({
            "name":    ord_atty.get("name", ""),
            "firm":    ord_atty.get("firm", ""),
            "sbot":    "",
            "address": " ".join(filter(None, [
                ord_atty.get("address", ""),
                ord_atty.get("city_state_zip", ""),
            ])).strip(),
            "phone":   ord_atty.get("phone", ""),
            "email":   ord_atty.get("email", ""),
            "party":   defendant or plaintiff,
        })

    # Fallback: every copy attorney → defense/opposing counsel.
    # Copy attorneys receive copies of the transcript and represent
    # the opposing party. Include all of them regardless of role field.
    if not defense_counsel:
        for ca in copy_attys:
            if not ca.get("name"):
                continue
            defense_counsel.append({
                "name":    ca.get("name", ""),
                "firm":    ca.get("firm", ""),
                "sbot":    "",
                "address": " ".join(filter(None, [
                    ca.get("address", ""),
                    ca.get("city_state_zip", ""),
                ])).strip(),
                "phone":   ca.get("phone", ""),
                "email":   ca.get("email", ""),
                "party":   plaintiff or defendant,
            })

    return {
        # ── UFM Title Page (Fig03) ───────────────────────────────
        "cause_number":       depo.get("cause_number", ""),
        "plaintiff_name":     plaintiff,
        "defendant_name":     defendant,
        "case_style":         case_style,
        "court_type":         court_type,
        "county":             county,
        "state":              depo.get("state", "Texas"),
        "judicial_district":  district_no,
        "depo_type":          depo_type,
        "subpoena_duces_tecum": subpoena_dt,
        "depo_date":          date_str,
        "depo_date_month":    dt.strftime("%B") if dt else "",
        "depo_date_day":      str(dt.day) if dt else "",
        "depo_date_year":     dt.strftime("%Y") if dt else "",
        "depo_time_start":    depo.get("scheduled_time", ""),
        "depo_location":      depo.get("location", ""),
        "depo_method":        depo.get("method", ""),
        "depo_time_end":      depo.get("scheduled_end_time", ""),

        # ── UFM Witness Fields ───────────────────────────────────
        "witness_name":       witness_name,
        "volume_number":      "1",

        # ── UFM Appearances Page (Fig04) ─────────────────────────
        "plaintiff_counsel":  plaintiff_counsel,
        "defense_counsel":    defense_counsel,
        "also_present":       [],

        # ── UFM Certificate Page (Fig05) ─────────────────────────
        "reporter_name":      reporter.get("name", "Miah Bardot"),
        "csr_number":         reporter.get("csr_number", "12129"),
        "reporter_agency":    reporter.get("agency", "SA Legal Solutions"),
        "reporter_csr_expiration": reporter.get("csr_expiration", ""),
        "reporter_firm_registration": reporter.get("firm_registration", ""),
        "reporter_address":   reporter.get("address",
                                  "3201 Cherry Ridge, B 208-3"),
        "reporter_city_state_zip": reporter.get("city_state_zip",
                                  "San Antonio, Texas 78230"),
        "reporter_phone":     reporter.get("phone", "(210) 591-1791"),

        # ── Billing / Copy Info ──────────────────────────────────
        "ordered_by":         depo.get("ordered_by", ""),
        "ordering_firm":      ord_atty.get("firm", ""),
        "copy_attorneys":     copy_attys,

        # ── Video / CSR flags ────────────────────────────────────
        "video_required":     depo.get("video_required", ""),
        "csr_required":       depo.get("csr_required", "Yes"),
    }
