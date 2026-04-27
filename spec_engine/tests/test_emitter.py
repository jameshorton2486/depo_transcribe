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

    assert "\tQ.\tDid you see that?" in result
    assert "\tA.\tYes." in result
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
    assert "\tQ.\tDid you see it?" in result
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


# ── Phase F — Q./A. line format change to tab-tab (reporter direction 2026-04-27)
# These tests pin the new format contract: Q./A. lines emit a tab character
# (not two literal spaces) between the label and the text. The change keeps
# the SP line format unchanged. See CLAUDE.md §18 and
# docs/transcription_standards/depo_pro_style.md §3 (UFM 2.11).


class TestQALineFormat:

    def _emit_q_block(self, text: str = "Did you go there?") -> str:
        blocks = [Block(text=text, block_type=BlockType.QUESTION, speaker_id=2)]
        return emit_blocks(blocks)

    def _emit_a_block(self, text: str = "Yes.") -> str:
        blocks = [Block(text=text, block_type=BlockType.ANSWER, speaker_id=1)]
        return emit_blocks(blocks)

    def test_q_line_uses_tab_after_period(self):
        result = self._emit_q_block("Did you go there?")
        # New format: \tQ.\ttext
        assert "\tQ.\tDid you go there?" in result

    def test_a_line_uses_tab_after_period(self):
        result = self._emit_a_block("Yes, sir.")
        # New format: \tA.\ttext
        assert "\tA.\tYes, sir." in result

    def test_q_line_no_double_spaces_after_period(self):
        # Regression guard against the old form ever returning. The
        # substring "\tQ.  " (tab + Q. + two literal spaces) must NOT
        # appear anywhere in the emitter output once Phase F has
        # landed. If a future patch reverts to the two-space form,
        # this test fails.
        result = self._emit_q_block("Did you go there?")
        assert "\tQ.  " not in result
        # And confirm the same for A. while we're here.
        result_a = self._emit_a_block("Yes, sir.")
        assert "\tA.  " not in result_a

    def test_sp_line_format_unchanged(self):
        # Hard-stop guard. The SP line format remains the three-tab
        # indent + LABEL: + two literal spaces + text. Phase F was
        # explicitly scoped to Q./A. — SP must be unaffected.
        blocks = [
            Block(
                text="Please raise your right hand.",
                block_type=BlockType.SPEAKER,
                speaker_id=4,
                speaker_name="THE REPORTER",
            ),
        ]
        result = emit_blocks(blocks)
        # SP form is \t\t\tLABEL:  text (three tabs + label + colon
        # + two SPACES + text). The two-space construction here is
        # unchanged and intentional.
        assert "\t\t\tTHE REPORTER:  Please raise your right hand." in result
        # Defensive: SP line must NOT have been converted to a tab
        # form by a stray over-broad edit.
        assert "\t\t\tTHE REPORTER:\t" not in result
