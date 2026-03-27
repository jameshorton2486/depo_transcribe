"""
caption.py
Page 2 — Caption page in Texas district court format.
Spec Section 3.2
"""

from docx import Document

from ..models import JobConfig


def write_caption(doc: Document, job_config: JobConfig) -> None:
    """Write Page 2 caption in Texas district court filing format (lined-page)."""
    from ._lined_page import paginate_lines, write_lined_page

    jc = job_config
    rule = "\u2500" * 60

    witness_display = jc.witness_name.upper()
    if jc.witness_title:
        witness_display += f", {jc.witness_title.upper()}"

    appearance_lines = []
    for counsel in jc.plaintiff_counsel:
        party = counsel.party or "Plaintiff"
        appearance_lines.append(f"  FOR THE {party.upper()}:")
        appearance_lines.append(f"    {counsel.name}")
        if counsel.sbot:
            appearance_lines.append(f"    State Bar No. {counsel.sbot}")
        appearance_lines.append(f"    {counsel.firm}")
        addr_parts = [part for part in [
            counsel.address, counsel.city, counsel.state, counsel.zip_code
        ] if part]
        if addr_parts:
            appearance_lines.append(f"    {', '.join(addr_parts)}")
        if counsel.phone:
            appearance_lines.append(f"    {counsel.phone}")
        appearance_lines.append("")

    for counsel in jc.defense_counsel:
        party = counsel.party or "Defendant(s)"
        appearance_lines.append(f"  FOR THE {party.upper()}:")
        appearance_lines.append(f"    {counsel.name}")
        if counsel.sbot:
            appearance_lines.append(f"    State Bar No. {counsel.sbot}")
        appearance_lines.append(f"    {counsel.firm}")
        addr_parts = [part for part in [
            counsel.address, counsel.city, counsel.state, counsel.zip_code
        ] if part]
        if addr_parts:
            appearance_lines.append(f"    {', '.join(addr_parts)}")
        if counsel.phone:
            appearance_lines.append(f"    {counsel.phone}")
        appearance_lines.append("")

    if jc.also_present:
        appearance_lines.append("  ALSO PRESENT:")
        for name in jc.also_present:
            appearance_lines.append(f"    {name}")
        appearance_lines.append("")

    csr_str = jc.reporter_name
    if jc.reporter_csr:
        csr_str += f", {jc.reporter_csr}"
    if jc.reporter_expiration:
        csr_str += f"  (Exp. {jc.reporter_expiration})"

    reporter_lines = [
        "  COURT REPORTER:",
        f"    {csr_str}",
        f"    {jc.reporter_firm}",
    ]
    if jc.firm_registration:
        reporter_lines.append(f"    Firm Reg. No. {jc.firm_registration}")
    reporter_lines.append(f"    {jc.reporter_address}")
    if jc.reporter_phone:
        reporter_lines.append(f"    {jc.reporter_phone}")

    lines = [
        f"  IN THE {jc.court_type.upper()}",
        f"  {jc.court.upper()}",
        f"  {rule}",
        f"  {jc.plaintiff_name},",
        "        Plaintiff,",
        f"                                    Cause No. {jc.cause_number}",
        "  vs.",
    ]
    for defendant in jc.defendant_names:
        lines.append(f"  {defendant},")
    lines += [
        "        Defendant(s).",
        f"  {rule}",
        f"  DEPOSITION OF {witness_display}",
        f"  Taken on {jc.depo_date}",
    ]
    if jc.method and jc.method.lower() not in ("in person", "in-person"):
        lines.append(f"  Method: {jc.method}")
    if jc.subpoena_duces_tecum:
        lines.append("  (Subpoena Duces Tecum)")
    lines += [f"  {rule}", "  A P P E A R A N C E S", ""]
    lines += appearance_lines
    lines += reporter_lines
    lines += [f"  {rule}", "  PROCEEDINGS"]

    for page_lines in paginate_lines(lines):
        write_lined_page(doc, page_lines)
