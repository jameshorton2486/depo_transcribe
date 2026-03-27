"""
exhibit_index.py
Exhibit Index section (UFM Section 11).
"""

from docx import Document

from ._lined_page import paginate_lines, write_lined_page
from ..models import JobConfig


def write_exhibit_index(doc: Document, job_config: JobConfig) -> None:
    """Write the Exhibit Index page(s)."""
    jc = job_config
    sep = "\u2500" * 60
    header_lines = [
        "  INDEX OF EXHIBITS",
        "",
        f"  {'NO.':<6}{'DESCRIPTION':<36}{'OFFERED':>8}{'ADMITTED':>9}{'EXCLUDED':>9}",
        f"  {sep}",
    ]

    exhibits = jc.exhibits or []
    body_lines = []
    if not exhibits:
        for _ in range(3):
            body_lines.append(
                f"  {'___':<6}{'_________________________________':<36}{'___':>8}{'___':>9}{'___':>9}"
            )
    else:
        for exhibit in exhibits:
            desc = exhibit.description[:35] if exhibit.description else ""
            body_lines.append(
                f"  {exhibit.number:<6}{desc:<36}"
                f"{exhibit.offered_page:>8}"
                f"{exhibit.admitted_page:>9}"
                f"{exhibit.excluded_page:>9}"
            )

    for page_lines in paginate_lines(header_lines + body_lines):
        write_lined_page(doc, page_lines)
