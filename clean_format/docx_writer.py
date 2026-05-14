"""DOCX writer for clean-format deposition output."""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from clean_format.low_confidence_markers import split_into_runs

# Windows-illegal filename characters plus ASCII control bytes. NTFS
# silently treats `:` as an alternate-data-stream separator, so a bad
# filename can succeed at write time but be unreachable to Word.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')
_WHITESPACE_RUN = re.compile(r"\s+")
_TRAILING_AT_SUFFIX = re.compile(r"\s+at\s+.*$", re.IGNORECASE)
_SENTENCE_SPACE_RE = re.compile(r"([.!?])\s+")

# Reporter's Certificate template (Texas, signature required).
# Sourced from ufm_engine/templates/figures/. The template is
# treated as read-only; defect #9 copies its paragraphs into
# the deposition document with field substitution.
#
# Signature-waived variant deferred to a future defect.
_CERT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "ufm_engine"
    / "templates"
    / "figures"
    / "cert_tx_sig_required.docx"
)

# Always-blank placeholders per Shaw convention. These represent
# reporter-fillable values that aren't known at transcript
# generation time.
_ALWAYS_BLANK_PLACEHOLDERS = {
    "[Submitted Date]": "____________________",
    "[Return-By Date]": "____________________",
    "[Certification Date]": "_____ day of ___________, _____",
}

# Default placeholder for missing reporter/firm fields. Visible
# blank > silent fabrication for legal documents.
_BLANK_FIELD_PLACEHOLDER = "_______"


def sanitize_filename_component(value: str) -> str:
    """
    Strip Windows-illegal characters from a filename component.

    Removes <>:"/\\|?* and ASCII control bytes, collapses whitespace runs,
    strips leading/trailing dots and spaces. Falls back to "document" when
    the input is empty or sanitizes to nothing — bare-suffix filenames
    (e.g. ".docx") are illegal on Windows.
    """
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("", value or "")
    cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip()
    cleaned = cleaned.strip(". ")
    return cleaned or "document"


def safe_save(
    document: Document, path: Path, *, retries: int = 3, delay_seconds: float = 1.0
) -> None:
    """Retry transient Word lock failures before surfacing a clean error."""
    for attempt in range(retries):
        try:
            document.save(path)
            return
        except PermissionError:
            if attempt == retries - 1:
                break
            time.sleep(delay_seconds)

    raise PermissionError(f"File is open or locked:\n{path}")


def _set_cell_border(cell: Any) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "8")
        element.set(qn("w:color"), "000000")


def _set_document_defaults(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)

    style = document.styles["Normal"]
    style.font.name = "Courier New"
    style.font.size = Pt(12)
    paragraph_format = style.paragraph_format
    paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    paragraph_format.space_after = Pt(0)


def _center_paragraph(document: Document, text: str, *, bold: bool = False) -> Any:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.bold = bold
    return paragraph


def _left_paragraph(document: Document, text: str = "", *, bold: bool = False) -> Any:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = bold
    return paragraph


def _format_date_for_filename(raw_date: str) -> str:
    # Intake often appends a start time after the date ("April 9, 2026 at
    # 8:00 a.m."). Strip that suffix before strptime so the strict formats
    # below have a chance to match.
    candidate = _TRAILING_AT_SUFFIX.sub("", raw_date or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return (candidate or raw_date).replace("/", "-").replace(",", "")


def _double_space_sentences(text: str) -> str:
    return _SENTENCE_SPACE_RE.sub(r"\1  ", (text or "").strip())


def _add_marked_runs(paragraph: Any, text: str) -> None:
    """Append one or more runs to ``paragraph`` for ``text``, highlighting
    any ``‹LC:...›``-wrapped chunks with yellow.

    Step D of the verbatim-punctuation plan. Marker characters
    themselves are stripped at render time — the paragraph's resulting
    ``.text`` contains only the wrapped token text, not the marker
    boundaries.

    When ``text`` has no markers, this collapses to a single
    default-styled run with the original text (no change in document
    output for unmarked content).

    When ``text`` is empty, no run is added — matches the prior
    behavior of ``add_run("")``.
    """
    runs = split_into_runs(text)
    if not runs:
        return
    for chunk, is_low_confidence in runs:
        run = paragraph.add_run(chunk)
        if is_low_confidence:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW


def _parse_blocks(formatted_text: str) -> list[dict[str, str]]:
    """Parse emitter output into structured blocks for rendering.

    Recognizes the emitter's tab-prefixed shapes:

      * ``\tQ.\t<body>`` and ``\tA.\t<body>`` -> kind="qa".
      * A multi-line emitter block whose first line is
        ``\t\t\t<SPEAKER>:`` followed by ``\t\t\t<body>``
        lines -> kind="colloquy_block" with merged body.
      * A single-line ``\t\t\t<text>`` block (no colon-ended
        speaker label) -> kind="directive".
      * A bare ``<HEADER>:`` line with no tab prefix ->
        kind="header" (manually-added section headers like
        "EXAMINATION:" in _write_proceedings).

    Returns the legacy ``kind="speaker"`` form only for content
    that doesn't match any of the above patterns - defensive
    fallback that shouldn't fire in practice with the current
    emitter output.
    """
    blocks: list[dict[str, str]] = []
    for raw_block in (formatted_text or "").split("\n\n"):
        lines = [line.rstrip() for line in raw_block.splitlines() if line.strip()]
        if not lines:
            continue

        first = lines[0]

        if first.startswith("\tQ.\t"):
            blocks.append({"kind": "qa", "label": "Q.", "text": first[4:]})
            for extra in lines[1:]:
                tail = extra.lstrip("\t").strip()
                if tail:
                    blocks[-1]["text"] += " " + tail
            continue
        if first.startswith("Q.\t"):
            blocks.append({"kind": "qa", "label": "Q.", "text": first[3:]})
            for extra in lines[1:]:
                tail = extra.lstrip("\t").strip()
                if tail:
                    blocks[-1]["text"] += " " + tail
            continue
        if first.startswith("\tA.\t"):
            blocks.append({"kind": "qa", "label": "A.", "text": first[4:]})
            for extra in lines[1:]:
                tail = extra.lstrip("\t").strip()
                if tail:
                    blocks[-1]["text"] += " " + tail
            continue
        if first.startswith("A.\t"):
            blocks.append({"kind": "qa", "label": "A.", "text": first[3:]})
            for extra in lines[1:]:
                tail = extra.lstrip("\t").strip()
                if tail:
                    blocks[-1]["text"] += " " + tail
            continue

        if first.startswith("\t\t\t") and first.rstrip().endswith(":"):
            label = first[3:].rstrip()
            body_lines: list[str] = []
            for extra in lines[1:]:
                body_lines.append(extra.lstrip("\t"))
            text = "\n".join(body_lines).strip()
            blocks.append(
                {"kind": "colloquy_block", "label": label, "text": text}
            )
            continue

        if ":\t" in first:
            label, text = first.split(":\t", 1)
            blocks.append({"kind": "speaker", "label": label + ":", "text": text})
            continue

        if first.startswith("\t\t\t"):
            text = first.lstrip("\t").strip()
            for extra in lines[1:]:
                tail = extra.lstrip("\t").strip()
                if tail:
                    text += "\n" + tail
            blocks.append({"kind": "directive", "label": "", "text": text})
            continue

        if first.endswith(":"):
            blocks.append({"kind": "header", "label": first, "text": ""})
            continue

        blocks.append({"kind": "directive", "label": "", "text": first})

    return _merge_consecutive_speaker_blocks(blocks)


def _merge_consecutive_speaker_blocks(
    blocks: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Merge consecutive same-speaker colloquy_block entries.

    With the new tab-prefixed parser, the legacy ``kind="speaker"``
    merging path is no longer the primary case. Consecutive same-
    speaker colloquy still benefits from merging when the emitter
    produces them as separate emitter blocks (rare in current
    output but possible).

    Legacy ``kind="speaker"`` blocks are still merged the same way
    for backward compatibility, in case any caller produces them.
    """
    merged: list[dict[str, str]] = []
    for block in blocks:
        if (
            merged
            and block["kind"] == "colloquy_block"
            and merged[-1]["kind"] == "colloquy_block"
            and block["label"]
            and block["label"] == merged[-1]["label"]
        ):
            prior_text = merged[-1]["text"].rstrip()
            current_text = block["text"].lstrip()
            merged[-1]["text"] = f"{prior_text}\n{current_text}"
            continue
        if (
            merged
            and block["kind"] == "speaker"
            and merged[-1]["kind"] == "speaker"
            and block["label"]
            and block["label"] == merged[-1]["label"]
        ):
            prior_text = merged[-1]["text"].rstrip()
            current_text = block["text"].lstrip()
            merged[-1]["text"] = _double_space_sentences(f"{prior_text} {current_text}")
            continue
        if block["kind"] == "speaker" and block["text"]:
            block = {**block, "text": _double_space_sentences(block["text"])}
        merged.append(block)
    return merged


def _write_caption_table(document: Document, case_meta: dict[str, Any]) -> None:
    table = document.add_table(rows=4, cols=3)
    table.columns[0].width = Inches(3)
    table.columns[1].width = Inches(0.4)
    table.columns[2].width = Inches(3)

    defendant_text = "\n".join(case_meta.get("defendant_names", []) or [])
    right_top = "IN THE DISTRICT COURT"
    district = case_meta.get("judicial_district", "")
    county = case_meta.get("county", "")
    right_bottom = f"{district} JUDICIAL DISTRICT\n{county} COUNTY, TEXAS".strip()

    rows = [
        (case_meta.get("plaintiff_name", ""), "§", right_top),
        ("Plaintiff,", "§", ""),
        ("vs.", "§", right_bottom),
        (defendant_text or "Defendant", "§", ""),
    ]
    for row_index, row_values in enumerate(rows):
        for col_index, value in enumerate(row_values):
            cell = table.cell(row_index, col_index)
            cell.text = value
            _set_cell_border(cell)
            if col_index == 1:
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER


def _write_appearances(document: Document, case_meta: dict[str, Any]) -> None:
    _center_paragraph(document, "APPEARANCES", bold=True)
    attorneys = case_meta.get("attorneys", []) or []
    plaintiffs = [entry for entry in attorneys if entry.get("role") == "plaintiff"]
    defendants = [entry for entry in attorneys if entry.get("role") == "defendant"]

    if plaintiffs:
        _left_paragraph(document, "FOR THE PLAINTIFF", bold=True)
        for entry in plaintiffs:
            _left_paragraph(document, entry.get("name", ""))
            if entry.get("city"):
                _left_paragraph(document, entry["city"])

    if defendants:
        for entry in defendants:
            _left_paragraph(
                document, f"FOR DEFENDANT {entry.get('name', '').upper()}", bold=True
            )
            _left_paragraph(document, entry.get("name", ""))
            if entry.get("city"):
                _left_paragraph(document, entry["city"])

    _left_paragraph(document, "ALSO PRESENT", bold=True)
    if case_meta.get("videographer_name"):
        _left_paragraph(document, case_meta["videographer_name"])
    if case_meta.get("reporter_name"):
        _left_paragraph(document, case_meta["reporter_name"])


def _write_proceedings(
    document: Document, formatted_text: str, case_meta: dict[str, Any]
) -> None:
    _center_paragraph(document, "PROCEEDINGS", bold=True)

    witness_name = case_meta.get("witness_name", "").upper()
    if witness_name:
        _center_paragraph(document, f"{witness_name},", bold=True)
        _left_paragraph(document, "having been first duly sworn, testified as follows:")
        _center_paragraph(document, "EXAMINATION", bold=True)

        examining = next(
            (
                entry
                for entry in case_meta.get("attorneys", []) or []
                if entry.get("role") == "defendant"
            ),
            None,
        )
        if examining:
            last_name = examining.get("name", "").split()[-1].upper()
            _left_paragraph(document, f"BY MS. {last_name}:")

    for block in _parse_blocks(formatted_text):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
        paragraph.paragraph_format.space_after = Pt(0)
        # Canonical UFM tab stops per spec_engine/ufm_rules.py:25
        # (UFM Section 2.102.11). The "\tQ.\t..." / "\tA.\t..." text from
        # spec_engine/emitter.py lands the letter at 0.5" and the body at
        # 1.0"; the third stop at 1.5" exists for indented continuation.
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(0.5))
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(1.0))
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(1.5))

        if block["kind"] == "qa":
            # Hanging indent for Q/A wrap, with the canonical leading-tab
            # text shape "\tQ.\t{body}" / "\tA.\t{body}" (matches what
            # spec_engine/emitter.py emits).
            #
            # Geometry:
            #   left_indent       = 1.0"   — wrapped continuation lines
            #                                hang at 1.0", aligning under
            #                                the first character of body.
            #   first_line_indent = -1.0"  — first-line origin is column 0
            #                                so the leading "\t" lands the
            #                                "Q."/"A." letter at the 0.5"
            #                                tab stop, then the body tab
            #                                pushes text to the 1.0" stop.
            paragraph.paragraph_format.left_indent = Inches(1.0)
            paragraph.paragraph_format.first_line_indent = Inches(-1.0)
            # Step D: prefix run holds the canonical "\tQ.\t" / "\tA.\t"
            # shape; body text is split on low-confidence markers so each
            # marked token renders as its own yellow-highlighted run.
            paragraph.add_run(f"\t{block['label']}\t")
            _add_marked_runs(paragraph, block["text"])
        elif block["kind"] == "colloquy_block":
            # Colloquy: speaker label line plus one or more body
            # lines within a single paragraph. Hanging indent at
            # 1.5" so the leading "\t\t\t" lands first-line content
            # at the 1.5" tab stop and wrap continuation also
            # lands at 1.5".
            #
            # Body lines after the label are emitted as soft line
            # breaks (run.add_break) inside the same paragraph, so
            # they share the same indent geometry.
            paragraph.paragraph_format.left_indent = Inches(1.5)
            paragraph.paragraph_format.first_line_indent = Inches(-1.5)
            paragraph.add_run(f"\t\t\t{block['label']}")
            body = (block.get("text") or "").strip()
            if body:
                for body_line in body.split("\n"):
                    line_text = body_line.strip()
                    if not line_text:
                        continue
                    break_run = paragraph.add_run()
                    break_run.add_break()
                    paragraph.add_run("\t\t\t")
                    _add_marked_runs(
                        paragraph, _double_space_sentences(line_text)
                    )
        elif block["kind"] == "directive":
            # Directive: single text line at 1.5", hanging indent
            # so any wrap continuation also lands at 1.5".
            paragraph.paragraph_format.left_indent = Inches(1.5)
            paragraph.paragraph_format.first_line_indent = Inches(-1.5)
            paragraph.add_run("\t\t\t")
            _add_marked_runs(
                paragraph, _double_space_sentences(block.get("text") or "")
            )
        elif block["kind"] == "speaker":
            # Legacy speaker kind - retained for backward compat
            # with any caller producing the old shape. Geometry
            # uses the new 1.5" hanging indent so wrap continuation
            # matches the visible first-line position.
            paragraph.paragraph_format.left_indent = Inches(1.5)
            paragraph.paragraph_format.first_line_indent = Inches(-1.5)
            if block["label"]:
                paragraph.add_run(f"\t\t\t{block['label']}  ")
                _add_marked_runs(paragraph, block["text"])
            else:
                paragraph.add_run("\t\t\t")
                _add_marked_runs(
                    paragraph, _double_space_sentences(block["text"])
                )
        else:
            # header kind - manually-added section headers like
            # "EXAMINATION:" rendered without indent. Unchanged.
            paragraph.paragraph_format.left_indent = Inches(0)
            paragraph.paragraph_format.first_line_indent = Inches(0)
            run = paragraph.add_run(f"\t\t\t{block['label']}")
            run.bold = True


def _derive_court_designation(judicial_district: str) -> str:
    """Map a judicial district string to a court designation phrase.

    Texas district court captions use the form 'IN THE DISTRICT
    COURT OF' for Texas state courts. If a numeric district like
    '37TH' is present, return 'IN THE 37TH JUDICIAL DISTRICT'.
    Otherwise return the bare 'IN THE DISTRICT COURT' fallback.
    """
    district = (judicial_district or "").strip()
    if not district:
        return "IN THE DISTRICT COURT"
    return f"IN THE {district.upper()} JUDICIAL DISTRICT"


def _derive_judicial_district_phrase(judicial_district: str) -> str:
    """Return the right-side caption phrase, e.g. '115TH JUDICIAL DISTRICT'."""
    district = (judicial_district or "").strip()
    if not district:
        return "JUDICIAL DISTRICT"
    return f"{district.upper()} JUDICIAL DISTRICT"


def _render_time_used_per_attorney(attorneys: list[dict] | None) -> str:
    """Render the multi-line 'time used' block per Shaw convention.

    One line per attorney with name + blank time placeholder. If
    no attorneys, render a single placeholder line.
    """
    if not attorneys:
        return (
            f"{_BLANK_FIELD_PLACEHOLDER}_______________ "
            "(______ hours ______ minutes)"
        )
    lines = []
    for entry in attorneys:
        name = (entry.get("name") or "").strip() or _BLANK_FIELD_PLACEHOLDER
        lines.append(f"{name} (______ hours ______ minutes)")
    return "\n".join(lines)


def _render_attorney_party_pairs(
    attorneys: list[dict] | None,
    plaintiff_name: str,
    defendant_names: list[str] | None,
) -> str:
    """Render the multi-line attorney/party block.

    One line per attorney with format 'NAME, Attorney for ROLE PARTY'.
    Plaintiff attorneys are paired with the plaintiff_name.
    Defendant attorneys are paired with the defendant_names
    (first one if multiple, since per-attorney mapping isn't tracked).
    """
    if not attorneys:
        return "_______________________________"
    plaintiff = (plaintiff_name or "").strip()
    defendants = defendant_names or []
    primary_defendant = (defendants[0] if defendants else "").strip()

    lines = []
    for entry in attorneys:
        name = (entry.get("name") or "").strip() or _BLANK_FIELD_PLACEHOLDER
        role = (entry.get("role") or "").strip().lower()
        if role == "plaintiff":
            party_label = f"Plaintiff, {plaintiff}" if plaintiff else "Plaintiff"
        else:
            party_label = (
                f"Defendant, {primary_defendant}"
                if primary_defendant
                else "Defendant"
            )
        lines.append(f"{name}, Attorney for {party_label}")
    return "\n".join(lines)


def _substitute_case_placeholders(text: str, case_meta: dict[str, Any]) -> str:
    """Substitute case-level and reporter/firm placeholders.

    Applied in order. The order matters: longer/more-specific
    placeholders are substituted before shorter ones to avoid
    partial replacement.
    """
    attorneys = case_meta.get("attorneys") or []
    defendant_names = case_meta.get("defendant_names") or []

    substitutions = [
        ("[Plaintiff Name(s)]", case_meta.get("plaintiff_name", "") or ""),
        (
            "[Court Designation]",
            _derive_court_designation(case_meta.get("judicial_district", "")),
        ),
        (
            "[Judicial District Phrase]",
            _derive_judicial_district_phrase(case_meta.get("judicial_district", "")),
        ),
        ("[Defendant Names]", "\n".join(defendant_names) if defendant_names else ""),
        ("[Witness Name]", case_meta.get("witness_name", "") or ""),
        ("[Deposition Date]", case_meta.get("deposition_date", "") or ""),
        ("[Reporter Name]", case_meta.get("reporter_name", "") or ""),
        ("[Cause Number]", case_meta.get("cause_number", "") or ""),
        ("[County]", case_meta.get("county", "") or ""),
        (
            "[Time Used Per Attorney (multi-line)]",
            _render_time_used_per_attorney(attorneys),
        ),
        ("[Time Used Per Attorney]", _render_time_used_per_attorney(attorneys)),
        (
            "[Attorney/Party Pairs (multi-line)]",
            _render_attorney_party_pairs(
                attorneys,
                case_meta.get("plaintiff_name", ""),
                defendant_names,
            ),
        ),
        (
            "[Attorney/Party Pairs]",
            _render_attorney_party_pairs(
                attorneys,
                case_meta.get("plaintiff_name", ""),
                defendant_names,
            ),
        ),
        (
            "[Credentials]",
            case_meta.get("reporter_credentials") or _BLANK_FIELD_PLACEHOLDER,
        ),
        ("[CSR Number]", case_meta.get("reporter_csr") or _BLANK_FIELD_PLACEHOLDER),
        (
            "[CSR Expiration]",
            case_meta.get("reporter_csr_expiration") or _BLANK_FIELD_PLACEHOLDER,
        ),
        ("[Firm Name]", case_meta.get("firm_name") or _BLANK_FIELD_PLACEHOLDER),
        (
            "[Firm Reg No.]",
            case_meta.get("firm_registration") or _BLANK_FIELD_PLACEHOLDER,
        ),
        (
            "[Address Line 1]",
            case_meta.get("firm_address_line1") or _BLANK_FIELD_PLACEHOLDER,
        ),
        ("[City]", case_meta.get("firm_city") or _BLANK_FIELD_PLACEHOLDER),
        ("[ZIP]", case_meta.get("firm_zip") or _BLANK_FIELD_PLACEHOLDER),
        ("[Phone]", case_meta.get("firm_phone") or _BLANK_FIELD_PLACEHOLDER),
        ("[Email]", case_meta.get("firm_email") or _BLANK_FIELD_PLACEHOLDER),
    ]

    out = text
    for placeholder, replacement in substitutions:
        if placeholder in out:
            out = out.replace(placeholder, replacement)

    for placeholder, replacement in _ALWAYS_BLANK_PLACEHOLDERS.items():
        if placeholder in out:
            out = out.replace(placeholder, replacement)

    if "[State]" in out:
        if "COUNTY," in out.upper():
            out = out.replace("[State]", "TEXAS")
        else:
            firm_state = case_meta.get("firm_state") or _BLANK_FIELD_PLACEHOLDER
            out = out.replace("[State]", firm_state)

    return out


def _extract_paragraph_text(paragraph: Any) -> str:
    """Concatenate all text runs in a paragraph, including those
    inside structured-document-tag (SDT) content controls.

    python-docx's ``paragraph.text`` only returns text from
    top-level runs and misses content-control wrapped text.
    Reach into the XML and grab every <w:t> directly.
    """
    paragraph_element = getattr(paragraph, "_p", paragraph)
    texts = []
    for t_element in paragraph_element.iter(qn("w:t")):
        if t_element.text:
            texts.append(t_element.text)
    return "".join(texts)


def _extract_paragraph_formatting(paragraph: Any) -> dict[str, Any]:
    """Extract alignment and bold flags from a template paragraph.

    Returns a dict with 'alignment' (WD_ALIGN_PARAGRAPH or None)
    and 'bold' (bool). These match the formatting hints the
    deposition document writer can reproduce.
    """
    paragraph_element = getattr(paragraph, "_p", paragraph)

    alignment = None
    jc_element = next(paragraph_element.iter(qn("w:jc")), None)
    if jc_element is not None:
        jc_value = jc_element.get(qn("w:val"))
        alignment_map = {
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
            "both": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
        }
        alignment = alignment_map.get(jc_value)

    bold = next(paragraph_element.iter(qn("w:b")), None) is not None

    return {"alignment": alignment, "bold": bold}


def _write_reporters_certificate(
    document: Document, case_meta: dict[str, Any]
) -> None:
    """Append a Texas TRCP-compliant reporter's certificate page
    (signature required) to the deposition document.

    Reads the canonical template at
    ``ufm_engine/templates/figures/cert_tx_sig_required.docx``
    and copies each paragraph into the main document with
    case_meta field substitution.

    The signature-waived variant
    (``cert_tx_sig_waived.docx``) is intentionally out of
    scope for defect #9. A future defect can add it via a
    case_meta flag.

    Missing reporter/firm fields render as visible blank
    placeholders per Shaw convention; never fabricate values.
    """
    if not _CERT_TEMPLATE_PATH.exists():
        return

    document.add_page_break()
    template_doc = Document(str(_CERT_TEMPLATE_PATH))

    for template_paragraph in template_doc.element.body.iter(qn("w:p")):
        raw_text = _extract_paragraph_text(template_paragraph)
        substituted = _substitute_case_placeholders(raw_text, case_meta)
        formatting = _extract_paragraph_formatting(template_paragraph)

        for line in substituted.split("\n"):
            new_paragraph = document.add_paragraph()
            new_paragraph.paragraph_format.line_spacing_rule = (
                WD_LINE_SPACING.DOUBLE
            )
            new_paragraph.paragraph_format.space_after = Pt(0)
            if formatting["alignment"] is not None:
                new_paragraph.alignment = formatting["alignment"]
            run = new_paragraph.add_run(line)
            if formatting["bold"]:
                run.bold = True


def build_deposition_document(
    formatted_text: str, case_meta: dict[str, Any]
) -> Document:
    document = Document()
    _set_document_defaults(document)

    _center_paragraph(
        document, f"CAUSE NO. {case_meta.get('cause_number', '')}", bold=True
    )
    _write_caption_table(document, case_meta)
    _center_paragraph(document, "* * * * *")
    _center_paragraph(document, "ORAL VIDEOTAPED", bold=True)
    _center_paragraph(document, "DEPOSITION OF", bold=True)
    _center_paragraph(document, case_meta.get("witness_name", "").upper(), bold=True)
    _center_paragraph(document, case_meta.get("deposition_date", ""), bold=True)

    document.add_paragraph()
    _left_paragraph(
        document,
        (
            f"ORAL VIDEOTAPED DEPOSITION OF {case_meta.get('witness_name', '').upper()}, "
            "produced as a witness at the time and place set out below."
        ),
    )
    document.add_paragraph()
    _write_appearances(document, case_meta)
    document.add_page_break()
    _write_proceedings(document, formatted_text, case_meta)
    _write_reporters_certificate(document, case_meta)
    return document


def write_deposition_docx(
    formatted_text: str,
    case_meta: dict[str, Any],
    output_path: str | Path | None = None,
) -> str:
    witness_last = (case_meta.get("witness_name", "Witness").split() or ["Witness"])[-1]
    date_part = _format_date_for_filename(str(case_meta.get("deposition_date", "")))
    if output_path:
        path = Path(output_path)
    else:
        path = Path(f"{witness_last}_Deposition_{date_part}.docx")
    # Last-line defense: sanitize the filename stem regardless of whether
    # output_path was passed. Callers that pre-build a path (UI, CLI) miss
    # the helper above, and a `:` in the name silently writes into an ADS
    # rather than a real file Word can open.
    suffix = path.suffix or ".docx"
    sanitized_stem = sanitize_filename_component(path.stem)
    path = path.with_name(f"{sanitized_stem}{suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    document = build_deposition_document(formatted_text, case_meta)
    safe_save(document, path)
    return str(path)
