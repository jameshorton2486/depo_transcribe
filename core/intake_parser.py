"""
AI-assisted intake parsing with typed results and conservative keyterm filtering.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from app_logging import get_logger

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
    copy_attorneys: list[dict]
    reporter_name: Optional[str]
    reporter_csr: Optional[str]
    reporter_firm: Optional[str]
    reporter_address: Optional[str]
    vocabulary_terms: list[VocabularyTerm]
    all_proper_nouns: list[str]
    confirmed_spellings: dict[str, str]
    term_count: int
    parse_method: str


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
You are a legal transcript intake parser for a Texas court reporting firm.
Your job is to extract structured data and vocabulary keyterms from a
court reporting intake sheet and/or Notice of Deposition PDF.

You must be highly selective. The output feeds Deepgram Nova-3 (100-term
hard cap) and a transcript formatter substitution pipeline. Garbage terms
waste cap slots and degrade transcription accuracy.


WHAT TO INCLUDE  qualify each term against ALL criteria

Include a term ONLY if ALL of the following are true:
  1. It is a proper noun, specialized phrase, or technical term
     that a speech-to-text model is likely to mishear or misspell.
  2. It has at least two words OR is a single proper noun of 5+
     characters not in a standard dictionary.
  3. A court reporter who has not read the case file would benefit
     from having this term boosted in the transcript.

VALID term_type categories:
  PERSON     Full names (first + last minimum). Include a short form
              ONLY if phonetically distinct from the full form.
  COMPANY    Full legal entity names including suffix
              (PLLC, P.C., LLC, Inc., LLP, LC).
  LOCATION   Full addresses as phrases (never fragments).
              City + state. County + state. Named incident sites.
  LEGAL      Multi-word legal phrases specific to this case type.
              e.g. "Subpoena Duces Tecum", "slip and fall",
              "dangerous condition", "premises liability".
  TECHNICAL  Product names, equipment, Bates prefixes, exhibit
              labels, document section headings, case-specific
              identifiers referenced in testimony.
  CUSTOM     Cause numbers, incident identifiers, exhibit numbers
              (e.g. "Exhibit 17", "Murphy 095") that appear verbatim.


WHAT TO EXCLUDE  always excluded without exception

NEVER include:
  - Single common English words even if capitalized:
    Court, Texas, Plaintiff, Defendant, Notice, Deposition,
    Attorney, Firm, March, July, February, January, This,
    Your, With, Please, Take, Pursuant, Telephone, Facsimile,
    Witness, Produce, Case, Appearance, Delivery, Signature,
    Parking, Interpreter, Original, Standard, Certificate,
    District, Intention, Oral, Cause, County, Austin, Bexar,
    Will, David, Kathie, Love, Wright, Greenhill, PLLC, William.
  - Intake form labels and field headers:
    "Ordered by", "Read & Sign", "Start Time", "End Time",
    "Special Instructions", "Conference Room", "Trans Rush Due",
    "Hard Copy", "E-Trans", "BW", "Color", "Pages",
    "Exhibit Count", "Deponent", "Location", "Date",
    "Video/Med/Tech", "Appearance", "CNA", "Odered".
  - Address or name fragments where a complete form is included:
    Do not include "Wright" if "Wright and Greenhill P.C." exists.
    Do not include "George Rd" if the full address is included.
    Do not include "Allan" if "William N. Allan IV" is included.
  - OCR typos  correct them first, then evaluate.
    "Mathew"  correct to "Matthew" then include as full name.
    "Odered"  discard entirely.
  - Duplicates of any term already in a more complete form.
  - Any term you cannot justify with a single confident reason.


DEDUPLICATION RULES

  - Prefer the most complete, correctly spelled version.
  - Include a short name form only if phonetically distinct.
  - Do not include firm name without legal suffix if full form exists.
  - Correct spelling silently before including.
  - all_proper_nouns must be deduplicated  no term appears twice.
  - all_proper_nouns must not exceed 60 entries.


CONFIRMED SPELLINGS

Generate a confirmed_spellings map of likely Deepgram mishearings
 correct forms based on the names and entities you extract.
Standard patterns to cover:
  - Name variants: "Will Allen"  "Will Allan"
  - Company garbles: "Murphy USAA"  "Murphy USA"
  - Product mishearings: case-specific product names
  - Counsel name garbles based on phonetics of extracted names


OUTPUT FORMAT

Return ONLY valid JSON. No preamble, no markdown, no explanation.

{
  "cause_number": "string or null",
  "court": "string or null",
  "case_style": "string or null",
  "deposition_date": "string or null",
  "deposition_method": "In Person | Via Zoom | Via Teams | null",
  "subpoena_duces_tecum": true | false,
  "read_and_sign": true | false,
  "signature_waived": true | false,
  "video_recorded": true | false,
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
  "copy_attorneys": [{
    "name": "string or null",
    "firm": "string or null",
    "address": "string or null",
    "email": "string or null"
  }],
  "reporter_name": "string or null",
  "reporter_csr": "string or null",
  "reporter_firm": "string or null",
  "reporter_address": "string or null",
  "vocabulary_terms": [
    {
      "term": "exact string to send to Deepgram",
      "term_type": "PERSON|COMPANY|LOCATION|LEGAL|TECHNICAL|CUSTOM",
      "field_name": "internal label e.g. plaintiff_counsel[0].name",
      "reason": "one sentence explaining why Deepgram needs this boosted"
    }
  ],
  "all_proper_nouns": ["flat deduplicated array of term strings  max 60"],
  "confirmed_spellings": {
    "deepgram_wrong_form": "correct_form"
  }
}

The reason field is internal logging only  never shown to users.
It forces careful justification of each term included.
""".strip()


def INTAKE_PARSER_USER_PROMPT(text: str) -> str:
    return (
        "Parse the following court reporting intake document.\n"
        "Apply all extraction and exclusion rules strictly.\n"
        "Be conservative  when in doubt, leave it out.\n\n"
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
    config or sending to Deepgram. Cap: 60 terms.
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

    return result[:60]


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


def _coerce_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


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
) -> IntakeParsedResult | None:
    """
    Main entry point. Accepts a PDF filepath and returns a typed parse result.
    """

    def log(msg: str):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    log(f"[IntakeParser] Reading PDF: {filepath}")
    try:
        import pdfplumber

        text = ""
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages[:5]:
                text += page.extract_text() or ""
        text = text.strip()
    except Exception as exc:
        logger.error("[IntakeParser] PDF read failed: %s", exc)
        return None

    if len(text) < 50:
        log("[IntakeParser] PDF appears to be scanned  AI extraction skipped.")
        return None

    log("[IntakeParser] Calling Claude API for intelligent extraction...")
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=INTAKE_PARSER_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": INTAKE_PARSER_USER_PROMPT(text[:8000]),
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
    if len(filtered_terms) > 40:
        logger.warning(
            "[IntakeParser] %s terms  approaching 60-term intake cap",
            len(filtered_terms),
        )

    vocabulary_terms = _build_vocabulary_terms(data, filtered_terms)
    ai_spellings = _coerce_dict(data.get("confirmed_spellings"))
    final_spellings = {
        **STANDARD_LEGAL_SPELLINGS,
        **{str(k): str(v) for k, v in ai_spellings.items()},
    }

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
        deponents=_coerce_list_of_dict(data.get("deponents")),
        ordering_attorney=_coerce_dict(data.get("ordering_attorney")),
        copy_attorneys=_coerce_list_of_dict(data.get("copy_attorneys")),
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
