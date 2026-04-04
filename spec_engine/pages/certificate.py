"""
certificate.py
Final page — Texas court reporter certification.
Spec Section 7
"""

from docx import Document

from ..models import JobConfig


def write_certificate(doc: Document, job_config: JobConfig) -> None:
    """Write the certificate page using lined-page format (Spec Section 7)."""
    from ._lined_page import paginate_lines, write_lined_page

    jc = job_config
    signature_waived = bool(getattr(jc, "signature_waived", False))
    parties = [jc.plaintiff_name] + jc.defendant_names
    parties_str = "; ".join(parties) if parties else "[parties]"

    csr_str = f"State of Texas, {jc.reporter_csr}"
    if jc.reporter_expiration:
        csr_str += f"  (Exp. {jc.reporter_expiration})"

    lines = [
        "  CERTIFICATE",
        "",
        f"  I, {jc.reporter_name}, Certified Shorthand Reporter in and for",
        "  the State of Texas, do hereby certify:",
        "",
        f"  That the witness, {jc.witness_name}, was duly sworn by me, and",
        "  that the transcript of the oral deposition is a true record of",
        "  the testimony given by the witness;",
        "",
    ]

    if signature_waived:
        lines += [
            "  That examination and signature of the witness to the",
            "  deposition transcript was waived by the witness and the",
            "  parties at the time of the deposition;",
            "",
        ]

    if jc.time_used:
        for attorney, time_str in jc.time_used.items():
            lines.append(f"    {attorney}: {time_str}")
        lines.append("")

    lines += [
        f"  That the original deposition transcript was delivered in the",
        f"  matter of {parties_str}.",
        "",
        "  That I am not a relative, employee, attorney, or counsel of",
        "  any of the parties, nor am I a relative or employee of such",
        "  attorney or counsel, nor am I financially interested in the action.",
        "",
    ]

    if jc.cost_paid_by:
        lines += [
            "  The cost of this transcript is to be paid by:",
            f"  {jc.cost_paid_by}",
            "",
        ]

    lines += [
        "",
        "",
        "  ______________________________",
        f"  {jc.reporter_name.upper()}",
        "  Certified Shorthand Reporter",
        f"  {csr_str}",
        f"  {jc.reporter_firm}",
    ]
    if jc.firm_registration:
        lines.append(f"  Firm Reg. No. {jc.firm_registration}")
    lines.append(f"  {jc.reporter_address}")
    if jc.reporter_phone:
        lines.append(f"  {jc.reporter_phone}")

    for page_lines in paginate_lines(lines):
        write_lined_page(doc, page_lines)
