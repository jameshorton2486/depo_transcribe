import pytest

from spec_engine.classifier import classify_blocks
from spec_engine.qa_fixer import enforce_structure


def test_directive_sets_examiner_for_subsequent_questions():
    classified = classify_blocks(
        [
            {"speaker": "speaker 1", "text": "BY MS. MALONEY:", "type": "paragraph"},
            {"speaker": "speaker 1", "text": "\tQ.\tPlease state your name.", "type": "paragraph"},
            {"speaker": "speaker 2", "text": "\tA.\tBianca Caram.", "type": "paragraph"},
        ]
    )
    fixed = enforce_structure(classified)
    assert fixed[1].examiner == "MS. MALONEY"


def test_orphan_answer_raises():
    classified = classify_blocks(
        [
            {"speaker": "speaker 2", "text": "\tA.\tYes.", "type": "paragraph"},
        ]
    )
    with pytest.raises(ValueError, match="orphan answers"):
        enforce_structure(classified)


def test_short_followup_after_question_is_coerced_to_answer():
    classified = classify_blocks(
        [
            {"speaker": "speaker 1", "text": "\tQ.\tDid you go there?", "type": "paragraph"},
            {"speaker": "speaker 2", "text": "Yes.", "type": "paragraph"},
        ]
    )
    fixed = enforce_structure(classified)
    assert fixed[0].type == "question"
    assert fixed[1].type == "answer"
