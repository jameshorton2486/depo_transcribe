from spec_engine.models import Block
from spec_engine.speaker_intelligence import enforce_qa_sequence, infer_speaker_roles
from spec_engine.speaker_resolver import ROLE_ATTORNEY, ROLE_REPORTER, ROLE_WITNESS


def test_infer_speaker_roles_marks_question_as_attorney():
    blocks = [Block(text="Did you see the accident?", speaker_id=7, raw_text="", meta={})]
    cfg = {"speaker_map": {}, "examining_attorney_id": 2}

    result = infer_speaker_roles(blocks, cfg)

    assert result[0].speaker_role == ROLE_ATTORNEY


def test_infer_speaker_roles_marks_short_answer_as_witness():
    blocks = [Block(text="Yes.", speaker_id=7, raw_text="", meta={})]
    cfg = {"speaker_map": {}, "witness_id": 1}

    result = infer_speaker_roles(blocks, cfg)

    assert result[0].speaker_role == ROLE_WITNESS


def test_infer_speaker_roles_marks_oath_as_reporter():
    blocks = [Block(text="Do you swear to tell the truth?", speaker_id=7, raw_text="", meta={})]
    cfg = {"speaker_map": {}, "witness_id": 1}

    result = infer_speaker_roles(blocks, cfg)

    assert result[0].speaker_role == ROLE_REPORTER


def test_enforce_qa_sequence_splits_inline_question_and_answer():
    block = Block(
        text="Correct? Correct.",
        speaker_id=2,
        raw_text="Correct? Correct.",
        speaker_role=ROLE_ATTORNEY,
        speaker_name="MR. SMITH",
        meta={},
    )
    cfg = {
        "speaker_map": {1: "THE WITNESS", 2: "MR. SMITH"},
        "witness_id": 1,
        "examining_attorney_id": 2,
    }

    result = enforce_qa_sequence([block], cfg)

    assert len(result) == 2
    assert result[0].text == "Correct?"
    assert result[0].speaker_role == ROLE_ATTORNEY
    assert result[1].text == "Correct."
    assert result[1].speaker_role == ROLE_WITNESS
