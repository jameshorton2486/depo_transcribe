"""
core/pdf_extractor.py

Hybrid regex + Claude API extraction pipeline for case information PDFs.
Regex runs first for speed; Claude API is called only for fields that
regex could not extract.
"""

import json
import os
import re
import glob
from typing import Any

from app_logging import get_logger
from core.config import AI_MODEL

logger = get_logger(__name__)


def _extract_keyterms_from_pdf_text(text: str, progress_callback=None) -> list[str]:
    """Extract intake keyterms from PDF text with AI-first and local fallback behavior."""

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    try:
        from core.intake_parser import parse_intake_document

        intake = parse_intake_document("", extracted_text=text)
        if intake is None:
            from core.case_vocab import build_case_vocab_from_text

            fallback = build_case_vocab_from_text(text)
            _log(
                "Regex case-vocab fallback: "
                f"{fallback['counts'].get('People', 0)} people, "
                f"{fallback['counts'].get('Orgs', 0)} orgs, "
                f"{len(fallback['deepgram_keyterms'])} keyterms"
            )
            return list(fallback["deepgram_keyterms"])
        keyterms = list(intake.all_proper_nouns)
        reasons = intake.vocabulary_terms
        if reasons:
            preview = "; ".join(f"{item.term}: {item.reason}" for item in reasons[:5])
            _log(f"AI intake keyterms: {preview}")
        return keyterms
    except Exception as exc:
        _log(f"AI intake parse unavailable, falling back to regex extraction: {exc}")
        from core.case_vocab import build_case_vocab_from_text

        fallback = build_case_vocab_from_text(text)
        return list(fallback["deepgram_keyterms"])


# ── Step 0: Filename extraction ──────────────────────────────────────────────


def extract_from_filename(filename: str) -> dict:
    """
    Parse audio filename for witness name.
    Supported patterns:
      - MM-DD-YY FirstName LastName ChunkNumber.ext
      - YYYY-MM-DD- FirstName LastName suffix.ext
    Examples:
      - '03-24-26 Matthew Coger 01_1.wav'
      - '2026-04-09- Bianca Caram md.mp4'
    """
    import os

    name = os.path.splitext(os.path.basename(filename))[0]

    # Remove leading normalized_ prefix if present
    name = re.sub(r"^normalized_", "", name).strip()

    results = {
        "cause_number": (None, "failed"),
        "witness_last": (None, "failed"),
        "witness_first": (None, "failed"),
        "date": (None, "failed"),
        "scanned": False,
    }

    # Accept either legacy MM-DD-YY or modern YYYY-MM-DD prefixes.
    # The deposition date is not trusted here, but the date token is a reliable
    # anchor for extracting the first two name tokens that follow it.
    pattern = (
        r"^(?P<date>\d{2}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})"
        r"(?:\s*-\s*|\s+)"
        r"(?P<first>[A-Z][a-zA-Z\'-]+)"
        r"\s+"
        r"(?P<last>[A-Z][a-zA-Z\'-]+)"
        r"(?:\b.*)?$"
    )
    match = re.match(pattern, name)

    if match:
        raw_date = match.group("date")
        first_name = match.group("first")
        last_name = match.group("last")
        # NOTE: raw_date is intentionally not parsed into results["date"].
        # Deposition date must come from the uploaded NOD/PDF, never from
        # the audio filename.
        results["witness_first"] = (first_name, "filename")
        results["witness_last"] = (last_name, "filename")

    logger.info(
        "Filename extraction: %s -> %s",
        os.path.basename(filename),
        {k: v for k, v in results.items() if k != "scanned"},
    )
    return results


# ── Step 1: PDF text extraction ──────────────────────────────────────────────


def extract_pdf_text(filepath: str) -> str:
    """Extract text from pages 1-5 of a PDF using pdfplumber."""
    import pdfplumber

    text = ""
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages[:5]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def find_case_pdf(case_folder: str) -> str | None:
    """
    Look for the newest PDF in case_folder/source_docs/.
    """
    source_docs = os.path.join(case_folder, "source_docs")
    if not os.path.isdir(source_docs):
        return None

    pdfs = glob.glob(os.path.join(source_docs, "*.pdf"))
    return max(pdfs, key=os.path.getmtime) if pdfs else None


def find_reporter_notes(case_folder: str) -> str | None:
    """
    Look for a non-transcript .txt file in case_folder/source_docs/.
    """
    excluded = {
        "transcript.txt",
        "transcript_corrected.txt",
        "deepgram_raw_transcript.txt",
    }
    source_docs = os.path.join(case_folder, "source_docs")
    if not os.path.isdir(source_docs):
        return None

    txt_files = glob.glob(os.path.join(source_docs, "*.txt"))
    for filepath in sorted(txt_files, key=os.path.getmtime, reverse=True):
        if os.path.basename(filepath).lower() not in excluded:
            return filepath
    return None


# ── Step 2: Regex extraction ────────────────────────────────────────────────


def extract_cause_number(text: str) -> tuple[str | None, str]:
    """Extract cause/case number via regex. Returns (value, source)."""
    patterns = [
        r"Cause\s*No\.?\s*[:\-]?\s*([A-Z0-9\-]+)",
        r"Case\s*No\.?\s*[:\-]?\s*([A-Z0-9\-]+)",
        r"Docket\s*No\.?\s*[:\-]?\s*([A-Z0-9\-]+)",
        r"No\.\s*([A-Z0-9]{2,}\-[A-Z0-9\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(), "regex"
    return None, "failed"


# Honorifics and credential suffixes stripped from AI-extracted deponent
# names before splitting into first/last. The list is intentionally
# conservative: only tokens whose presence in a "last name" position is
# almost certainly an artefact of how the deponent was introduced
# (e.g. "Deposition of Alfred Karam, M.D.").
_HONORIFIC_SUFFIXES: frozenset[str] = frozenset({
    # Medical
    "md", "mds", "do", "dds", "dmd", "dvm", "dpm", "dpt", "od", "pa", "rn", "np",
    # Doctoral
    "phd", "edd", "psyd", "thd", "scd", "dsc", "drph",
    # Legal / accounting / business
    "esq", "jd", "llb", "llm", "cpa", "mba", "pe",
    # Mental health / counselling
    "lcsw", "lpc", "lmft", "lmhc", "mft",
    # Generational
    "jr", "sr", "ii", "iii", "iv", "v",
})


def _strip_name_token(token: str) -> str:
    """Return token lowercased with all interior and surrounding periods,
    commas, semicolons, colons, and whitespace removed.

    Strips interior punctuation too so 'M.D.' / 'Ph.D.' normalize to 'md'
    / 'phd' for honorific lookup. Without this, 'M.D.' would become 'm.d'
    after .strip() and miss the suffix set.
    """
    return token.translate({ord(c): None for c in " ,.;:"}).lower()


def split_witness_name(full_name: str) -> tuple[str | None, str | None]:
    """Split a deponent's full name into (first, last).

    Strips honorifics and credential suffixes from the trailing tokens
    before taking the surname. A token is treated as an honorific if its
    lowercase, punctuation-stripped form is in `_HONORIFIC_SUFFIXES`.

    Returns (None, None) if no two non-honorific tokens remain.

    Examples:
        "Alfred Karam, M.D."        -> ("Alfred", "Karam")
        "Alfred Karam M.D."         -> ("Alfred", "Karam")
        "ALFRED KARAM, MD"          -> ("ALFRED", "KARAM")
        "Jane Smith Jr."            -> ("Jane", "Smith")
        "Jane Smith Jr"             -> ("Jane", "Smith")
        "John Public"               -> ("John", "Public")
        "John Smith III, Esq."      -> ("John", "Smith")
        "Madonna"                   -> (None, None)
        "M.D."                      -> (None, None)
    """
    if not full_name:
        return (None, None)
    tokens = full_name.split()
    # Drop trailing honorifics. Iterate from the end and keep dropping
    # while the trailing token is an honorific.
    while tokens and _strip_name_token(tokens[-1]) in _HONORIFIC_SUFFIXES:
        tokens.pop()
    if len(tokens) < 2:
        return (None, None)
    # Strip a trailing comma from the surname token (e.g. "Karam,").
    last = tokens[-1].rstrip(",.")
    first = tokens[0].rstrip(",.")
    return (first or None, last or None)


def extract_witness_name(text: str) -> tuple[str | None, str]:
    """Extract witness last name via regex. Returns (value, source)."""
    patterns = [
        r"(?:Deposition|Testimony)\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"Witness[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"My\s+name\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"THE\s+WITNESS[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"[Dd]eposition\s+of\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            full_name = match.group(1).strip()
            _first, last_name = split_witness_name(full_name)
            if last_name:
                return last_name, "regex"
    return None, "failed"


def extract_date(text: str) -> tuple[str | None, str]:
    """Extract deposition date via regex. Returns (value, source)."""
    from dateutil import parser as dateparser

    patterns = [
        r"taken\s+on\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
        r"this\s+\d{1,2}(?:st|nd|rd|th)?\s+day\s+of\s+([A-Z][a-z]+,?\s+\d{4})",
        r"Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
        r"([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                parsed = dateparser.parse(match.group(1))
                if parsed:
                    return parsed.strftime("%m/%d/%Y"), "regex"
            except (ValueError, OverflowError):
                continue
    return None, "failed"


# ── Step 3: Claude API fallback ─────────────────────────────────────────────


def ai_extract_fields(text: str, missing_fields: list[str]) -> dict[str, Any]:
    """Call Claude API to extract fields that regex missed."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — cannot run AI extraction")
        return {}

    field_instructions = {
        "cause_number": "The case or cause number (e.g. 2024-CI-12345)",
        "witness_last": "The witness or deponent's last name only",
        "date": "The deposition date formatted as MM/DD/YYYY",
    }

    fields_needed = "\n".join(
        f'- "{k}": {field_instructions[k]}'
        for k in missing_fields
        if k in field_instructions
    )

    if not fields_needed:
        return {}

    prompt = (
        "You are a legal document parser. Extract the following fields "
        "from this deposition transcript text.\n\n"
        "Return ONLY a valid JSON object with these keys. "
        "If a field cannot be found, return null for that key. "
        "No explanation, no markdown.\n\n"
        f"Fields to extract:\n{fields_needed}\n\n"
        f"Document text:\n{text[:4000]}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=AI_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()
        # Strip markdown fences if present
        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
            response_text = re.sub(r"\s*```$", "", response_text)
        result = json.loads(response_text)
        logger.info("AI extraction returned: %s", result)
        return result
    except Exception as exc:
        logger.error("AI extraction failed: %s", exc)
        return {}


# ── Full pipeline ───────────────────────────────────────────────────────────


def extract_case_info_from_pdf(
    filepath: str,
    progress_callback=None,
) -> dict[str, Any]:
    """
    Hybrid extraction pipeline.
    Step 1: Regex for cause number, witness name, date.
    Step 2: parse_intake_document() for full structured extraction.
    """
    from core.intake_parser import parse_intake_document

    def log(msg: str):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    log(f"[PDFExtractor] Processing: {filepath}")
    text = extract_pdf_text(filepath)
    if len(text) < 50:
        log("[PDFExtractor] Scanned PDF  cannot extract.")
        return {"scanned": True}

    cause = extract_cause_number(text)
    witness = extract_witness_name(text)
    date = extract_date(text)
    witness_first: tuple[str | None, str] = (None, "failed")

    intake_result = parse_intake_document(
        filepath,
        progress_callback,
        extracted_text=text,
    )
    fallback_vocab = None
    if intake_result:
        if cause[1] == "failed" and intake_result.cause_number:
            cause = (intake_result.cause_number, "ai")

        if witness[1] == "failed":
            for deponent in intake_result.deponents:
                first, last = split_witness_name(str(deponent.get("name", "")))
                if first and last:
                    witness = (last, "ai")
                    witness_first = (first, "ai")
                    break

        if date[1] == "failed" and intake_result.deposition_date:
            try:
                from dateutil import parser as dp

                parsed_dt = dp.parse(intake_result.deposition_date)
                date = (parsed_dt.strftime("%m/%d/%Y"), "ai")
            except Exception:
                pass
    else:
        from core.case_vocab import build_case_vocab_from_text

        fallback_vocab = build_case_vocab_from_text(text)

    return {
        "cause_number": cause,
        "witness_last": witness,
        "witness_first": witness_first,
        "date": date,
        "keyterms": (
            intake_result.all_proper_nouns
            if intake_result
            else list((fallback_vocab or {}).get("deepgram_keyterms", []))
        ),
        "confirmed_spellings": (
            intake_result.confirmed_spellings
            if intake_result
            else dict((fallback_vocab or {}).get("confirmed_spellings", {}))
        ),
        "speaker_map_suggestion": (
            intake_result.speaker_map_suggestion
            if intake_result
            else dict((fallback_vocab or {}).get("speaker_map_suggestion", {}))
        ),
        "intake_entity_counts": (
            intake_result.entity_counts
            if intake_result
            else dict((fallback_vocab or {}).get("counts", {}))
        ),
        "intake_result": intake_result,
        "scanned": False,
    }
