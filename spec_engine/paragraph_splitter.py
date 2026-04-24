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
)

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
