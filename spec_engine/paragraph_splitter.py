"""
Deterministic paragraph splitting helpers for transcript blocks.
"""

from __future__ import annotations

import re


SENTENCE_SPLIT_RE = re.compile(r'(?<=[.?!])\s+(?=[A-Z])')
ABBREVIATION_PLACEHOLDER = "__DOT__"
PROTECTED_ABBREVIATIONS = (
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "Mister.",
    "Doctor.",
    "Reverend.",
    "Professor.",
)
# Single-letter initials inside names — "Holly D. Scholl", "J. K. Rowling".
# These look identical to a sentence terminator (single uppercase letter,
# period, whitespace, capital) so the splitter mistakes them for sentence
# breaks. The lookahead (?=\s+[A-Z]) avoids consuming the trailing capital,
# so consecutive initials (J. K. Rowling) are all caught in a single
# re.sub pass without iteration.
INITIAL_RE = re.compile(r'\b([A-Z])\.(?=\s+[A-Z])')

SHORT_ANSWER_SET = {
    "Yes.",
    "No.",
    "Correct.",
    "Okay.",
    "I do.",
    "I don't.",
    "That's right.",
}


def split_block_text(text: str) -> list[str]:
    """
    Split transcript block text into smaller logical segments.

    Handles:
    - sentence splitting
    - embedded Q/A patterns such as "Correct? Correct."
    """
    if not text:
        return [""]

    stripped = text.strip()
    if len(stripped) < 120:
        return [stripped]

    protected = stripped
    for abbreviation in PROTECTED_ABBREVIATIONS:
        protected = protected.replace(abbreviation, abbreviation.replace(".", ABBREVIATION_PLACEHOLDER))

    # Protect single-letter initials AFTER the abbreviation pass so the
    # "Dr." / "Mr." replacements are already in placeholder form and
    # can't be re-matched here as "D." / "M." with a capital lookahead.
    protected = INITIAL_RE.sub(rf"\1{ABBREVIATION_PLACEHOLDER}", protected)

    sentences = [
        sentence.replace(ABBREVIATION_PLACEHOLDER, ".")
        for sentence in SENTENCE_SPLIT_RE.split(protected)
    ]
    result: list[str] = []
    index = 0

    while index < len(sentences):
        current = sentences[index].strip()

        if index + 1 < len(sentences):
            next_sentence = sentences[index + 1].strip()
            if current.endswith("?") and next_sentence in SHORT_ANSWER_SET:
                result.append(current)
                result.append(next_sentence)
                index += 2
                continue

        result.append(current)
        index += 1

    return result
