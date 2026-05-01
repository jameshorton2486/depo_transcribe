"""UFM RULES (Uniform Format Manual)

This module defines deterministic formatting and structural rules
derived from the Uniform Format Manual (UFM) for Texas Reporters' Records.

IMPORTANT:
- These rules are NOT dynamically loaded from PDFs
- They are explicitly encoded for deterministic, testable behavior
- They are applied across the pipeline in different stages:

PIPELINE USAGE:
- classifier.py detects Q/A (LOOSE detection)
- qa_fixer.py enforces Q/A sequence rules
- emitter.py enforces FINAL strict formatting

Source Reference:
- UFM Section 2.7 (Questions and Answers)
- UFM Section 2.102.11 (Tab settings)
- UFM Section 3.22 (Identification of Speakers)
"""

UFM_RULES = {
    "qa_format": "\tQ.\t{text}",
    "answer_format": "\tA.\t{text}",
    "tab_stops": [0.5, 1.0, 1.5],
    "speaker_label_format": "LEFT_ALIGNED",
    "speaker_label_uppercase": True,
    "verbatim_required": True,
    "filler_words_preserved": True,
    "require_qa_sequence": True,
    "no_orphan_answers": True,
    "no_nested_qa": True,
}


def is_question_loose(line: str) -> bool:
    """Detect question lines in intermediate pipeline stages."""
    return line.lstrip().startswith("Q.")


def is_answer_loose(line: str) -> bool:
    """Detect answer lines in intermediate pipeline stages."""
    return line.lstrip().startswith("A.")


def is_valid_question(line: str) -> bool:
    """Strict UFM-compliant question format."""
    return line.startswith("\tQ.\t")


def is_valid_answer(line: str) -> bool:
    """Strict UFM-compliant answer format."""
    return line.startswith("\tA.\t")


def has_valid_qa_format(line: str) -> bool:
    """Check if line is valid Q/A in final format."""
    return is_valid_question(line) or is_valid_answer(line)
