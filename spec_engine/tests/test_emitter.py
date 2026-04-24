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
