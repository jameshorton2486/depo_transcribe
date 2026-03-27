"""
changes_signature.py
Changes and Signature page — UFM Figures 7 and 7A.
"""

from docx import Document

from ._lined_page import paginate_lines, write_lined_page
from ..models import JobConfig

CHANGE_ROWS_PAGE1 = 20


def write_changes_signature(doc: Document, job_config: JobConfig) -> None:
    """Write the changes table and signature/notary page."""
    jc = job_config

    lines_p1 = [
        "  CHANGES AND SIGNATURE",
        "",
        f"  WITNESS NAME: {jc.witness_name:<28}  DATE: {jc.depo_date}",
        f"  {'PAGE':<8}{'LINE':<8}{'CHANGE':<30}REASON",
    ]

    changes = jc.changes or []
    for idx in range(CHANGE_ROWS_PAGE1):
        if idx < len(changes):
            change = changes[idx]
            lines_p1.append(
                f"  {change.page:<8}{change.line:<8}{change.change:<30}{change.reason}"
            )
        else:
            lines_p1.append(
                f"  {'______':<8}{'______':<8}{'______________________':<30}__________________"
            )

    while len(lines_p1) < 25:
        lines_p1.append("")
    write_lined_page(doc, lines_p1)

    if len(changes) > CHANGE_ROWS_PAGE1:
        overflow_lines = [
            "  CHANGES AND SIGNATURE (continued)",
            "",
            f"  {'PAGE':<8}{'LINE':<8}{'CHANGE':<30}REASON",
            "",
        ]
        for change in changes[CHANGE_ROWS_PAGE1:]:
            overflow_lines.append(
                f"  {change.page:<8}{change.line:<8}{change.change:<30}{change.reason}"
            )
        for page_lines in paginate_lines(overflow_lines):
            write_lined_page(doc, page_lines)

    id_method = jc.identification_method or (
        "driver's license or other government-issued photo identification"
    )
    lines_p2 = [
        f"  I, {jc.witness_name}, have read the foregoing",
        "  deposition and hereby affix my signature that same is",
        "  true and correct, except as noted above.",
        "",
        "",
        "  ______________________________",
        f"  ({jc.witness_name.upper()})",
        "",
        "  THE STATE OF TEXAS              )",
        f"  COUNTY OF {jc.notary_county or '___________________'}    )",
        f"  Before me, {jc.notary_name or '________________'}, on this day personally",
        f"  appeared {jc.witness_name} known to me (or",
        f"  proved to me under oath or through {id_method})",
        "  (description of identity card or other document) to be the",
        "  person whose name is subscribed to the foregoing instrument",
        "  and acknowledged to me that they executed the same for the",
        "  purposes and consideration therein expressed.",
        "  Given under my hand and seal of office this _____",
        "  day of _____________________, _______.",
        "",
        "",
        "",
        "  NOTARY PUBLIC IN AND FOR",
        "  THE STATE OF TEXAS",
        "",
    ]
    write_lined_page(doc, lines_p2)
