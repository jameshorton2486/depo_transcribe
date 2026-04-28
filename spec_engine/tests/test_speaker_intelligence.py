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


def test_infer_speaker_roles_uses_sequence_for_unknown_answer_and_marks_verification():
    blocks = [
        Block(
            text="Would you state your name for the record?",
            speaker_id=2,
            raw_text="",
            speaker_role=ROLE_ATTORNEY,
            speaker_name="MS. MALONEY",
            meta={},
        ),
        Block(text="I reviewed the charts.", speaker_id=7, raw_text="", meta={}),
    ]
    cfg = {
        "speaker_map": {1: "THE WITNESS", 2: "MS. MALONEY"},
        "witness_id": 1,
        "examining_attorney_id": 2,
    }

    result = infer_speaker_roles(blocks, cfg)

    assert result[1].speaker_role == ROLE_WITNESS
    assert result[1].speaker_id == 1
    assert "verification_flags" in result[1].meta
    assert "verify from audio" in result[1].meta["verification_flags"][0]


def test_enforce_qa_sequence_relabels_attorney_labeled_answer_and_marks_verification():
    blocks = [
        Block(
            text="Have you reviewed the chart?",
            speaker_id=2,
            raw_text="",
            speaker_role=ROLE_ATTORNEY,
            speaker_name="MS. MALONEY",
            meta={},
        ),
        Block(
            text="I reviewed the charts.",
            speaker_id=2,
            raw_text="",
            speaker_role=ROLE_ATTORNEY,
            speaker_name="MS. MALONEY",
            meta={},
        ),
    ]
    cfg = {
        "speaker_map": {1: "THE WITNESS", 2: "MS. MALONEY"},
        "witness_id": 1,
        "examining_attorney_id": 2,
    }

    result = enforce_qa_sequence(blocks, cfg)

    assert result[1].speaker_role == ROLE_WITNESS
    assert result[1].speaker_id == 1
    assert "verification_flags" in result[1].meta
    assert "verify from audio" in result[1].meta["verification_flags"][0]


def test_enforce_qa_sequence_relabels_witness_labeled_question_and_marks_verification():
    blocks = [
        Block(
            text="Yes.",
            speaker_id=1,
            raw_text="",
            speaker_role=ROLE_WITNESS,
            speaker_name="THE WITNESS",
            meta={},
        ),
        Block(
            text="Would you please state your full name for the record?",
            speaker_id=1,
            raw_text="",
            speaker_role=ROLE_WITNESS,
            speaker_name="THE WITNESS",
            meta={},
        ),
    ]
    cfg = {
        "speaker_map": {1: "THE WITNESS", 2: "MS. MALONEY"},
        "witness_id": 1,
        "examining_attorney_id": 2,
    }

    result = enforce_qa_sequence(blocks, cfg)

    assert result[1].speaker_role == ROLE_ATTORNEY
    assert result[1].speaker_id == 2
    assert "verification_flags" in result[1].meta
    assert "verify from audio" in result[1].meta["verification_flags"][0]
