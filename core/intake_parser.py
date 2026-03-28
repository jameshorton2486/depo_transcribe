"""
AI-assisted intake document parsing for case metadata and high-value keyterms.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app_logging import get_logger

logger = get_logger(__name__)

INTAKE_KEYTERM_LIMIT = 60

NOISE_WORDS = {
    "court", "texas", "plaintiff", "defendant", "notice", "deposition",
    "attorney", "firm", "march", "july", "february", "january", "april",
    "this", "your", "with", "please", "take", "pursuant", "telephone",
    "facsimile", "witness", "produce", "case", "appearance", "delivery",
    "signature", "parking", "interpreter", "original", "standard",
    "certificate", "district", "intention", "oral", "cause", "county",
    "austin", "bexar", "will", "david", "kathie", "love", "wright",
    "greenhill", "pllc", "william", "ordered", "odered", "deponent",
    "location", "date", "pages", "exhibit", "format", "rush", "due",
    "copy", "color", "video", "special", "instructions", "conference",
    "room", "trans", "hard", "notary", "public", "rules", "civil",
    "procedure", "respectfully", "submitted", "read", "sign", "start",
    "end", "time",
}

_SYSTEM_PROMPT = """
You are a legal transcript intake parser for a Texas court reporting firm.

Your job is to extract structured case data and a clean vocabulary list
from a Notice of Deposition or court reporting intake sheet.

Your output feeds directly into two downstream systems:
  1. Deepgram Nova-3 keyterms (hard cap: 100 terms total, 60 from intake)
  2. A transcript formatter substitution map

Low-quality terms waste cap slots and degrade transcription accuracy.
Be conservative. When in doubt, leave it out.

INCLUDE terms that meet ALL of these criteria:

  1. It is a proper noun or specialized term Deepgram is likely
     to mishear or misspell.
  2. It is not a standalone common English word.
  3. It cannot be reconstructed correctly from general knowledge.

Valid categories:
   Full personal names (first + last minimum)
   Company and law firm names (full legal name)
   Full street addresses (as a phrase, never as fragments)
   City + state combinations
   Cause numbers and court designations
   Case style in short form (Plaintiff v. Defendant)
   Trade names and legal product names
   Specialized legal or technical phrases (3+ words)

EXCLUDE never include any of the following:

   Standalone common words:
    Court, Texas, Plaintiff, Defendant, Notice, Deposition,
    Attorney, Firm, Witness, Case, Appearance, Delivery,
    Signature, Parking, Interpreter, Certificate, District,
    Intention, Oral, Cause, County, Bexar, Austin, March,
    July, February, This, Your, With, Please, Take, Pursuant,
    Telephone, Facsimile, Produce, Original, Standard

   Form field labels:
    Ordered By, Read & Sign, Start Time, End Time,
    Special Instructions, Conference Room, Trans Rush Due,
    Hard Copy, E-Trans, BW, Color, Pages, Exhibit Count,
    Deponent, Location, Date, Video, Format

   Address fragments without a full address context:
    "George Rd" alone, "Mueller Blvd" alone,
    "Cherry Ridge" alone, "Greenhill" alone

   Name fragments:
    "Wright" alone, "David" alone, "Kathie" alone,
    "Love" alone, "Allan" alone, "William" alone, "PLLC" alone

   OCR artifacts and misspellings; correct them first,
    then evaluate whether the corrected form qualifies.
    Example: "Odered" discard. "Mathew" correct to
    "Matthew Coger" and include as the full name.

DEDUPLICATION RULES:

   Always prefer the longest, most complete version of a name.
   If "Will Allan Law Firm PLLC" is included, do not also
    include "Will Allan Firm", "Will Allan", or "PLLC".
   If a full address is included, do not also include the
    street name fragment.
   Short-form names are only acceptable if they are
    phonetically distinct from the full form AND are likely
    to appear spoken that way in the transcript.
   Always correct spelling before including.
    "Mathew" to "Matthew". Include corrected form only.

OUTPUT FORMAT:

Return ONLY valid JSON. No preamble, no explanation, no markdown fences.

{
  "causeNumber": "string | null",
  "court": "string | null",
  "caseStyle": "string | null",
  "depositionDate": "string | null",
  "deponents": [
    { "name": "string", "role": "string" }
  ],
  "plaintiffs": ["string"],
  "defendants": ["string"],
  "orderingAttorney": {
    "name": "string",
    "firm": "string",
    "address": "string",
    "phone": "string",
    "email": "string"
  },
  "copyAttorneys": [
    {
      "name": "string",
      "firm": "string",
      "address": "string",
      "email": "string"
    }
  ],
  "keyterms": [
    {
      "term": "string",
      "term_type": "PERSON | COMPANY | LOCATION | LEGAL | TECHNICAL | CUSTOM",
      "reason": "One sentence justifying why this term qualifies."
    }
  ],
  "allProperNouns": ["string"]
}

FIELD NOTES:
   "reason" is for internal logging only, never shown to the user.
    Its purpose is to force self-justification and prevent noise
    terms from being included without a valid rationale.
   "allProperNouns" is a flat deduplicated list of term strings only.
    Maximum 60 entries. The remaining 40 slots under Nova-3's 100-term
    cap are reserved for firm-level and court-reporter vocabulary.
   "keyterms" and "allProperNouns" must be consistent; every term
    in "allProperNouns" must also appear in "keyterms".
""".strip()


def _strip_markdown_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _empty_result() -> dict[str, Any]:
    return {
        "causeNumber": None,
        "court": None,
        "caseStyle": None,
        "depositionDate": None,
        "deponents": [],
        "plaintiffs": [],
        "defendants": [],
        "orderingAttorney": {
            "name": "",
            "firm": "",
            "address": "",
            "phone": "",
            "email": "",
        },
        "copyAttorneys": [],
        "keyterms": [],
        "allProperNouns": [],
    }


def filter_keyterms(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for term in raw:
        t = " ".join((term or "").strip().split())
        if len(t) <= 3:
            continue
        if t.isdigit():
            continue
        if " " not in t and not (t[0].isupper() or re.search(r"[A-Za-z]", t)):
            continue
        if t.lower() in NOISE_WORDS:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(t)

    return result[:INTAKE_KEYTERM_LIMIT]


def _normalise_ai_result(data: dict[str, Any]) -> dict[str, Any]:
    result = _empty_result()
    result.update({k: v for k, v in data.items() if k in result})

    raw_keyterms = data.get("keyterms", []) or []
    kept_terms = filter_keyterms(
        [item.get("term", "") for item in raw_keyterms if isinstance(item, dict)]
    )[:INTAKE_KEYTERM_LIMIT]
    kept_lookup = {term.lower() for term in kept_terms}

    result["keyterms"] = [
        {
            "term": item.get("term", "").strip(),
            "term_type": item.get("term_type", "CUSTOM"),
            "reason": item.get("reason", "").strip(),
        }
        for item in raw_keyterms
        if isinstance(item, dict)
        and item.get("term", "").strip().lower() in kept_lookup
    ]

    # Reorder keyterms to match the filtered flat list.
    by_term = {item["term"].lower(): item for item in result["keyterms"]}
    result["keyterms"] = [by_term[term.lower()] for term in kept_terms if term.lower() in by_term]
    result["allProperNouns"] = kept_terms
    return result


def parse_intake_document(text: str) -> dict[str, Any]:
    """
    Parse intake text with Anthropic and return a filtered structured result.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set.")

    try:
        import anthropic
    except ImportError as exc:
        raise ImportError("anthropic is not installed.") from exc

    prompt = (
        "Parse the following intake document and return the structured JSON "
        "described above. Be conservative; when in doubt about whether a "
        "term qualifies, leave it out.\n\n"
        f"{text[:16000]}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2400,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = _strip_markdown_fences(message.content[0].text)
    payload = json.loads(response_text)
    result = _normalise_ai_result(payload)
    logger.info(
        "Intake parse complete cause=%s keyterms=%s",
        result.get("causeNumber"),
        len(result.get("allProperNouns", [])),
    )
    return result
