"""
pipeline/keywords.py

Builds the legal keyword/keyterm list for Deepgram Nova-3.

WHY KEYWORDS MATTER:
  Nova-3 supports up to 100 keyterms injected via in-context learning.
  Multi-word phrases are dramatically more effective than single words.
  These reduce word error rate on domain-specific terms by 30-60%.

BUDGET: 50 static legal phrases + up to 50 dynamic case-specific terms = 100 max.
"""

import re
from typing import List

# ── Static legal vocabulary ───────────────────────────────────────────────────
STATIC_LEGAL_KEYTERMS: List[str] = [
    # Texas procedural
    "Texas Rules of Civil Procedure",
    "Texas Rules of Evidence",
    "Texas Uniform Format Manual",
    "Bexar County District Court",
    "285th Judicial District",
    "Rules of Civil Procedure",
    "Code of Criminal Procedure",
    "Texas Civil Practice and Remedies Code",
    "District Court of Texas",
    "Texas Supreme Court",
    # Deposition verbal markers
    "let the record reflect",
    "mark as Exhibit",
    "on the record",
    "off the record",
    "calls for speculation",
    "asked and answered",
    "beyond the scope",
    "compound question",
    "leading question",
    "lack of foundation",
    "assumes facts not in evidence",
    "move to strike",
    # Legal standards
    "preponderance of the evidence",
    "beyond a reasonable doubt",
    "standard of care",
    "reasonable person standard",
    "proximate cause",
    "res ipsa loquitur",
    "summary judgment",
    "motion in limine",
    "directed verdict",
    "judgment notwithstanding the verdict",
    # Speaker labels
    "THE REPORTER",
    "THE WITNESS",
    "EXAMINATION BY",
    "CROSS-EXAMINATION BY",
    "REDIRECT EXAMINATION",
    "RECROSS-EXAMINATION",
    "BY THE WITNESS",
    "BY MR",
    # Medical / expert witness
    "reasonable degree of medical probability",
    "reasonable degree of medical certainty",
    "causal relationship",
    "differential diagnosis",
    "mechanism of injury",
    "permanent impairment",
    "activities of daily living",
    "maximum medical improvement",
    "independent medical examination",
    "subpoena duces tecum",
]


def get_static_keyterms() -> List[str]:
    """Return a copy of the built-in static keyterm list."""
    return list(STATIC_LEGAL_KEYTERMS)


def build_keyterms(dynamic_terms: List[str] = None) -> List[str]:
    """
    Build the final keyterm list for a Deepgram call.

    Args:
        dynamic_terms: Case-specific terms from user input or extracted from docs.

    Returns:
        List of up to 100 keyterm strings. Dynamic terms have priority.
    """
    if dynamic_terms is None:
        dynamic_terms = []

    cleaned: List[str] = []
    seen: set = set()
    for term in dynamic_terms:
        term = term.strip()
        if term and term.lower() not in seen:
            cleaned.append(term)
            seen.add(term.lower())

    combined = cleaned + STATIC_LEGAL_KEYTERMS
    return combined[:100]


def parse_dynamic_terms_from_text(raw_text: str) -> List[str]:
    """
    Parse a newline-separated or comma-separated string of terms.

    Returns:
        List of individual term strings, stripped and deduplicated.
    """
    if not raw_text or not raw_text.strip():
        return []

    if "\n" in raw_text:
        terms = raw_text.split("\n")
    else:
        terms = raw_text.split(",")

    return [t.strip() for t in terms if t.strip()]


def extract_terms_from_document_text(doc_text: str) -> List[str]:
    """
    Extract candidate proper nouns and legal terms from raw document text.
    Used as a fallback when AI extraction is unavailable.

    Looks for:
      - Capitalized multi-word phrases (likely names / entities)
      - Cause numbers (pattern: YYYY-XX-NNNNNN)
      - All-caps abbreviations (LLC, PLLC, CSR, etc.)

    Returns:
        Deduplicated list of candidate terms.
    """
    terms: List[str] = []
    seen: set = set()

    # Cause number pattern
    for m in re.finditer(r"\b\d{4}-[A-Z]{1,4}-\d{4,8}\b", doc_text):
        val = m.group(0)
        if val.lower() not in seen:
            terms.append(val)
            seen.add(val.lower())

    # Capitalized proper-noun phrases (2-4 words)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", doc_text):
        val = m.group(1).strip()
        if val.lower() not in seen and len(val) > 4:
            terms.append(val)
            seen.add(val.lower())

    # Known legal entity suffixes in full form
    for m in re.finditer(
        r"\b([A-Z][A-Za-z\s&,\.]+(?:LLC|LP|LLP|PLLC|Inc\.|Corp\.|P\.C\.))\b",
        doc_text,
    ):
        val = m.group(1).strip().rstrip(",.")
        if val.lower() not in seen:
            terms.append(val)
            seen.add(val.lower())

    return terms
