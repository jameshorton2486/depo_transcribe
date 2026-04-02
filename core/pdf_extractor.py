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
            return []
        keyterms = list(intake.all_proper_nouns)
        reasons = intake.vocabulary_terms
        if reasons:
            preview = "; ".join(
                f"{item.term}: {item.reason}"
                for item in reasons[:5]
            )
            _log(f"AI intake keyterms: {preview}")
        return keyterms
    except Exception as exc:
        _log(f"AI intake parse unavailable, falling back to regex extraction: {exc}")
        from core.keyterm_extractor import clean_keyterms, extract_keyterms_from_text

        raw_candidates = re.findall(
            r"\b[A-Z][a-zA-Z]{1,}\b(?:\s+[A-Z][a-zA-Z]{1,}\b)*",
            text,
        )
        raw_candidates.extend(extract_keyterms_from_text(text))
        return clean_keyterms(raw_candidates)


# ── Step 0: Filename extraction ──────────────────────────────────────────────

def extract_from_filename(filename: str) -> dict:
    """
    Parse audio filename for witness name.
    Expected pattern: MM-DD-YY FirstName LastName ChunkNumber.ext
    e.g. '03-24-26 Matthew Coger 01_1.wav'
    """
    import os

    name = os.path.splitext(os.path.basename(filename))[0]

    # Remove leading normalized_ prefix if present
    name = re.sub(r'^normalized_', '', name).strip()

    results = {
        "cause_number": (None, "failed"),
        "witness_last": (None, "failed"),
        "witness_first": (None, "failed"),
        "date": (None, "failed"),
        "scanned": False,
    }

    # Match: MM-DD-YY FirstName LastName ChunkInfo
    pattern = r'^(\d{2}-\d{2}-\d{2})\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)'
    match = re.match(pattern, name)

    if match:
        raw_date, first_name, last_name = match.groups()
        # NOTE: raw_date is intentionally not parsed into results["date"].
        # Deposition date must come from the uploaded NOD/PDF, never from
        # the audio filename.
        results["witness_first"] = (first_name, "filename")
        results["witness_last"] = (last_name, "filename")

    logger.info("Filename extraction: %s -> %s",
                os.path.basename(filename),
                {k: v for k, v in results.items() if k != "scanned"})
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
        r'Cause\s*No\.?\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'Case\s*No\.?\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'Docket\s*No\.?\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'No\.\s*([A-Z0-9]{2,}\-[A-Z0-9\-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(), "regex"
    return None, "failed"


def extract_witness_name(text: str) -> tuple[str | None, str]:
    """Extract witness last name via regex. Returns (value, source)."""
    patterns = [
        r'(?:Deposition|Testimony)\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        r'Witness[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        r'My\s+name\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        r'THE\s+WITNESS[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        r'[Dd]eposition\s+of\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            full_name = match.group(1).strip()
            last_name = full_name.split()[-1]
            return last_name, "regex"
    return None, "failed"


def extract_date(text: str) -> tuple[str | None, str]:
    """Extract deposition date via regex. Returns (value, source)."""
    from dateutil import parser as dateparser

    patterns = [
        r'taken\s+on\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
        r'this\s+\d{1,2}(?:st|nd|rd|th)?\s+day\s+of\s+([A-Z][a-z]+,?\s+\d{4})',
        r'Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
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
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
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
    if intake_result:
        if cause[1] == "failed" and intake_result.cause_number:
            cause = (intake_result.cause_number, "ai")

        if witness[1] == "failed":
            for deponent in intake_result.deponents:
                name_parts = str(deponent.get("name", "")).split()
                if len(name_parts) >= 2:
                    witness = (name_parts[-1], "ai")
                    witness_first = (name_parts[0], "ai")
                    break

        if date[1] == "failed" and intake_result.deposition_date:
            try:
                from dateutil import parser as dp

                parsed_dt = dp.parse(intake_result.deposition_date)
                date = (parsed_dt.strftime("%m/%d/%Y"), "ai")
            except Exception:
                pass

    return {
        "cause_number": cause,
        "witness_last": witness,
        "witness_first": witness_first,
        "date": date,
        "keyterms": intake_result.all_proper_nouns if intake_result else [],
        "confirmed_spellings": intake_result.confirmed_spellings if intake_result else {},
        "intake_result": intake_result,
        "scanned": False,
    }
