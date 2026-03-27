"""
witness_index.py
Witness Index section (UFM Section 11).
"""

from docx import Document

from ._lined_page import paginate_lines, write_lined_page
from ..models import JobConfig


def write_witness_index(doc: Document, job_config: JobConfig) -> None:
    """Write the Witness Index page(s)."""
    jc = job_config
    sep = "\u2500" * 60
    header_lines = [
        "  INDEX OF WITNESSES",
        "",
        f"  {'WITNESS':<30}{'DIR':>5}{'CRS':>5}{'REDIR':>6}{'RECRSS':>7}{'VD':>4}",
        f"  {sep}",
    ]

    witnesses = jc.witnesses or []
    body_lines = []
    if not witnesses:
        body_lines.append(f"  {'[WITNESS NAME]':<30}{'':>5}{'':>5}{'':>6}{'':>7}{'':>4}")
    else:
        for witness in witnesses:
            body_lines.append(
                f"  {witness.name:<30}"
                f"{witness.direct_page:>5}"
                f"{witness.cross_page:>5}"
                f"{witness.redirect_page:>6}"
                f"{witness.recross_page:>7}"
                f"{witness.voir_dire_page:>4}"
            )

    for page_lines in paginate_lines(header_lines + body_lines):
        write_lined_page(doc, page_lines)
