from spec_engine.models import Block, BlockType
from spec_engine.flag_rules import generate_scopist_flags


def test_generate_scopist_flags_inserts_flag_block_after_garbled_case_number():
    block = Block(
        text="case number $ 1 2 3 4",
        raw_text="case number $ 1 2 3 4",
        speaker_id=1,
        meta={},
    )

    result = generate_scopist_flags([block])

    assert len(result) == 2
    assert result[0].text == "case number $ 1 2 3 4"
    assert result[1].block_type == BlockType.FLAG
    assert result[1].text == "[SCOPIST: FLAG 1: possible garbled number]"


def test_generate_scopist_flags_preserves_original_blocks():
    block = Block(
        text="plain text",
        raw_text="plain text",
        speaker_id=1,
        meta={},
    )

    result = generate_scopist_flags([block])

    assert result == [block]


def test_generate_scopist_flags_inserts_verification_flag_from_block_meta():
    block = Block(
        text="I reviewed the charts.",
        raw_text="I reviewed the charts.",
        speaker_id=1,
        block_type=BlockType.ANSWER,
        meta={"verification_flags": ["speaker role inferred as witness from Q/A sequence — verify from audio"]},
    )

    result = generate_scopist_flags([block])

    assert len(result) == 2
    assert result[0] is block
    assert result[1].block_type == BlockType.FLAG
    assert "speaker role inferred as witness from Q/A sequence" in result[1].text
