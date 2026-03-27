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

    Returns a dict ready to be passed to JobConfig or saved as
    a ufm_fields.json alongside the transcript.
    """
    depo       = extracted.get("deposition_details", {})
    ord_atty   = extracted.get("ordering_attorney", {})
    copy_attys = extracted.get("copy_attorneys", [])
    all_attys  = extracted.get("all_attorneys", [])
    reporter   = extracted.get("court_reporter", {})

    # ── Parse date into components ──────────────────────────────
    date_str = depo.get("date", "")
    dt = None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            break
        except ValueError:
            continue

    # ── Parse plaintiff and defendant from case_style ───────────
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

    # ── Parse court into components ──────────────────────────────
    court_raw   = depo.get("court", "")
    district_no = ""
    court_type  = "DISTRICT COURT"
    m = re.search(r'(\d+)', court_raw)
    if m:
        district_no = m.group(1) + "TH"

    # ── Build plaintiff counsel list ─────────────────────────────
    plaintiff_counsel = []
    defense_counsel   = []

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

    # Fallback: use ordering attorney as plaintiff counsel
    if not plaintiff_counsel and ord_atty.get("name"):
        plaintiff_counsel.append({
            "name":    ord_atty.get("name", ""),
            "firm":    ord_atty.get("firm", ""),
            "sbot":    "",
            "address": ((ord_atty.get("address", "") or "") + " " +
                        (ord_atty.get("city_state_zip", "") or "")).strip(),
            "phone":   ord_atty.get("phone", ""),
            "email":   ord_atty.get("email", ""),
            "party":   plaintiff,
        })

    # Fallback: use copy attorneys as defense counsel
    if not defense_counsel:
        for ca in copy_attys:
            rep = (ca.get("represents", "") or "").lower()
            if "defendant" in rep or "defense" in rep:
                defense_counsel.append({
                    "name":    ca.get("name", ""),
                    "firm":    ca.get("firm", ""),
                    "sbot":    "",
                    "address": ((ca.get("address", "") or "") + " " +
                                (ca.get("city_state_zip", "") or "")).strip(),
                    "phone":   ca.get("phone", ""),
                    "email":   ca.get("email", ""),
                    "party":   defendant,
                })

    return {
        # ── UFM Title Page (Fig03) ───────────────────────────────
        "cause_number":       depo.get("cause_number", ""),
        "plaintiff_name":     plaintiff,
        "defendant_name":     defendant,
        "case_style":         case_style,
        "court_type":         court_type,
        "county":             depo.get("county", ""),
        "state":              depo.get("state", "Texas"),
        "judicial_district":  district_no,
        "depo_date":          date_str,
        "depo_date_month":    dt.strftime("%B") if dt else "",
        "depo_date_day":      str(dt.day) if dt else "",
        "depo_date_year":     dt.strftime("%Y") if dt else "",
        "depo_time_start":    depo.get("scheduled_time", ""),
        "depo_location":      depo.get("location", ""),
        "depo_method":        depo.get("method", ""),

        # ── UFM Witness Fields ───────────────────────────────────
        "witness_name":       depo.get("witness", ""),

        # ── UFM Appearances Page (Fig04) ─────────────────────────
        "plaintiff_counsel":  plaintiff_counsel,
        "defense_counsel":    defense_counsel,

        # ── UFM Certificate Page (Fig05) ─────────────────────────
        "reporter_name":      reporter.get("name", "Miah Bardot"),
        "csr_number":         reporter.get("csr_number", "12129"),
        "reporter_agency":    reporter.get("agency", "SA Legal Solutions"),

        # ── Billing / Copy Info ──────────────────────────────────
        "ordered_by":         depo.get("ordered_by", ""),
        "ordering_firm":      ord_atty.get("firm", ""),
        "copy_attorneys":     copy_attys,

        # ── Video / CSR flags ────────────────────────────────────
        "video_required":     depo.get("video_required", ""),
        "csr_required":       depo.get("csr_required", "Yes"),
    }
