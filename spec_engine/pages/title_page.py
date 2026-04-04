"""
title_page.py
Page — Style/Title Page (Fig03 UFM layout).
"""

from docx import Document

from ._lined_page import paginate_lines, write_lined_page
from ..models import JobConfig


def write_title_page(doc: Document, job_config: JobConfig) -> None:
    """Write the Style/Title page (UFM Fig03)."""
    jc = job_config

    method_note = ""
    if jc.method and jc.method.lower() not in ("in person", "in-person"):
        method_note = f", via {jc.method},"

    depo_label = "ORAL AND VIDEOTAPED" if jc.is_videotaped else "ORAL"
    def_display = jc.defendant_names[0] if jc.defendant_names else "[DEFENDANT]"
    if len(jc.defendant_names) > 1:
        def_display += ", et al."

    rule = "\u2500" * 60

    lines = [
        f"  NO. {jc.cause_number}",
        "",
        f"  {jc.plaintiff_name},    )   IN THE {jc.court_type.upper()} OF",
        "  Plaintiff(s)           )",
        f"  VS.                    )   {jc.county.upper()} COUNTY, TEXAS",
        f"  {def_display},    )",
        f"  Defendant(s)           )   {jc.judicial_district} JUDICIAL DISTRICT",
        "",
        f"  {rule}",
        f"  {depo_label} DEPOSITION OF",
        f"  {jc.witness_name.upper()}",
        f"  {jc.depo_date}",
        f"  {rule}",
        "",
        f"  {depo_label} DEPOSITION OF {jc.witness_name},",
        f"  produced as a witness at the instance of {jc.plaintiff_name},",
        "  and duly sworn, was taken in the above-styled",
        f"  and numbered cause on the {jc.depo_date}, from",
        f"  {jc.depo_start_time} to {jc.depo_end_time}{method_note} before",
        f"  {jc.reporter_name}, {jc.reporter_csr} in and for the State of Texas,",
        "  at the offices of",
        f"  {jc.location}, {jc.location_city}, pursuant to the Texas Rules",
        "  of Civil Procedure and the provisions stated on the record",
        "  or attached hereto.",
    ]

    for page_lines in paginate_lines(lines):
        write_lined_page(doc, page_lines)
