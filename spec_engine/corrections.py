"""Text normalization only for deterministic transcript enforcement."""

from __future__ import annotations

import re

from .models import TranscriptBlock
from .objections import looks_like_parenthetical, normalize_objection_line, normalize_parenthetical_line

_QUESTION_STARTERS = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "did",
    "do",
    "is",
    "are",
    "was",
    "were",
)
_INTRODUCTORY_COMMA_WORDS = ("yes", "no", "well", "so", "now", "correct")
# Per Morson's Rule 170: spell out isolated numbers 1-10. Eleven and
# twelve are kept as digits. Authority for this project's style is
# Morson's English Guide for Court Reporters, Second Edition.
_SMALL_NUMBER_WORDS = {
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
    "10": "Ten",
}
_NUMBER_WORDS_SENTENCE = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}
LEGAL_TERMS = {"objection", "form", "foundation", "privilege"}


def _fix_spacing(text: str) -> str:
    text = str(text or "").strip()
    return re.sub(r"\s{2,}", " ", text)


def _fix_sentence_start(text: str) -> str:
    if not text:
        return text

    match = re.match(r"^(\d+)\b(.*)$", text)
    if match and match.group(1) in _SMALL_NUMBER_WORDS:
        text = f"{_SMALL_NUMBER_WORDS[match.group(1)]}{match.group(2)}"

    return text[0].upper() + text[1:] if text else text


def _fix_small_numbers(text: str) -> str:
    """Spell out isolated numbers 1-9 when safe.

    Preserves cause numbers, dates, exhibit references, and alphanumeric IDs.
    """
    skip_tokens = ("exhibit", "cause", "page", "line", "section")

    def repl(match: re.Match[str]) -> str:
        num = match.group(1)
        start = match.start(1)
        prefix = text[max(0, start - 12):start].lower()
        if any(token in prefix for token in skip_tokens):
            return num
        return _NUMBER_WORDS_SENTENCE.get(num, num)

    return re.sub(r"\b([1-9])\b", repl, text)


def _fix_stutters(text: str) -> str:
    return re.sub(
        r"\b(\w+)\s+\1\b",
        lambda match: f"{match.group(1)}  {match.group(1)}",
        text,
        flags=re.IGNORECASE,
    )


def _fix_ellipses(text: str) -> str:
    text = re.sub(r"\.\s*\.\s*\.", "...", text)
    return re.sub(r"\.{4,}", "...", text)


def _normalize_em_dashes(text: str) -> str:
    """Normalize all em-dash representations to spaced double-hyphen.

    Per Morson's Rule 85 Note, the spaced double-hyphen ` -- ` is the
    canonical court-reporting form. This function ONLY normalizes the
    representation; it NEVER collapses an interruption marker into
    spaces and NEVER removes one.

    Conversions:
    - U+2014 (em-dash) `—` -> ` -- `
    - U+2013 (en-dash) `–` -> ` -- `
    - ASCII `--` with inconsistent surrounding whitespace -> ` -- `

    The function is idempotent: running it on already-normalized text
    produces the same result.
    """
    # Unicode em-dash and en-dash with any surrounding whitespace.
    text = re.sub(r"\s*[–—]\s*", " -- ", text)
    # ASCII double-hyphen with any surrounding whitespace.
    text = re.sub(r"\s*--\s*", " -- ", text)
    return text


def _fix_short_answer_commas(text: str) -> str:
    if len(text.split()) <= 1:
        return text

    text = re.sub(
        r"^(yes|no|well|so|now|correct)\s+(?!,)",
        lambda match: f"{match.group(1)}, ",
        text,
        flags=re.IGNORECASE,
    )

    words = text.split()
    if len(words) > 6:
        text = re.sub(
            r"(?<!,)\s+(but|and|so)\s+", r", \1 ", text, count=1, flags=re.IGNORECASE
        )

    return text


def _fix_ending_punctuation(text: str) -> str:
    """Default missing terminal punctuation to a period.

    Verbatim rule (Morson's; clean_format/prompt.py):
    - Filler words (uh, um, you know) are spoken evidence and are
      NEVER stripped from the transcript, including from end of an
      utterance. The earlier regex that did so is removed.
    - Inferring `?` from word order is unsafe. Morson's gives no rule
      for it; the reporter is assumed to have heard the inflection.
      This deterministic pass defaults to `.` and lets the human
      reviewer flip the call to `?` after audio review.
    """
    text = text.rstrip()

    if not re.search(r"[.?!]$", text):
        text += "."

    return text


def apply_proper_noun_corrections(text: str, corrections: dict) -> str:
    """
    Replace misrecognized proper nouns using confirmed spellings.

    Must be:
    - case-insensitive
    - word-boundary safe
    """
    text = str(text or "")
    for wrong, correct in (corrections or {}).items():
        wrong_text = str(wrong or "").strip()
        correct_text = str(correct or "").strip()
        if not wrong_text or not correct_text:
            continue
        if wrong_text.lower() in LEGAL_TERMS:
            continue
        pattern = r"\b" + re.escape(wrong_text) + r"\b"
        text = re.sub(pattern, correct_text, text, flags=re.IGNORECASE)
    return text


def _build_corrections_map(
    confirmed_spellings: dict | None = None,
    keyterms: list[str] | None = None,
) -> dict[str, str]:
    """Build the (wrong → correct) map applied during corrections.

    Priority: per-case NOD spellings override the baseline legal dictionary
    override keyterm fallbacks. LEGAL_TERMS entries are silently dropped from
    every source — that blocklist guards against an intake or dictionary
    typo overwriting common objection vocabulary.
    """
    from core.case_vocab import load_legal_dictionary

    corrections: dict[str, str] = {}

    # Layer 1 (lowest priority): hand-maintained baseline dictionary —
    # common ASR mishearings that recur across cases (e.g. "voir deer"
    # → "voir dire"). Per-case NOD entries below will overwrite any
    # collisions, which is the intended override direction.
    for wrong, correct in load_legal_dictionary().items():
        wrong_text = str(wrong or "").strip()
        correct_text = str(correct or "").strip()
        if not wrong_text or not correct_text:
            continue
        if wrong_text.lower() in LEGAL_TERMS:
            continue
        corrections[wrong_text] = correct_text

    # Layer 2 (highest priority): per-case NOD spellings.
    for wrong, correct in (confirmed_spellings or {}).items():
        wrong_text = str(wrong or "").strip()
        correct_text = str(correct or "").strip()
        if not wrong_text or not correct_text:
            continue
        if wrong_text.lower() in LEGAL_TERMS:
            continue
        corrections[wrong_text] = correct_text

    # Layer 3 (fallback only): Deepgram keyterms, treated as canonical
    # capitalization for terms not already mapped by either layer above.
    for term in keyterms or []:
        clean_term = str(term or "").strip()
        if not clean_term:
            continue
        if clean_term.lower() in LEGAL_TERMS:
            continue
        corrections.setdefault(clean_term.lower(), clean_term)

    return corrections


def apply_morsons_rules(text: str) -> str:
    """Apply deterministic Morson's-style transcript rules.

    Order is significant:
    1. _fix_spacing collapses runs of whitespace.
    2. _normalize_em_dashes converts unicode and inconsistent ASCII
       em-dashes to canonical ` -- `. Runs after _fix_spacing so any
       pre-existing whitespace anomalies are settled first.
    3. _fix_sentence_start uppercases the first letter and spells out
       sentence-initial digits 1-10 per Morson's Rule 170.
    4. _fix_ellipses normalizes `. . .` and `....` to `...`.
    5. _fix_stutters preserves repeated tokens with explicit spacing.
    6. _fix_short_answer_commas inserts editorial commas after
       'yes/no/well/so/now/correct' at the start of an answer and
       before conjunctions in long sentences.
    7. _fix_ending_punctuation defaults missing terminal punctuation
       to `.`. Never strips fillers.
    """
    text = _fix_spacing(text)
    text = _normalize_em_dashes(text)
    text = _fix_sentence_start(text)
    text = _fix_small_numbers(text)
    text = _fix_ellipses(text)
    text = _fix_stutters(text)
    text = _fix_short_answer_commas(text)
    text = _fix_ending_punctuation(text)
    return text


def apply_corrections(
    blocks: list[TranscriptBlock],
    *,
    confirmed_spellings: dict | None = None,
    keyterms: list[str] | None = None,
) -> list[TranscriptBlock]:
    """Apply deterministic text-only corrections to transcript blocks."""
    corrections = _build_corrections_map(confirmed_spellings, keyterms)
    corrected: list[TranscriptBlock] = []
    for block in blocks:
        corrected_text = apply_proper_noun_corrections(block.text, corrections)
        corrected_text = apply_morsons_rules(corrected_text)
        if str(corrected_text).strip().lower().startswith("objection"):
            corrected_text = normalize_objection_line(corrected_text)
        if looks_like_parenthetical(corrected_text):
            corrected_text = normalize_parenthetical_line(corrected_text)
        corrected.append(
            TranscriptBlock(
                speaker=str(block.speaker or "").strip(),
                text=corrected_text,
                type=block.type,
                source_type=block.source_type,
                examiner=block.examiner,
                words=block.words,
            )
        )
    return corrected


def normalize_text_blocks(
    blocks: list[TranscriptBlock],
    *,
    confirmed_spellings: dict | None = None,
    keyterms: list[str] | None = None,
) -> list[TranscriptBlock]:
    """Compatibility alias for the corrections stage."""
    return apply_corrections(
        blocks,
        confirmed_spellings=confirmed_spellings,
        keyterms=keyterms,
    )
