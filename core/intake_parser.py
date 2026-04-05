"""
AI-assisted intake parsing with typed results and conservative keyterm filtering.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app_logging import get_logger
from core.config import AI_MODEL, MAX_KEYTERMS

logger = get_logger(__name__)

VALID_TERM_TYPES = {
    "PERSON",
    "COMPANY",
    "LOCATION",
    "LEGAL",
    "TECHNICAL",
    "CUSTOM",
}


@dataclass
class VocabularyTerm:
    term: str
    term_type: str
    field_name: str
    reason: str


@dataclass
class IntakeParsedResult:
    cause_number: Optional[str]
    court: Optional[str]
    case_style: Optional[str]
    deposition_date: Optional[str]
    deposition_method: Optional[str]
    subpoena_duces_tecum: bool
    read_and_sign: bool
    signature_waived: bool
    video_recorded: bool
    plaintiffs: list[str]
    defendants: list[str]
    deponents: list[dict]
    ordering_attorney: dict
    filing_attorney: dict = field(default_factory=dict)
    copy_attorneys: list[dict] = field(default_factory=list)
    ordered_by: Optional[str] = None
    amendment: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_csr: Optional[str] = None
    reporter_firm: Optional[str] = None
    reporter_address: Optional[str] = None
    vocabulary_terms: list[VocabularyTerm] = field(default_factory=list)
    all_proper_nouns: list[str] = field(default_factory=list)
    confirmed_spellings: dict[str, str] = field(default_factory=dict)
    term_count: int = 0
    parse_method: str = "ai"


STANDARD_LEGAL_SPELLINGS: dict[str, str] = {
    "Injection form": "Objection.  Form.",
    "Infection": "Objection.",
    "Protection": "Objection.",
    "Perfection": "Objection.",
    "Detection": "Objection.",
    "Eviction": "Objection.",
    "Definition": "Objection.",
    "Direction form": "Objection.  Form.",
    "Bleeding": "Leading.",
    "Leaving": "Leading.",
    "Warm, leading": "Leading.",
    "Former leaving": "Form and leading.",
    "Form and leaving": "Form and leading.",
    "Form and legal": "Form and leading.",
    "Past witness": "Pass the witness.",
    "Pastor witness": "Pass the witness.",
    "so many sorts": "solemnly swear to",
    "remotes wearing": "remote swearing of",
    "mister": "Mr.",
    "miss ": "Miss ",
    "Elma": "Elmo",
    "any exerts": "any exhibits",
    "cop number": "Cause Number",
    "cost number": "Cause Number",
}

INTAKE_PARSER_SYSTEM_PROMPT = """
You are a Texas court reporter intake processor for SA Legal Solutions.
You are extracting structured data from a court reporting intake packet.

These packets often contain multiple document types in one PDF:
  - SA Legal Solutions intake / scheduling sheet
  - Notice of Deposition
  - Notice of Deposition Duces Tecum
  - Certificate of Service

Your job is to read the ENTIRE packet, recognize which sections exist,
and extract only the structured data needed for scheduling, transcript
setup, confirmed spellings, and Deepgram keyterms.

SOURCE PRIORITY
When the same fact appears in both the intake sheet and the legal pleading:
  1. Prefer the Notice of Deposition body and caption for legal case data.
  2. Prefer the intake sheet for scheduling/admin data such as ordered_by.
  3. If intake sheet and NOD conflict on attorneys, keep BOTH when they
     represent different roles (ordering attorney vs filing attorney).

SECTION RECOGNITION
Before extracting values, identify which pages/sections exist:
  - Intake / scheduling sheet
  - Notice of Deposition
  - Duces Tecum
  - Certificate of Service

Ignore Certificate of Service for structured extraction.
If Duces Tecum exists, extract only the duces tecum flag and the phrase
"Subpoena Duces Tecum" as a potential keyterm. Ignore the duces tecum body text.

ROBUSTNESS RULES
  - Cause number formats vary by county. Capture exactly as written.
  - Rejoin OCR split names across line breaks, especially suffixes like
    "Jr.", "Sr.", "III", and "IV".
  - A copy attorney may appear only in the NOD body and not on the intake sheet.
  - Ordering attorney may differ from the filing/signing attorney. Keep both.
  - Prefer full firm names including suffixes such as PLLC, P.C., LLC, LLP.
  - If the NOD title includes "First Amended", "Second Amended",
    "Third Amended", etc., capture that in amendment.

FIELDS TO EXTRACT
  cause_number: exact string as written
  court: full court caption string from the NOD caption
  case_style: full plaintiff v. defendant style
  deposition_date: as written in the NOD or scheduling sheet
  deposition_method: one of "In Person", "Via Zoom", "Via Teams", "Telephonic", or null
  subpoena_duces_tecum: true if the packet is a duces tecum notice, else false
  amendment: amendment title string or null
  read_and_sign: true/false if explicitly stated
  signature_waived: true/false if explicitly stated
  video_recorded: true/false if explicitly stated
  plaintiffs: array of plaintiff names from the case caption
  defendants: array of defendant names from the case caption
  deponents: array with at least one object when the deponent is identifiable
  ordering_attorney: attorney on the intake sheet ordering field
  filing_attorney: attorney who signed the NOD or appears in the signature block
  copy_attorneys: pull from BOTH the intake sheet and NOD copy/to/by-and-through sections
  ordered_by: the contact/person from the "Ordered by" or OCR variant "Odered by" field
  reporter_name / reporter_csr / reporter_firm / reporter_address: reporter data when present

DEEPGRAM KEYTERM RULES
Deepgram keyterms must be selective and case-specific.
Include a term only if all are true:
  1. It appears in this packet.
  2. It is a proper noun, firm name, cause number, or specialized phrase
     that speech-to-text could plausibly mishear.
  3. It is a full name/phrase, not a fragment.

Always include when present:
  - every full person name
  - every full law firm name with suffix
  - the reporter firm name
  - the cause number
  - ordered_by contact
  - "Subpoena Duces Tecum" when subpoena_duces_tecum is true

Never include:
  - certificate of service text
  - duces tecum boilerplate requests/body text
  - form labels or headers
  - common English words
  - address fragments
  - state abbreviations by themselves

Return at most 20 keyterms. Drop the least case-specific terms first.

CONFIRMED SPELLINGS
Generate confirmed_spellings for names/entities with real mishearing risk.
Cover patterns like:
  - phonetic surname mishears
  - suffix variations (Jr./Sr.)
  - hyphen-loss variants
  - firm name without legal suffix when the full firm is present
Do not pad with obvious or pointless variations.

OUTPUT FORMAT
Return ONLY valid JSON. No markdown, no explanation.

{
  "cause_number": "string or null",
  "court": "string or null",
  "case_style": "string or null",
  "deposition_date": "string or null",
  "deposition_method": "In Person | Via Zoom | Via Teams | Telephonic | null",
  "subpoena_duces_tecum": true,
  "amendment": "string or null",
  "read_and_sign": true,
  "signature_waived": false,
  "video_recorded": false,
  "plaintiffs": ["string"],
  "defendants": ["string"],
  "deponents": [{"name": "string", "role": "string"}],
  "ordering_attorney": {
    "name": "string or null",
    "firm": "string or null",
    "address": "string or null",
    "phone": "string or null",
    "email": "string or null"
  },
  "filing_attorney": {
    "name": "string or null",
    "firm": "string or null",
    "address": "string or null",
    "phone": "string or null",
    "email": "string or null"
  },
  "copy_attorneys": [{
    "name": "string or null",
    "firm": "string or null",
    "address": "string or null",
    "email": "string or null"
  }],
  "ordered_by": "string or null",
  "reporter_name": "string or null",
  "reporter_csr": "string or null",
  "reporter_firm": "string or null",
  "reporter_address": "string or null",
  "vocabulary_terms": [
    {
      "term": "exact string to send to Deepgram",
      "term_type": "PERSON|COMPANY|LOCATION|LEGAL|TECHNICAL|CUSTOM",
      "field_name": "internal label",
      "reason": "one sentence"
    }
  ],
  "all_proper_nouns": ["flat deduplicated array of term strings"],
  "confirmed_spellings": {
    "deepgram_wrong_form": "correct_form"
  }
}
""".strip()


def INTAKE_PARSER_USER_PROMPT(text: str) -> str:
    return (
        "Parse the following Texas court reporting intake packet.\n"
        "Recognize the packet sections first, then extract structured data.\n"
        "Prefer the NOD body for legal case facts and the intake sheet for administrative fields.\n"
        "Be conservative with keyterms and ignore certificate-of-service text.\n\n"
        f"{text}"
    )


NOISE_WORDS = {
    "court", "texas", "plaintiff", "defendant", "notice",
    "deposition", "attorney", "firm", "march", "july",
    "february", "january", "april", "may", "june", "august",
    "september", "october", "november", "december", "this",
    "your", "with", "please", "take", "pursuant", "telephone",
    "facsimile", "witness", "produce", "case", "appearance",
    "delivery", "signature", "parking", "interpreter",
    "original", "standard", "certificate", "district",
    "intention", "oral", "cause", "county", "austin", "bexar",
    "will", "david", "kathie", "love", "wright", "greenhill",
    "pllc", "william", "ordered", "odered", "deponent",
    "location", "date", "pages", "exhibit", "format", "rush",
    "due", "copy", "color", "video", "special", "instructions",
    "conference", "room", "trans", "hard", "notary", "public",
    "rules", "civil", "procedure", "respectfully", "submitted",
}


def _strip_markdown_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def hard_filter_keyterms(raw: list[str]) -> list[str]:
    """
    Post-AI safety filter. Runs on all_proper_nouns before storing to job
    config or sending to Deepgram. Cap: MAX_KEYTERMS.
    """
    seen: set[str] = set()
    result: list[str] = []

    for term in raw:
        t = " ".join((term or "").strip().split())
        if len(t) < 4:
            continue
        words = t.split()
        has_alpha = any(ch.isalpha() for ch in t)
        has_digit = any(ch.isdigit() for ch in t)
        if len(words) == 1 and not (t[0].isupper() or (has_alpha and has_digit)):
            continue
        if t.lower() in NOISE_WORDS:
            continue
        if t.isdigit():
            continue
        if t.isupper() and len(words) == 1 and has_alpha and not has_digit:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(t)

    return result[:MAX_KEYTERMS]


def filter_keyterms(raw: list[str]) -> list[str]:
    """Backward-compatible alias for older pure-function tests/callers."""
    return hard_filter_keyterms(raw)


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_list_of_dict(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _coerce_deponents(data: dict[str, Any]) -> list[dict]:
    deponents = _coerce_list_of_dict(data.get("deponents"))
    if deponents:
        return deponents

    singular = _coerce_str(data.get("deponent"))
    if singular:
        return [{"name": singular, "role": "deponent"}]
    return []


def _coerce_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _normalize_confirmed_spellings(
    ai_spellings: dict[str, str],
    filtered_terms: list[str],
) -> dict[str, str]:
    """
    Merge AI-provided spelling corrections with the standard legal map and
    canonicalize correction targets against extracted proper nouns.
    """
    canonical_terms = {
        " ".join(term.split()).strip().lower(): " ".join(term.split()).strip()
        for term in filtered_terms
        if " ".join(term.split()).strip()
    }
    merged = dict(STANDARD_LEGAL_SPELLINGS)

    for wrong, correct in ai_spellings.items():
        wrong_text = " ".join(str(wrong).split()).strip()
        correct_text = " ".join(str(correct).split()).strip()
        if not wrong_text or not correct_text:
            continue
        canonical_correct = canonical_terms.get(correct_text.lower(), correct_text)
        merged[wrong_text] = canonical_correct

    return merged


def _build_vocabulary_terms(data: dict[str, Any], filtered_terms: list[str]) -> list[VocabularyTerm]:
    filtered_lookup = {term.lower() for term in filtered_terms}
    result: list[VocabularyTerm] = []

    for item in data.get("vocabulary_terms", []):
        if not isinstance(item, dict):
            continue
        term = " ".join(str(item.get("term", "")).split()).strip()
        if not term or term.lower() not in filtered_lookup:
            continue
        term_type = str(item.get("term_type", "CUSTOM")).strip() or "CUSTOM"
        if term_type not in VALID_TERM_TYPES:
            term_type = "CUSTOM"
        result.append(
            VocabularyTerm(
                term=term,
                term_type=term_type,
                field_name=str(item.get("field_name", "")).strip(),
                reason=str(item.get("reason", "")).strip(),
            )
        )

    return result


def parse_intake_document(
    filepath: str,
    progress_callback=None,
    extracted_text: str | None = None,
) -> IntakeParsedResult | None:
    """
    Main entry point. Accepts a PDF filepath and returns a typed parse result.
    If extracted_text is provided, it is used directly and the PDF is not re-read.
    """

    def log(msg: str):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    if extracted_text is not None:
        log("[IntakeParser] Using pre-extracted text")
        text = extracted_text.strip()
        text = re.sub(r",\s*\n\s*(Jr\.?|Sr\.?|III|IV)\b", r", \1", text)
    else:
        log(f"[IntakeParser] Reading PDF: {filepath}")
        try:
            import pdfplumber

            text_parts: list[str] = []
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        text_parts.append(page_text)
            text = "\n\n".join(text_parts).strip()
            text = re.sub(r",\s*\n\s*(Jr\.?|Sr\.?|III|IV)\b", r", \1", text)
        except Exception as exc:
            logger.error("[IntakeParser] PDF read failed: %s", exc)
            return None

    if len(text) < 50:
        log("[IntakeParser] PDF appears to be scanned  AI extraction skipped.")
        return None

    log("[IntakeParser] Calling Claude API for intelligent extraction...")
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "").strip())
        message = client.messages.create(
            model=AI_MODEL,
            max_tokens=4096,
            system=INTAKE_PARSER_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": INTAKE_PARSER_USER_PROMPT(text[:16000]),
            }],
        )
        raw_json = _strip_markdown_fences(message.content[0].text.strip())
    except Exception as exc:
        logger.error("[IntakeParser] Claude API call failed: %s", exc)
        return None

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.error("[IntakeParser] JSON parse failed: %s", exc)
        logger.debug("[IntakeParser] Raw response: %s", raw_json[:500])
        return None

    raw_terms = data.get("all_proper_nouns", [])
    filtered_terms = hard_filter_keyterms(raw_terms if isinstance(raw_terms, list) else [])
    log(
        f"[IntakeParser] Terms: {len(raw_terms) if isinstance(raw_terms, list) else 0} raw  "
        f"{len(filtered_terms)} after filter"
    )
    if filtered_terms:
        log(f"[IntakeParser] Keyterm preview: {filtered_terms[:10]}")
    if len(filtered_terms) > 40:
        logger.warning(
            "[IntakeParser] %s terms  approaching %s-term intake cap",
            len(filtered_terms),
            MAX_KEYTERMS,
        )

    vocabulary_terms = _build_vocabulary_terms(data, filtered_terms)
    ai_spellings = _coerce_dict(data.get("confirmed_spellings"))
    final_spellings = _normalize_confirmed_spellings(ai_spellings, filtered_terms)
    if final_spellings:
        preview_items = list(final_spellings.items())[:10]
        log(f"[IntakeParser] Confirmed spellings preview: {preview_items}")

    result = IntakeParsedResult(
        cause_number=_coerce_str(data.get("cause_number")),
        court=_coerce_str(data.get("court")),
        case_style=_coerce_str(data.get("case_style")),
        deposition_date=_coerce_str(data.get("deposition_date")),
        deposition_method=_coerce_str(data.get("deposition_method")),
        subpoena_duces_tecum=bool(data.get("subpoena_duces_tecum", False)),
        read_and_sign=bool(data.get("read_and_sign", False)),
        signature_waived=bool(data.get("signature_waived", False)),
        video_recorded=bool(data.get("video_recorded", False)),
        plaintiffs=_coerce_list_of_str(data.get("plaintiffs")),
        defendants=_coerce_list_of_str(data.get("defendants")),
        deponents=_coerce_deponents(data),
        ordering_attorney=_coerce_dict(data.get("ordering_attorney")),
        filing_attorney=_coerce_dict(data.get("filing_attorney")),
        copy_attorneys=_coerce_list_of_dict(data.get("copy_attorneys")),
        ordered_by=_coerce_str(data.get("ordered_by")),
        amendment=_coerce_str(data.get("amendment")),
        reporter_name=_coerce_str(data.get("reporter_name")),
        reporter_csr=_coerce_str(data.get("reporter_csr")),
        reporter_firm=_coerce_str(data.get("reporter_firm")),
        reporter_address=_coerce_str(data.get("reporter_address")),
        vocabulary_terms=vocabulary_terms,
        all_proper_nouns=filtered_terms,
        confirmed_spellings=final_spellings,
        term_count=len(filtered_terms),
        parse_method="ai",
    )
    log(
        f"[IntakeParser] Complete  {len(filtered_terms)} keyterms, "
        f"{len(final_spellings)} spelling corrections"
    )
    return result
