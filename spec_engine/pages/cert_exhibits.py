"""
cert_exhibits.py
Official Reporter's Record — Certification Page for Exhibits (UFM Fig06).
"""

from docx import Document

from ._lined_page import paginate_lines, write_lined_page
from ..models import JobConfig


def write_cert_exhibits(doc: Document, job_config: JobConfig) -> None:
    """Write the Exhibit Volume Certification page (UFM Fig06)."""
    jc = job_config

    def_display = jc.defendant_names[0] if jc.defendant_names else "[DEFENDANT]"
    if len(jc.defendant_names) > 1:
        def_display += ", et al."

    cost_line = ""
    if jc.cost_total or jc.cost_paid_by:
        cost_line = (
            "  I further certify that the total cost for the preparation of this "
            f"Reporter's Record is ${jc.cost_total or '______'} and was paid/will "
            f"be paid by {jc.cost_paid_by or '_______________________'}."
        )

    rule = "\u2500" * 60
    lines = [
        f"  TRIAL COURT CAUSE NO. {jc.cause_number}",
        f"  {jc.plaintiff_name},    )   IN THE {jc.court_type.upper()} OF",
        f"  VS.                    )   {jc.county.upper()} COUNTY, TEXAS",
        f"  {def_display},    )   {jc.judicial_district} JUDICIAL DISTRICT",
        f"  {rule}",
        f"  I, {jc.reporter_name}, Official Court Reporter in",
        f"  and for the {jc.judicial_district} District Court of {jc.county}, Texas,",
        "  do hereby certify that the foregoing exhibits constitute",
        "  true and complete duplicates of the original exhibits,",
        "  excluding physical evidence, admitted, tendered in an",
        "  offer of proof or offered into evidence during the",
        f"  {jc.proceeding_type} in the above entitled and numbered",
        f"  cause as set out herein before the Honorable {jc.judge_name},",
        f"  Judge of the {jc.judicial_district} District Court of {jc.county} County,",
        f"  Texas, beginning {jc.depo_date}.",
    ]

    if cost_line:
        lines.extend(["", cost_line])

    lines.extend([
        "",
        "  WITNESS MY OFFICIAL HAND on this, the _________",
        "  day of _____________________, _______.",
        "",
        "",
        f"  {jc.reporter_name}, Texas {jc.reporter_csr}",
        f"  Expiration Date: {jc.reporter_expiration or '__/__/__'}  Official Court Reporter",
        f"  {jc.county} County, Texas",
        "",
        "",
    ])

    for page_lines in paginate_lines(lines):
        write_lined_page(doc, page_lines)
