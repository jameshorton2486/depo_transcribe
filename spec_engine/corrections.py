"""Text normalization only for deterministic transcript enforcement."""

from __future__ import annotations

import re

from .models import TranscriptBlock

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
    "11": "Eleven",
    "12": "Twelve",
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


def _fix_em_dashes(text: str) -> str:
    text = re.sub(r"\s?--\s?", "  ", text)
    return re.sub(r"\s-\s", "  ", text)


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
    text = re.sub(r"(?:,\s*)?(you know|uh|um)\s*$", "", text, flags=re.IGNORECASE)
    text = text.rstrip()

    if not re.search(r"[.?!]$", text):
        if text.lower().startswith(_QUESTION_STARTERS):
            text += "?"
        else:
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
    corrections: dict[str, str] = {}

    for wrong, correct in (confirmed_spellings or {}).items():
        wrong_text = str(wrong or "").strip()
        correct_text = str(correct or "").strip()
        if not wrong_text or not correct_text:
            continue
        if wrong_text.lower() in LEGAL_TERMS:
            continue
        corrections[wrong_text] = correct_text

    for term in keyterms or []:
        clean_term = str(term or "").strip()
        if not clean_term:
            continue
        if clean_term.lower() in LEGAL_TERMS:
            continue
        corrections.setdefault(clean_term.lower(), clean_term)

    return corrections


def apply_morsons_rules(text: str) -> str:
    """Apply deterministic Morson's-style transcript rules."""
    text = _fix_spacing(text)
    text = _fix_sentence_start(text)
    text = _fix_ellipses(text)
    text = _fix_em_dashes(text)
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
        corrected.append(
            TranscriptBlock(
                speaker=str(block.speaker or "").strip(),
                text=apply_morsons_rules(
                    apply_proper_noun_corrections(block.text, corrections)
                ),
                type=block.type,
                source_type=block.source_type,
                examiner=block.examiner,
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
