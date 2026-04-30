"""
Helpers for cleaning, prioritizing, and merging Deepgram keyterms.
"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING

from app_logging import get_logger
from core.config import MAX_KEYTERMS, MIN_TERM_LENGTH

logger = get_logger(__name__)

if TYPE_CHECKING:
    from core.intake_parser import IntakeParsedResult

MULTIWORD_FIXES = {
    "subpoena deuces tecum": "subpoena duces tecum",
}

STRUCTURE_BLACKLIST = {
    "district court",
    "court reporter",
    "the witness",
    "the reporter",
    "special instructions",
    "ordered by",
    "start time",
    "end time",
    "read and sign",
}

LEGAL_PHRASES = (
    "subpoena duces tecum",
    "duces tecum",
)

NAME_PATTERN = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+(?:\s+(?:Jr|Sr|III))?\b"
)
CASE_NUMBER_PATTERN = re.compile(r"\b[Cc]-?\d{4,}-\d{2}-[A-Z]\b")
FIRM_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z&., ]+(?:PLLC|LLP|LLC|P\.C\.|PC|Firm|Offices)\b"
)
ADDRESS_PATTERN = re.compile(
    r"\b\d{3,5}\s+[A-Za-z0-9.\- ]+?"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Suite|Ste|Place|Pl|Expressway|Blvd)\b"
    r"(?:[^,\n]*)(?:,\s*[A-Za-z.\- ]+)*(?:\s+\d{5}(?:-\d{4})?)?",
    re.IGNORECASE,
)

SKIP_WORDS = {
    "the", "of", "and", "or", "a", "an", "in", "at", "by", "to",
    "for", "with", "this", "that", "is", "are", "was", "be",
    "suite", "ste", "blvd", "rd", "hwy", "st", "ave", "dr",
    "tx", "texas", "san", "floor", "building",
    "200", "300", "400", "100",
}

STOPWORDS = {
    "a", "an", "the", "and", "or", "if", "by", "to", "of", "in",
    "for", "on", "at", "is", "it", "be", "as", "so", "we", "he",
    "she", "do", "no", "yes", "you", "via", "vs", "rep", "copy",
    "notes", "pages", "phone", "email", "fax", "date", "time",
    "style", "format", "sign", "read", "send", "state", "suite",
    "ste", "route", "rule", "tech", "med", "lc", "bw", "cr", "tx",
    "civ", "csr", "llc", "lp", "am", "pm", "end", "start", "any",
    "hard", "soft", "color", "building", "loop", "address", "location",
    "zoom", "video", "audio", "ordered", "ordering", "travel", "miles",
    "exhibit", "count", "start time", "end time", "send to",
    "service email", "zoom date",
}

BOUNDARY_NOISE_WORDS = {
    "a", "an", "the", "and", "or", "if", "by", "to", "of", "in",
    "for", "on", "at", "is", "it", "be", "as", "so", "we", "he",
    "she", "do", "no", "yes", "you", "via", "vs", "rep", "copy",
    "notes", "pages", "phone", "email", "fax", "date", "time",
    "style", "format", "sign", "read", "send", "state", "suite",
    "ste", "route", "rule", "tech", "med", "bw", "cr", "tx",
    "civ", "csr", "am", "pm", "end", "start", "any", "hard",
    "soft", "color", "building", "loop", "address", "location",
    "zoom", "video", "audio", "ordered", "ordering", "travel",
    "miles", "exhibit", "count", "service",
}


def _normalize_whitespace(term: str) -> str:
    return " ".join(term.strip().split())


def _strip_boundary_noise(term: str) -> str:
    parts = [part for part in _normalize_whitespace(term).split(" ") if part]
    while parts and parts[0].lower() in BOUNDARY_NOISE_WORDS:
        parts.pop(0)
    while parts and parts[-1].lower() in BOUNDARY_NOISE_WORDS:
        parts.pop()
    return " ".join(parts)


def _is_valid_term(term: str) -> bool:
    """Return True when a term is worth sending to Deepgram."""
    normalized = _strip_boundary_noise(term)
    lowered = normalized.lower()

    if not normalized or len(normalized) <= 1:
        return False
    if lowered in STOPWORDS:
        return False
    if lowered in STRUCTURE_BLACKLIST:
        return False
    if normalized.isdigit():
        return False
    if re.fullmatch(r"[^a-zA-Z0-9]+", normalized):
        return False
    if len(normalized.split()) == 1 and lowered.islower() and len(normalized) <= MIN_TERM_LENGTH:
        return False
    return True


def _deduplicate(terms: list[str]) -> list[str]:
    """Remove case-insensitive duplicates while preserving order."""
    seen: set[str] = set()
    result: list[str] = []

    for term in terms:
        normalized = _strip_boundary_noise(term)
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _looks_like_proper_name(term: str) -> bool:
    parts = [part for part in term.split() if part]
    if len(parts) < 2:
        return False
    return all(part[0].isupper() for part in parts if part[0].isalnum())


def _is_full_name(term: str) -> bool:
    """
    Return True when a term looks like a person's full name.
    """
    return bool(
        re.fullmatch(
            r"[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,2}",
            term.strip(),
        )
    )


def split_compound_terms(terms: list[str]) -> list[str]:
    """
    Break compound address-style phrases into Deepgram-friendly components.
    """
    result: list[str] = []

    for term in terms:
        if _is_full_name(term):
            result.append(term)
            continue

        parts = re.split(r"[,;]", term)

        for part in parts:
            cleaned = part.strip()
            cleaned = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", cleaned).strip()
            cleaned = re.sub(r"\b[A-Z]{2}\b", "", cleaned).strip()
            cleaned = re.sub(
                r"\b(?:Suite|Ste|Floor|Bldg|Building)\.?\s*\d+\w*\b",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            cleaned = re.sub(r"^\d+\s+", "", cleaned).strip()

            if not cleaned or cleaned.lower() in SKIP_WORDS or len(cleaned) < MIN_TERM_LENGTH:
                continue
            if cleaned.isdigit():
                continue

            result.append(cleaned)

    return result


def _prioritize(terms: list[str]) -> list[str]:
    """
    Sort keyterms by value:
    1. Full proper names
    2. Legal all-caps abbreviations
    3. Other multi-word phrases
    4. Everything else
    """
    proper_names = [term for term in terms if _looks_like_proper_name(term)]
    legal_caps = [
        term for term in terms
        if term.isupper() and len(term) >= 3 and " " not in term and term not in proper_names
    ]
    multi_word = [
        term for term in terms
        if " " in term and term not in proper_names and term not in legal_caps
    ]
    rest = [
        term for term in terms
        if term not in proper_names and term not in legal_caps and term not in multi_word
    ]
    return proper_names + legal_caps + multi_word + rest


def clean_keyterms(raw: list[str] | None) -> list[str]:
    """Filter, deduplicate, and prioritize a raw keyterm list."""
    filtered = [_strip_boundary_noise(term) for term in (raw or []) if _is_valid_term(term)]
    deduped = _deduplicate(filtered)
    return _prioritize(deduped)


def normalize_text(text: str) -> str:
    """Collapse raw extracted text into a regex-friendly single-line form."""
    text = text.replace("\n", " ")
    text = text.replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_legal_terms(text: str) -> str:
    """Normalize known multi-word legal phrase garbles before extraction."""
    normalized = text or ""
    for wrong, correct in MULTIWORD_FIXES.items():
        normalized = re.sub(re.escape(wrong), correct, normalized, flags=re.IGNORECASE)
    return normalized


def _extract_structured_entities(text: str) -> list[str]:
    """Extract multi-word legal entities from normalized text."""
    terms: list[str] = []

    for pattern in (NAME_PATTERN, CASE_NUMBER_PATTERN, FIRM_PATTERN, ADDRESS_PATTERN):
        terms.extend(match.group(0).strip(" ,.;:") for match in pattern.finditer(text))

    lowered = text.lower()
    for phrase in LEGAL_PHRASES:
        if phrase in lowered:
            terms.append(phrase.title() if phrase == "subpoena duces tecum" else phrase)

    return terms


def extract_keyterms_from_text(text: str) -> list[str]:
    """
    Extract candidate keyterms from source-document text.

    Uses structured regex extraction first, then supplements with quoted
    phrases, legal all-caps terms, and proper noun phrases.
    """
    normalized_text = normalize_legal_terms(normalize_text(text or ""))
    terms: list[str] = _extract_structured_entities(normalized_text)

    quoted = re.findall(r'"([^"]{2,50})"', normalized_text)
    terms.extend(quoted)

    caps_words = re.findall(r"\b([A-Z]{3,})\b", normalized_text)
    terms.extend(caps_words)

    proper_phrases = re.findall(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
        normalized_text,
    )
    terms.extend(proper_phrases)

    return clean_keyterms(terms)


def merge_keyterms(
    pdf_terms: list[str] | None,
    reporter_terms: list[str] | None = None,
    limit: int = MAX_KEYTERMS,
) -> tuple[list[str], list[str], list[str]]:
    """
    Merge primary intake/PDF terms with optional supplementary source-doc terms.

    Returns:
        final_terms, clean_primary_terms, reporter_terms_used
    """
    clean_primary = clean_keyterms(pdf_terms or [])
    clean_reporter = clean_keyterms(reporter_terms or [])

    clean_primary = split_compound_terms(clean_primary)
    clean_reporter = split_compound_terms(clean_reporter)

    clean_primary = clean_keyterms(clean_primary)
    clean_reporter = clean_keyterms(clean_reporter)

    primary_capped = clean_primary[:limit]
    remaining = max(0, limit - len(primary_capped))
    primary_keys = {term.lower() for term in primary_capped}

    reporter_fill = [
        term for term in clean_reporter
        if term.lower() not in primary_keys
    ][:remaining]

    final_terms = primary_capped + reporter_fill
    return final_terms, clean_primary, reporter_fill


def merge_from_intake(
    intake: "IntakeParsedResult",
    reporter_terms: list[str] | None = None,
    limit: int = MAX_KEYTERMS,
) -> tuple[list[str], int, int]:
    """
    Build final Deepgram keyterm list from a parsed intake result.
    """
    pdf_terms = list(getattr(intake, "all_proper_nouns", []) or [])

    clean_pdf = clean_keyterms(pdf_terms)
    clean_reporter = clean_keyterms(reporter_terms or [])

    clean_pdf = split_compound_terms(clean_pdf)
    clean_reporter = split_compound_terms(clean_reporter)

    clean_pdf = clean_keyterms(clean_pdf)
    clean_reporter = clean_keyterms(clean_reporter)

    pdf_capped = clean_pdf[:limit]
    remaining = max(0, limit - len(pdf_capped))
    pdf_lower = {term.lower() for term in pdf_capped}
    reporter_fill = [
        term for term in clean_reporter
        if term.lower() not in pdf_lower
    ][:remaining]

    final = pdf_capped + reporter_fill
    return final, len(pdf_capped), len(reporter_fill)
