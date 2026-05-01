"""UFM RULES (Uniform Format Manual)

This module defines deterministic formatting and structural rules
derived from the Uniform Format Manual (UFM) for Texas Reporters' Records.

IMPORTANT:
- These rules are NOT dynamically loaded from PDFs
- They are explicitly encoded for deterministic, testable behavior
- They are applied across the pipeline in different stages:

PIPELINE USAGE:
- classifier.py  detects Q/A (LOOSE detection)
- qa_fixer.py  enforces Q/A sequence rules
- emitter.py  enforces FINAL strict formatting

Source Reference:
- UFM Section 2.7 (Questions and Answers)
- UFM Section 2.102.11 (Tab settings)
- UFM Section 3.22 (Identification of Speakers)
"""

# ================================
# CORE FORMATTING RULES
# ================================

UFM_RULES = {
    # Required Q/A format (STRICT - enforced at emitter stage)
    "qa_format": "\tQ.\t{text}",
    "answer_format": "\tA.\t{text}",
    # Tab stop expectations (used for DOCX / layout layer)
    "tab_stops": [0.5, 1.0, 1.5],
    # Speaker formatting rules
    "speaker_label_format": "LEFT_ALIGNED",
    "speaker_label_uppercase": True,
    # Verbatim rules (CRITICAL for legal transcripts)
    "verbatim_required": True,
    "filler_words_preserved": True,
    # Structural enforcement flags (used by qa_fixer)
    "require_qa_sequence": True,
    "no_orphan_answers": True,
    "no_nested_qa": True,
}


# ================================
# DETECTION HELPERS (LOOSE)
# ================================

def is_question_loose(line: str) -> bool:
    """
    Detect question lines in intermediate pipeline stages.

    Accepts:
    - 'Q. text'
    - '   Q. text'
    """
    return line.lstrip().startswith("Q.")


def is_answer_loose(line: str) -> bool:
    """
    Detect answer lines in intermediate pipeline stages.
    """
    return line.lstrip().startswith("A.")


# ================================
# VALIDATION HELPERS (STRICT)
# ================================

def is_valid_question(line: str) -> bool:
    """
    Strict UFM-compliant question format.
    Used at final output validation stage.
    """
    return line.startswith("\tQ.\t")


def is_valid_answer(line: str) -> bool:
    """
    Strict UFM-compliant answer format.
    """
    return line.startswith("\tA.\t")


def has_valid_qa_format(line: str) -> bool:
    """
    Check if line is valid Q/A in final format.
    """
    return is_valid_question(line) or is_valid_answer(line)
