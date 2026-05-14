"""Deterministic Deepgram keyterm sanitizer — single active-path layer.

The active-path keyterm pipeline today is:

    intake/source-docs  →  UI assembly  →  merge_keyterms  →  job_runner
                                                                  │
                                                                  ▼
                                                 keyterm_sanitizer.sanitize_for_deepgram(...)
                                                                  │
                                                                  ▼
                                                  pipeline/transcriber._transcribe_direct
                                                  (urlencode + POST to Deepgram)

Earlier filters (``core.intake_parser.hard_filter_keyterms``,
``core.keyterm_extractor.clean_keyterms``) keep running for their own
data-model invariants. This module is the **final authoritative
gate**: nothing after this point applies content rules to the keyterm
list before Deepgram sees it.

Design contract (from
``docs/investigations/KEYTERM_REQUEST_AUDIT.md``):

- **Deterministic.** No model calls, no probabilistic scoring.
- **Quality over quantity.** 25 excellent keyterms is preferred over
  100 noisy keyterms. Legal entities, person names, addresses,
  case numbers, medical and legal terminology are protected.
- **Provenance preserved.** Every input keyterm produces a
  ``SanitizedKeyterm`` record carrying the original text, the
  sanitized form, the score, the category, and (when rejected)
  the reason.
- **Hard budget enforcement.** Token budget never exceeds
  ``config.DEEPGRAM_MAX_KEYTERM_TOKENS``. When the budget is
  saturated, the lowest-scoring terms drop first; protected
  entities are preserved.
- **No architectural drift.** Single module under ``pipeline/``;
  does not import from ``clean_format/``, ``spec_engine/``, or any
  UI module. Production callers replace the legacy
  ``trim_keyterms_for_deepgram`` invocation site with
  ``sanitize_for_deepgram`` (one call-site change in
  ``core/job_runner.py``).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum characters per single keyterm. A legitimate keyterm is at
# most a short phrase; entries past 100 chars are almost always
# form-template extraction noise.
KEYTERM_MAX_ENTRY_CHARS = 100

# Minimum character length for any keyterm to be considered.
KEYTERM_MIN_LENGTH = 3

# Hard cap on the number of keyterms shipped to Deepgram per request.
# Observed production failure (logs/pipeline.log 2026-05-13 10:52:52):
# Deepgram returned ``400 Bad Request: Keyterm limit exceeded. The
# maximum number of tokens across all keyterms is 500.`` when the
# request carried ~102 short keyterms. The token estimate said we
# were inside the 500-token cap; Deepgram's server-side tokenizer
# counted higher. 98 leaves a margin below the failure point and is
# a deterministic count-based safety net regardless of token math.
MAX_KEYTERM_COUNT = 98

# Per-keyterm overhead (in estimated tokens) added on top of the
# char-based estimate. Calibrated against the observed failure
# above: the 500-token Deepgram cap is the *server-side* count, not
# the URL byte count, and short keyterms appear to cost more than
# our ``(len + 3) // 4 + 1`` formula suggests. Adding +1 per term
# leaves headroom without dropping legitimate entries.
KEYTERM_TOKEN_OVERHEAD = 1

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORY_PERSON = "person"
CATEGORY_LAW_FIRM = "law_firm"
CATEGORY_MEDICAL = "medical"
CATEGORY_ADDRESS = "address"
CATEGORY_CASE_NUMBER = "case_number"
CATEGORY_LEGAL_TERM = "legal_term"
CATEGORY_ACRONYM = "acronym"
CATEGORY_PROPER_PHRASE = "proper_phrase"
CATEGORY_UNKNOWN = "unknown"
CATEGORY_REJECTED_NOISE = "rejected_noise"

# Score table — higher means "more valuable to Deepgram on this case".
CATEGORY_SCORES: dict[str, int] = {
    CATEGORY_CASE_NUMBER: 100,
    CATEGORY_PERSON: 90,
    CATEGORY_LAW_FIRM: 85,
    CATEGORY_ADDRESS: 80,
    CATEGORY_MEDICAL: 75,
    CATEGORY_LEGAL_TERM: 70,
    CATEGORY_ACRONYM: 60,
    CATEGORY_PROPER_PHRASE: 40,
    CATEGORY_UNKNOWN: 10,
    CATEGORY_REJECTED_NOISE: 0,
}

# ---------------------------------------------------------------------------
# Whitelists — terms that override the all-caps / single-word rejections
# ---------------------------------------------------------------------------

# Medical acronyms / abbreviations safe to ship even as single tokens.
MEDICAL_ACRONYMS = frozenset({
    "MRI", "CT", "EMG", "EKG", "ECG", "MR", "PA", "ER", "ICU", "OR",
    "CAT", "X-RAY", "XR", "PET", "DEXA", "EEG", "BP", "BMI",
    "ACL", "MCL", "PCL", "TKR", "THR", "ORIF", "C2", "C3", "C4",
    "C5", "C6", "C7", "L1", "L2", "L3", "L4", "L5", "S1", "T1",
})

# Court-reporting / legal abbreviations.
LEGAL_ACRONYMS = frozenset({
    "CSR", "RPR", "RMR", "CRR", "CDL", "DOB", "EIN", "SSN",
    "PLLC", "LLP", "LLC", "LLP", "PC", "JD", "MD", "DO",
    "JR", "SR", "III", "IV", "II",
})

# Single-word medical terminology worth preserving even though it's
# one word.
MEDICAL_TERMS = frozenset({
    "laminectomy", "vertebroplasty", "kyphoplasty", "discectomy",
    "radiculopathy", "spondylosis", "spondylolisthesis", "stenosis",
    "neuropathy", "myelopathy", "arthroplasty", "fusion",
    "epidural", "annulus", "facetectomy", "foraminotomy",
    "rhizotomy", "decompression", "diskectomy",
})

# Single-word / short multi-word legal terms worth preserving.
LEGAL_TERMS = frozenset({
    "voir dire", "stenographic", "deposition", "subpoena",
    "duces tecum", "subpoena duces tecum",
    "interrogatories", "deposition", "errata",
})

# ---------------------------------------------------------------------------
# Blacklists — boilerplate that should never reach Deepgram
# ---------------------------------------------------------------------------

# Generic single-word legal boilerplate. Comparison is case-insensitive.
GENERIC_BOILERPLATE = frozenset({
    "united", "states", "district", "court", "western", "eastern",
    "northern", "southern", "division", "take", "oral", "notice",
    "deposition", "intention", "plaintiff", "defendant", "attorney",
    "respectfully", "submitted", "civil", "rules", "procedure",
    "produce", "case", "appearance", "delivery", "signature",
    "parking", "interpreter", "original", "standard", "certificate",
    "telephone", "facsimile", "witness", "judicial", "county",
    "cause", "honorable", "judge", "courtroom", "video", "audio",
    "zoom", "service", "send", "send to", "service email",
    "trans", "rush", "due", "ordered", "ordering", "tx", "texas",
    "ste", "suite", "floor", "building", "address", "format",
    # Title-case noise tokens observed in real OCR output that
    # ride into the keyterm list as single words. These are common
    # legal-pleading vocabulary; their meaning is carried by context,
    # not by being keyed to Deepgram.
    "standing", "specialty", "seam", "company", "remote",
    "reporter", "judge", "honorable", "ordered", "inc",
    "personal", "health",
})

# Multi-word boilerplate phrases — OCR-tail patterns observed across
# real depositions. Comparison is case-insensitive substring match.
OCR_TAIL_PATTERNS = (
    "original standard",
    "trans rush",
    "trans rush due",
    "rush due",
    "service email",
    "electronically served",
    "signature waived",
    "certificate of service",
    "respectfully submitted",
    "notice of intention",
    "notice of intent to take",
    "notice of taking",
    "in accordance with",
    "pursuant to",
    "conference room",
)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Case number forms commonly seen on Texas/Federal pleadings.
# Examples: C-5722-24-L, 2024-CI-27841, 2:23-cv-00456.
CASE_NUMBER_RE = re.compile(
    r"\b("
    r"[Cc]-?\d{3,5}-\d{2}-?[A-Z]"
    r"|\d{4}-?[Cc][Ii]-?\d{3,6}"
    r"|\d:\d{2}-[a-z]{2}-\d{4,6}"
    r")\b"
)

# Person full-name shapes (2-3 word capitalized sequences with optional
# middle initial and suffix).
PERSON_NAME_RE = re.compile(
    r"^[A-Z][a-z'’-]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z'’-]+){1,2}(?:\s+(?:Jr|Sr|II|III|IV)\.?)?$"
)

# Law-firm suffixes — comparison is case-insensitive word match.
LAW_FIRM_SUFFIXES = re.compile(
    r"\b(PLLC|LLP|LLC|P\.?C\.?|Law Firm|Law Offices?|& Associates|"
    r"Brain and Spine Injury Lawyers|"
    r"Group|Partners)\b",
    re.IGNORECASE,
)

# Address shape — number prefix + street word.
ADDRESS_RE = re.compile(
    r"^\d{2,6}\s+[A-Za-z0-9.\-' ]+?\b("
    r"Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|"
    r"Place|Pl|Court|Ct|Expressway|Expy|Highway|Hwy|Parkway|Pkwy|"
    r"Way|Trail|Trl|Circle|Cir|Loop|Suite|Ste|Floor|Bldg|Building"
    r")\b",
    re.IGNORECASE,
)

# Acronym shape: 2-5 uppercase letters (possibly with dots/numbers).
ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{1,5}$")

# ---------------------------------------------------------------------------
# Rejection reasons (referenced by tests and audit reports)
# ---------------------------------------------------------------------------

REASON_EMPTY = "empty_or_whitespace"
REASON_TOO_SHORT = "below_min_length"
REASON_TOO_LONG = "above_char_cap"
REASON_PUNCT_ONLY = "punctuation_only"
REASON_DIGIT_ONLY = "digit_only"
REASON_SINGLE_GENERIC = "single_word_generic"
REASON_SINGLE_ALL_CAPS = "single_word_all_caps_not_whitelisted"
REASON_BOILERPLATE = "ocr_boilerplate_phrase"
REASON_DUPLICATE = "duplicate_of_kept"
REASON_SUBSUMED_BY_FULL_FORM = "subsumed_by_longer_full_form"
REASON_BUDGET = "trimmed_for_token_budget"
REASON_COUNT_CAP = "trimmed_for_count_cap"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SanitizedKeyterm:
    """Audit record for a single keyterm candidate."""

    original: str
    sanitized: str
    source: str = ""
    score: int = 0
    accepted: bool = False
    rejection_reason: str = ""
    token_count: int = 0
    category: str = CATEGORY_UNKNOWN


@dataclass(slots=True)
class SanitizationResult:
    """Result of running the sanitizer over a list of candidates."""

    accepted: list[SanitizedKeyterm] = field(default_factory=list)
    rejected: list[SanitizedKeyterm] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def accepted_terms(self) -> list[str]:
        return [k.sanitized for k in self.accepted]

    @property
    def used_tokens(self) -> int:
        return sum(k.token_count for k in self.accepted)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(term: str) -> str:
    return _WHITESPACE_RE.sub(" ", (term or "").strip())


def _estimate_tokens(term: str) -> int:
    """Conservative char→token estimator (English).

    Returns ``(len + 3) // 4 + 1 + KEYTERM_TOKEN_OVERHEAD``. The
    overhead term is calibrated against an observed Deepgram 400
    response — see ``MAX_KEYTERM_COUNT`` docstring for the incident.
    Without the overhead, short keyterms (UNITED, STATES, COURT)
    each cost 3 tokens by our estimator but apparently more by
    Deepgram's tokenizer, and the cumulative drift across ~100 terms
    pushed the request over Deepgram's 500-token cap.
    """
    return (len(term) + 3) // 4 + 1 + KEYTERM_TOKEN_OVERHEAD


def _is_punctuation_only(term: str) -> bool:
    return bool(term) and re.fullmatch(r"[^A-Za-z0-9]+", term) is not None


def _has_boilerplate_phrase(term: str) -> bool:
    lower = term.lower()
    return any(pattern in lower for pattern in OCR_TAIL_PATTERNS)


def _categorize(term: str) -> str:
    """Best-effort deterministic category for a sanitized term."""
    if CASE_NUMBER_RE.search(term):
        return CATEGORY_CASE_NUMBER

    if ADDRESS_RE.match(term):
        return CATEGORY_ADDRESS

    if LAW_FIRM_SUFFIXES.search(term):
        return CATEGORY_LAW_FIRM

    lower = term.lower()
    if lower in MEDICAL_TERMS:
        return CATEGORY_MEDICAL
    if any(lower == legal for legal in LEGAL_TERMS) or lower in LEGAL_TERMS:
        return CATEGORY_LEGAL_TERM

    if PERSON_NAME_RE.match(term):
        return CATEGORY_PERSON

    # Acronyms — only the whitelisted ones count.
    if ACRONYM_RE.match(term):
        if term.upper() in MEDICAL_ACRONYMS or term.upper() in LEGAL_ACRONYMS:
            return CATEGORY_ACRONYM
        # Unwhitelisted single-word all-caps → noise (Rule C).
        return CATEGORY_REJECTED_NOISE

    # Multi-word capitalized phrase that doesn't match a more specific
    # category — keep but score modestly.
    words = term.split()
    if (
        len(words) >= 2
        and all(w[:1].isupper() for w in words if w[:1].isalnum())
    ):
        return CATEGORY_PROPER_PHRASE

    return CATEGORY_UNKNOWN


def _is_single_generic_word(term: str) -> bool:
    """Rule B: single-word generic legal boilerplate."""
    if " " in term:
        return False
    return term.lower() in GENERIC_BOILERPLATE


def _is_whitelisted_acronym(term: str) -> bool:
    """True when ``term`` is a whitelisted medical / legal acronym.

    Acronyms get a fast-path past min-length and Rule-C checks so that
    valid 2-char tokens (CT, MR, OR, ER) and ALL-CAPS legal/medical
    abbreviations (CSR, PLLC, MRI) survive.
    """
    upper = term.upper()
    return upper in MEDICAL_ACRONYMS or upper in LEGAL_ACRONYMS


def _evaluate(
    candidate: str, source: str = ""
) -> SanitizedKeyterm:
    """Score and categorize a single candidate string.

    Order of checks (intentional — most-rejecting first, with the
    acronym whitelist short-circuited ahead of the min-length and
    Rule-C all-caps gates so that 2-char and ALL-CAPS acronyms
    survive).
    """
    original = candidate
    sanitized = _normalize(candidate)

    if not sanitized:
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_EMPTY,
            category=CATEGORY_REJECTED_NOISE,
        )

    if len(sanitized) > KEYTERM_MAX_ENTRY_CHARS:
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_TOO_LONG,
            category=CATEGORY_REJECTED_NOISE,
            token_count=_estimate_tokens(sanitized),
        )

    # Acronym fast-path — must run before min-length and Rule C so
    # that "CT", "MR", "OR", "ER", "MRI", "CSR", "PLLC" survive.
    if _is_whitelisted_acronym(sanitized):
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=True,
            score=CATEGORY_SCORES[CATEGORY_ACRONYM],
            token_count=_estimate_tokens(sanitized),
            category=CATEGORY_ACRONYM,
        )

    if len(sanitized) < KEYTERM_MIN_LENGTH:
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_TOO_SHORT,
            category=CATEGORY_REJECTED_NOISE,
        )

    if _is_punctuation_only(sanitized):
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_PUNCT_ONLY,
            category=CATEGORY_REJECTED_NOISE,
        )

    if sanitized.isdigit():
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_DIGIT_ONLY,
            category=CATEGORY_REJECTED_NOISE,
        )

    if _has_boilerplate_phrase(sanitized):
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_BOILERPLATE,
            category=CATEGORY_REJECTED_NOISE,
            token_count=_estimate_tokens(sanitized),
        )

    # Rule B — generic single-word legal boilerplate.
    if _is_single_generic_word(sanitized):
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_SINGLE_GENERIC,
            category=CATEGORY_REJECTED_NOISE,
        )

    # Rule C — single-word ALL-CAPS pure-alpha that did not pass the
    # acronym whitelist. Catches the load-bearing class of OCR-style
    # noise: "LEONARDO", "ROCIO", "DISTRICT", "CAUSE", etc.
    if (
        " " not in sanitized
        and sanitized.isalpha()
        and sanitized.isupper()
    ):
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_SINGLE_ALL_CAPS,
            category=CATEGORY_REJECTED_NOISE,
            token_count=_estimate_tokens(sanitized),
        )

    category = _categorize(sanitized)

    # Categorizer says "rejected_noise" — covers edge cases the
    # explicit Rule-B / Rule-C gates above did not catch.
    if category == CATEGORY_REJECTED_NOISE:
        return SanitizedKeyterm(
            original=original,
            sanitized=sanitized,
            source=source,
            accepted=False,
            rejection_reason=REASON_SINGLE_ALL_CAPS,
            category=CATEGORY_REJECTED_NOISE,
            token_count=_estimate_tokens(sanitized),
        )

    # Provisionally accept.
    return SanitizedKeyterm(
        original=original,
        sanitized=sanitized,
        source=source,
        accepted=True,
        score=CATEGORY_SCORES.get(category, 0),
        token_count=_estimate_tokens(sanitized),
        category=category,
    )


# ---------------------------------------------------------------------------
# Duplicate collapse — Rule D
# ---------------------------------------------------------------------------


def _is_subsumed(short: str, longer: str) -> bool:
    """True when ``short`` is a substring fragment of ``longer`` such
    that keeping both would be redundant (e.g. ``Cukjati`` inside
    ``Jacob D. Cukjati``).

    The match is whole-word and case-insensitive. ``Bardot`` and
    ``Miah Bardot`` both qualify — keep the longer form.
    """
    if not short or not longer or short == longer:
        return False
    if len(short.split()) >= len(longer.split()):
        return False
    pattern = r"\b" + re.escape(short) + r"\b"
    return bool(re.search(pattern, longer, re.IGNORECASE))


def _collapse_duplicates(
    accepted: list[SanitizedKeyterm],
) -> tuple[list[SanitizedKeyterm], list[SanitizedKeyterm]]:
    """Remove short fragments that are contained inside longer accepted
    forms. Higher-scoring / longer-form wins.

    Returns ``(kept, dropped)``.
    """
    # Sort by score desc, then word-count desc — longest highest-quality
    # form is considered "canonical" and shorter fragments that are
    # subsumed by it are dropped.
    ranked = sorted(
        accepted,
        key=lambda k: (k.score, len(k.sanitized.split()), len(k.sanitized)),
        reverse=True,
    )

    kept: list[SanitizedKeyterm] = []
    dropped: list[SanitizedKeyterm] = []
    seen_keys: set[str] = set()

    for term in ranked:
        key = term.sanitized.lower()
        if key in seen_keys:
            dup = SanitizedKeyterm(
                original=term.original,
                sanitized=term.sanitized,
                source=term.source,
                score=term.score,
                accepted=False,
                rejection_reason=REASON_DUPLICATE,
                token_count=term.token_count,
                category=term.category,
            )
            dropped.append(dup)
            continue

        subsumed = False
        for k in kept:
            if _is_subsumed(term.sanitized, k.sanitized):
                subsumed = True
                break
        if subsumed:
            dropped.append(
                SanitizedKeyterm(
                    original=term.original,
                    sanitized=term.sanitized,
                    source=term.source,
                    score=term.score,
                    accepted=False,
                    rejection_reason=REASON_SUBSUMED_BY_FULL_FORM,
                    token_count=term.token_count,
                    category=term.category,
                )
            )
            continue

        kept.append(term)
        seen_keys.add(key)

    return kept, dropped


# ---------------------------------------------------------------------------
# Budget enforcement — Rule E
# ---------------------------------------------------------------------------


def _enforce_token_budget(
    kept: list[SanitizedKeyterm],
    budget: int,
    *,
    max_count: int = MAX_KEYTERM_COUNT,
) -> tuple[list[SanitizedKeyterm], list[SanitizedKeyterm]]:
    """Greedy descending-score fill until BOTH the token budget and
    the count cap are honored.

    Highest-scoring terms are guaranteed to be kept first; lowest-
    scoring overflow becomes the dropped set with the most-specific
    reason (``REASON_COUNT_CAP`` when the cap fires, ``REASON_BUDGET``
    when the token budget fires).
    """
    ranked = sorted(
        kept,
        key=lambda k: (k.score, len(k.sanitized.split())),
        reverse=True,
    )
    final: list[SanitizedKeyterm] = []
    dropped: list[SanitizedKeyterm] = []
    used = 0
    for term in ranked:
        # Count cap fires first — it is the hard server-side safety
        # net regardless of any token-math drift.
        if len(final) >= max_count:
            dropped.append(
                SanitizedKeyterm(
                    original=term.original,
                    sanitized=term.sanitized,
                    source=term.source,
                    score=term.score,
                    accepted=False,
                    rejection_reason=REASON_COUNT_CAP,
                    token_count=term.token_count,
                    category=term.category,
                )
            )
            continue
        if used + term.token_count > budget:
            dropped.append(
                SanitizedKeyterm(
                    original=term.original,
                    sanitized=term.sanitized,
                    source=term.source,
                    score=term.score,
                    accepted=False,
                    rejection_reason=REASON_BUDGET,
                    token_count=term.token_count,
                    category=term.category,
                )
            )
            continue
        final.append(term)
        used += term.token_count
    return final, dropped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sanitize_for_deepgram(
    keyterms: Iterable[str] | None,
    *,
    sources: dict[str, list[str]] | None = None,
    token_budget: int | None = None,
    max_count: int = MAX_KEYTERM_COUNT,
) -> SanitizationResult:
    """Sanitize a keyterm list for the Deepgram request.

    Parameters
    ----------
    keyterms:
        Flat input list. Order is preserved through accept/reject.
        When ``sources`` is also provided, the ``source`` annotation
        on each accepted ``SanitizedKeyterm`` is recovered from it.
    sources:
        Optional ``{source_label: [terms]}`` map for provenance.
        Each label is propagated onto the per-keyterm record. Items
        in ``keyterms`` that don't appear in any source list get
        ``source=""``.
    token_budget:
        Override for the Deepgram token budget. Defaults to
        ``config.DEEPGRAM_MAX_KEYTERM_TOKENS``.
    max_count:
        Hard cap on the number of accepted keyterms. Defaults to
        ``MAX_KEYTERM_COUNT`` (98) — defense-in-depth against the
        observed Deepgram server-side count limit.
    """
    from config import DEEPGRAM_MAX_KEYTERM_TOKENS

    if token_budget is None:
        token_budget = DEEPGRAM_MAX_KEYTERM_TOKENS

    # Pre-build a source lookup for provenance.
    source_lookup: dict[str, str] = {}
    if sources:
        for label, items in sources.items():
            for item in items or []:
                key = _normalize(str(item)).lower()
                if key and key not in source_lookup:
                    source_lookup[key] = label

    raw = list(keyterms or [])

    # Stage 1 — per-term scoring + content rules.
    provisional_accepted: list[SanitizedKeyterm] = []
    rejected: list[SanitizedKeyterm] = []
    for candidate in raw:
        if candidate is None:
            continue
        record = _evaluate(str(candidate))
        # Stamp the source label, if known.
        key = record.sanitized.lower()
        if key and key in source_lookup:
            record.source = source_lookup[key]
        if record.accepted:
            provisional_accepted.append(record)
        else:
            rejected.append(record)

    # Stage 2 — collapse duplicates and longer-form-subsumed fragments.
    deduped, subsumed = _collapse_duplicates(provisional_accepted)
    rejected.extend(subsumed)

    # Stage 3 — enforce count cap AND token budget (count fires first).
    final_accepted, over_budget = _enforce_token_budget(
        deduped, token_budget, max_count=max_count
    )
    rejected.extend(over_budget)

    # Stats reflect the full journey.
    rule_counts: dict[str, int] = {}
    for r in rejected:
        rule_counts[r.rejection_reason] = rule_counts.get(r.rejection_reason, 0) + 1

    category_counts: dict[str, int] = {}
    for a in final_accepted:
        category_counts[a.category] = category_counts.get(a.category, 0) + 1

    stats: dict[str, int] = {
        "raw": len(raw),
        "accepted": len(final_accepted),
        "rejected": len(rejected),
        "duplicates_removed": rule_counts.get(REASON_DUPLICATE, 0)
        + rule_counts.get(REASON_SUBSUMED_BY_FULL_FORM, 0),
        "ocr_fragments_removed": rule_counts.get(REASON_BOILERPLATE, 0),
        "single_generic_removed": rule_counts.get(REASON_SINGLE_GENERIC, 0),
        "single_all_caps_removed": rule_counts.get(REASON_SINGLE_ALL_CAPS, 0),
        "budget_trimmed": rule_counts.get(REASON_BUDGET, 0),
        "count_cap_trimmed": rule_counts.get(REASON_COUNT_CAP, 0),
        "oversize_removed": rule_counts.get(REASON_TOO_LONG, 0),
        "below_min_length_removed": rule_counts.get(REASON_TOO_SHORT, 0),
        "final_tokens": sum(a.token_count for a in final_accepted),
        "budget": token_budget,
    }
    # Per-category accepted counts for logging.
    for cat, count in category_counts.items():
        stats[f"category_{cat}"] = count

    return SanitizationResult(
        accepted=final_accepted,
        rejected=rejected,
        stats=stats,
    )


def format_log_line(result: SanitizationResult) -> str:
    """One-line ``[KEYTERM_SANITIZER]`` log message."""
    s = result.stats
    parts = [
        f"raw={s.get('raw', 0)}",
        f"accepted={s.get('accepted', 0)}",
        f"rejected={s.get('rejected', 0)}",
        f"duplicates_removed={s.get('duplicates_removed', 0)}",
        f"ocr_fragments_removed={s.get('ocr_fragments_removed', 0)}",
        f"single_all_caps_removed={s.get('single_all_caps_removed', 0)}",
        f"single_generic_removed={s.get('single_generic_removed', 0)}",
        f"count_cap_trimmed={s.get('count_cap_trimmed', 0)}",
        f"budget_trimmed={s.get('budget_trimmed', 0)}",
        f"final_tokens={s.get('final_tokens', 0)}/{s.get('budget', 0)}",
    ]
    return "[KEYTERM_SANITIZER] " + " ".join(parts)
