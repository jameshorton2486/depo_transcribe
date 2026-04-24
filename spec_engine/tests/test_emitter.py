from spec_engine.emitter import emit_blocks
from spec_engine.models import Block, BlockType


def test_emit_blocks_formats_question_answer_and_speaker_lines():
    blocks = [
        Block(text="Did you see that?", block_type=BlockType.QUESTION, speaker_id=2),
        Block(text="Yes.", block_type=BlockType.ANSWER, speaker_id=1),
        Block(
            text="Please raise your right hand.",
            block_type=BlockType.SPEAKER,
            speaker_id=4,
            speaker_name="THE REPORTER",
        ),
    ]

    result = emit_blocks(blocks)

    assert "\tQ.  Did you see that?" in result
    assert "\tA.  Yes." in result
    assert "\t\t\tTHE REPORTER:  Please raise your right hand." in result


def test_emit_blocks_avoids_duplicate_prefixed_speaker_labels():
    blocks = [
        Block(
            text="THE REPORTER:  Please raise your right hand.",
            block_type=BlockType.SPEAKER,
            speaker_id=4,
            speaker_name="THE REPORTER",
        )
    ]

    result = emit_blocks(blocks)

    assert result == "\t\t\tTHE REPORTER:  Please raise your right hand."


def test_emit_blocks_normalizes_the_court_reporter_label():
    blocks = [
        Block(
            text="THE COURT REPORTER:  We are on the record.",
            block_type=BlockType.SPEAKER,
            speaker_id=4,
            speaker_name="THE COURT REPORTER",
        )
    ]

    result = emit_blocks(blocks)

    assert result == "\t\t\tTHE REPORTER:  We are on the record."


def test_emit_blocks_suppresses_label_on_consecutive_same_speaker_blocks():
    blocks = [
        Block(
            text="Have you done anything that would affect your testimony?",
            block_type=BlockType.SPEAKER,
            speaker_id=2,
            speaker_name="MR. GONZALEZ",
        ),
        Block(
            text="Alright, Peter. Can you tell me your full name?",
            block_type=BlockType.SPEAKER,
            speaker_id=2,
            speaker_name="MR. GONZALEZ",
        ),
    ]

    result = emit_blocks(blocks)
    lines = result.split("\n")

    assert lines[0] == (
        "\t\t\tMR. GONZALEZ:  Have you done anything that would "
        "affect your testimony?"
    )
    assert lines[1] == (
        "\t\t\tAlright, Peter. Can you tell me your full name?"
    )


def test_emit_blocks_resets_speaker_chain_after_question():
    blocks = [
        Block(
            text="Let me start here.",
            block_type=BlockType.SPEAKER,
            speaker_id=2,
            speaker_name="MR. GONZALEZ",
        ),
        Block(
            text="Did you see it?",
            block_type=BlockType.QUESTION,
            speaker_id=2,
        ),
        Block(
            text="Another colloquy sentence.",
            block_type=BlockType.SPEAKER,
            speaker_id=2,
            speaker_name="MR. GONZALEZ",
        ),
    ]

    result = emit_blocks(blocks)

    assert "\t\t\tMR. GONZALEZ:  Let me start here." in result
    assert "\tQ.  Did you see it?" in result
    assert "\t\t\tMR. GONZALEZ:  Another colloquy sentence." in result


def test_emit_blocks_re_emits_label_when_speaker_changes():
    blocks = [
        Block(
            text="First speaker line.",
            block_type=BlockType.SPEAKER,
            speaker_id=2,
            speaker_name="MR. GONZALEZ",
        ),
        Block(
            text="Opposing counsel response.",
            block_type=BlockType.SPEAKER,
            speaker_id=3,
            speaker_name="MS. SMITH",
        ),
    ]

    result = emit_blocks(blocks)

    assert "\t\t\tMR. GONZALEZ:  First speaker line." in result
    assert "\t\t\tMS. SMITH:  Opposing counsel response." in result
