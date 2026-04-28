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
    # Phase G — emit_blocks now joins with "\n\n" (blank line between
    # blocks). Split on that to get block-level chunks; .split("\n")
    # would yield ["block1", "", "block2", ...] with empty strings
    # between content lines.
    blocks_out = result.split("\n\n")

    assert blocks_out[0] == (
        "\t\t\tMR. GONZALEZ:  Have you done anything that would "
        "affect your testimony?"
    )
    assert blocks_out[1] == (
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


# ── Q./A. line format — one tab + label + two literal spaces + text.
# This is the correct Texas UFM format. The reporter (Miah Bardot) confirmed
# 2026-04-28 after a brief 2026-04-27 entry that mandated two tabs was found
# to be incorrect and reverted. SP line format is unaffected. See CLAUDE.md §18.


class TestQALineFormat:

    def _emit_q_block(self, text: str = "Did you go there?") -> str:
        blocks = [Block(text=text, block_type=BlockType.QUESTION, speaker_id=2)]
        return emit_blocks(blocks)

    def _emit_a_block(self, text: str = "Yes.") -> str:
        blocks = [Block(text=text, block_type=BlockType.ANSWER, speaker_id=1)]
        return emit_blocks(blocks)

    def test_q_line_uses_two_spaces_after_period(self):
        result = self._emit_q_block("Did you go there?")
        # Correct format: \tQ.  text  (one tab, Q., two literal spaces)
        assert "\tQ.  Did you go there?" in result

    def test_a_line_uses_two_spaces_after_period(self):
        result = self._emit_a_block("Yes, sir.")
        # Correct format: \tA.  text  (one tab, A., two literal spaces)
        assert "\tA.  Yes, sir." in result

    def test_q_line_does_not_use_tab_after_period(self):
        # Regression guard against the brief 2026-04-27 two-tab form
        # accidentally returning. Q. must be followed by two literal
        # spaces, NOT a tab character.
        result = self._emit_q_block("Did you go there?")
        assert "\tQ.\t" not in result
        # Same for A.
        result_a = self._emit_a_block("Yes, sir.")
        assert "\tA.\t" not in result_a

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


# ── Phase G — plain-text inter-block spacing ─────────────────────────────────
# emit_blocks now joins blocks with "\n\n" (blank line) instead of "\n".
# Reporter convention is visual separation between speaker turns. The
# DOCX path is unaffected — paragraph spacing in DOCX is handled by
# _set_paragraph_format. This is plain-text-only.


def test_emit_blocks_separates_blocks_with_blank_line():
    blocks = [
        Block(text="Did you go there?", block_type=BlockType.QUESTION, speaker_id=2),
        Block(text="Yes, sir.", block_type=BlockType.ANSWER, speaker_id=1),
    ]
    result = emit_blocks(blocks)
    # Two blocks joined with one blank line between them.
    assert "\n\n" in result
    # And exactly one — no triple-newline regression.
    assert "\n\n\n" not in result
    # Specifically: the Q line ends, then a blank line, then the A line.
    assert "\tQ.  Did you go there?\n\n\tA.  Yes, sir." in result


def test_emit_blocks_normalizes_nonbreaking_spaces():
    blocks = [
        Block(text="Did\u00a0you\u202fgo there?", block_type=BlockType.QUESTION, speaker_id=2),
    ]
    result = emit_blocks(blocks)
    assert result == "\tQ.\tDid you go there?"


# ── Phase H — DOCX double-spacing regression guard ───────────────────────────
# Verifies WD_LINE_SPACING.DOUBLE reaches every body-emitter paragraph type
# (Q, A, SP, SP continuation, PAREN, FLAG, header, BY, plain, plus every
# emit_line_numbered variant). Body-testimony rule per UFM 2.13 (style guide
# §12.1). Out of scope for this guard: admin pages under spec_engine/pages/
# (corrections_log, post_record) and table-cell layouts (_lined_page) which
# intentionally use different spacing and are not under UFM 2.13.


def test_all_emitted_paragraphs_use_double_spacing():
    from docx.enum.text import WD_LINE_SPACING

    from spec_engine.emitter import (
        QAPairTracker,
        LineNumberTracker,
        create_document,
        emit_q_line,
        emit_a_line,
        emit_sp_line,
        emit_pn_line,
        emit_flag_line,
        emit_header_line,
        emit_by_line,
        emit_plain_line,
        emit_line_numbered,
    )
    from spec_engine.models import LineType

    doc = create_document()

    # Body emitters that go through _set_paragraph_format
    emit_q_line(doc, "Did you go there?")
    emit_a_line(doc, "Yes, sir.")
    emit_sp_line(doc, "MR. GARCIA:  Objection. Form.")
    emit_sp_line(doc, "\t\t\tThis is a same-speaker continuation block.")
    emit_pn_line(doc, "(Whereupon, a recess was had.)")
    emit_flag_line(doc, "[SCOPIST: FLAG 1: verify timestamp]")
    emit_header_line(doc, "DIRECT EXAMINATION")
    emit_by_line(doc, "BY MR. GARCIA:")
    emit_plain_line(doc, "Plain transcript text without label.")

    # emit_line_numbered has its own line-spacing setup site (does not
    # call _set_paragraph_format) — verify each variant separately so a
    # future change can't drop DOUBLE on one variant silently.
    tracker = LineNumberTracker(start_page=3)
    qa_tracker = QAPairTracker()
    for line_type, text in [
        (LineType.Q, "Numbered Q line."),
        (LineType.A, "Numbered A line."),
        (LineType.SP, "MR. GARCIA:  Numbered SP line."),
        (LineType.PN, "(Numbered parenthetical.)"),
        (LineType.PLAIN, "Numbered plain line."),
    ]:
        emit_line_numbered(doc, line_type, text, tracker, qa_tracker)

    # Every paragraph in the test doc must have DOUBLE spacing — no
    # silent regressions to SINGLE / unset / EXACTLY / etc.
    bad = []
    for i, para in enumerate(doc.paragraphs):
        rule = para.paragraph_format.line_spacing_rule
        if rule != WD_LINE_SPACING.DOUBLE:
            bad.append((i, rule, para.text[:50]))

    assert not bad, (
        "Some paragraphs are missing WD_LINE_SPACING.DOUBLE:\n"
        + "\n".join(
            f"  paragraph[{i}] rule={rule!r} text={text!r}"
            for i, rule, text in bad
        )
    )
    # Defensive: at least one paragraph from each major branch should
    # have landed (14 emitters above, expect at least that many).
    assert len(doc.paragraphs) >= 14
