from __future__ import annotations

import pytest

from pipeline.assembler import ROLE_SEQUENCE
from spec_engine.classifier import ClassifierState, classify_block, classify_blocks
from spec_engine.models import Block, BlockType, JobConfig, LineType
from spec_engine.qa_fixer import (
    _merge_orphaned_continuations,
    _remove_near_duplicate_blocks,
    fix_qa_structure,
)


def test_role_sequence_includes_videographer_and_interpreter():
    assert "THE VIDEOGRAPHER" in ROLE_SEQUENCE
    assert "THE INTERPRETER" in ROLE_SEQUENCE


def test_videographer_after_question_is_parenthetical():
    q = Block(
        speaker_id=2,
        text="Did you go there?",
        raw_text="",
        speaker_role="EXAMINING_ATTORNEY",
        speaker_name="MR. ALLAN",
        block_type=BlockType.QUESTION,
    )
    vg = Block(
        speaker_id=0,
        text="We are back on the record.",
        raw_text="",
        speaker_role="",
        speaker_name="THE VIDEOGRAPHER",
    )
    results = classify_blocks([q, vg])
    assert results[1].block_type == BlockType.PARENTHETICAL


def test_remote_oath_variants_match():
    cfg = JobConfig.default_perez_ugalde()
    cfg.speaker_map_verified = True
    state = ClassifierState()
    block = Block(
        speaker_id=0,
        text="Would you raise your hand if you are able and do you affirm to tell the truth?",
        raw_text="",
    )
    results = classify_block(block, cfg, state, block_index=0)
    assert any(line_type == LineType.HEADER for line_type, _ in results)
    assert any("witness was sworn" in text.lower() for _, text in results)


def test_imperative_question_only_for_examiner():
    blocks = [
        Block(
            speaker_id=2,
            text="Tell me about that day.",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MR. ALLAN",
        ),
        Block(
            speaker_id=3,
            text="Tell you the truth, I never saw him.",
            raw_text="",
            speaker_role="OPPOSING_COUNSEL",
            speaker_name="MR. BOYCE",
        ),
    ]
    results = classify_blocks(blocks)
    assert results[0].block_type == BlockType.QUESTION
    assert results[1].block_type == BlockType.COLLOQUY


def test_exhibit_only_block_returns_only_parenthetical():
    cfg = JobConfig.default_perez_ugalde()
    cfg.speaker_map_verified = True
    state = ClassifierState()
    block = Block(
        speaker_id=2,
        text="I am handing you what has been marked as Exhibit 15.",
        raw_text="",
    )
    results = classify_block(block, cfg, state, block_index=0)
    assert all(line_type == LineType.PN for line_type, _ in results)


def test_exhibit_plus_question_returns_parenthetical_and_question():
    cfg = JobConfig.default_perez_ugalde()
    cfg.speaker_map_verified = True
    state = ClassifierState()
    block = Block(
        speaker_id=2,
        text="I am handing you Exhibit 16. Did you fill this out?",
        raw_text="",
    )
    results = classify_block(block, cfg, state, block_index=0)
    line_types = [line_type for line_type, _ in results]
    assert LineType.PN in line_types
    assert LineType.Q in line_types


# ── Witness rhetorical question must not become Q. ──────────────────────────
# Previously, classifier.py:746-761 emitted (LineType.Q, text) when a witness
# block's text *looked like* a question (ended in "?", started with a question
# word, etc.) but had no embedded answer split. Witness rhetorical questions,
# tag questions ("right?", "you know?"), and quoted speech ending in "?" are
# testimony — they must not initiate a new Q/A pair, because the next
# attorney line then gets read as a witness answer.


def test_witness_rhetorical_question_emits_answer_not_question():
    cfg = JobConfig.default_perez_ugalde()
    cfg.speaker_map_verified = True
    state = ClassifierState()
    block = Block(
        speaker_id=cfg.witness_id,
        text="He came in, you know?",
        raw_text="",
    )
    results = classify_block(block, cfg, state, block_index=0)
    assert all(line_type == LineType.A for line_type, _ in results), (
        f"Expected all A lines, got "
        f"{[lt.name for lt, _ in results]}"
    )


def test_witness_tag_question_does_not_set_qa_tracker_to_question():
    # If the rhetorical-question fallthrough wrongly emitted Q, the next
    # attorney block would be (mis)read as an "answer after a Q." The
    # qa_tracker state must reflect "we are not waiting on an answer."
    cfg = JobConfig.default_perez_ugalde()
    cfg.speaker_map_verified = True
    state = ClassifierState()
    block = Block(
        speaker_id=cfg.witness_id,
        text="I told him, right?",
        raw_text="",
    )
    classify_block(block, cfg, state, block_index=0)
    assert state.qa_tracker_last_was_q is False


def test_witness_question_starting_word_emits_answer():
    # _looks_like_question_text matches text starting with a question
    # word (who/what/when/etc.) even without a "?". Same fix path —
    # witness text → A.
    cfg = JobConfig.default_perez_ugalde()
    cfg.speaker_map_verified = True
    state = ClassifierState()
    block = Block(
        speaker_id=cfg.witness_id,
        text="Why would I lie about that.",  # starts with "why "
        raw_text="",
    )
    results = classify_block(block, cfg, state, block_index=0)
    assert all(line_type == LineType.A for line_type, _ in results)


def test_witness_normal_statement_still_emits_answer():
    # Sanity check — the unchanged path (witness text that doesn't look
    # like a question) still emits A.
    cfg = JobConfig.default_perez_ugalde()
    cfg.speaker_map_verified = True
    state = ClassifierState()
    block = Block(
        speaker_id=cfg.witness_id,
        text="Yes, sir.",
        raw_text="",
    )
    results = classify_block(block, cfg, state, block_index=0)
    assert all(line_type == LineType.A for line_type, _ in results)


def test_merge_orphaned_colloquy_continuation():
    b1 = Block(
        speaker_id=2,
        text="And I want to direct your attention",
        raw_text="",
        block_type=BlockType.COLLOQUY,
    )
    b2 = Block(
        speaker_id=2,
        text="to Exhibit 16.",
        raw_text="",
        block_type=BlockType.COLLOQUY,
    )
    merged = _merge_orphaned_continuations([b1, b2])
    assert len(merged) == 1
    assert "Exhibit 16" in merged[0].text


def test_remove_near_duplicate_blocks_keeps_longer_version():
    d1 = Block(
        speaker_id=1,
        text="I did not see any spill at that time.",
        raw_text="",
        block_type=BlockType.ANSWER,
        meta={"start": 10.0},
    )
    d2 = Block(
        speaker_id=1,
        text="I did not see any spill at that time really.",
        raw_text="",
        block_type=BlockType.ANSWER,
        meta={"start": 10.4},
    )
    deduped = _remove_near_duplicate_blocks([d1, d2])
    assert len(deduped) == 1
    assert deduped[0].text == d2.text


def test_remove_near_duplicate_blocks_keeps_similar_text_when_timing_far_apart():
    d1 = Block(
        speaker_id=1,
        text="I did not see any spill at that time.",
        raw_text="",
        block_type=BlockType.ANSWER,
        meta={"start": 10.0},
    )
    d2 = Block(
        speaker_id=1,
        text="I did not see any spill at that time really.",
        raw_text="",
        block_type=BlockType.ANSWER,
        meta={"start": 14.0},
    )

    deduped = _remove_near_duplicate_blocks([d1, d2])

    assert len(deduped) == 2


def test_fix_qa_structure_splits_merged_question_answer_question_sequence():
    cfg = JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MR. ALLAN"},
        witness_id=1,
        examining_attorney_id=2,
    )
    block = Block(
        speaker_id=2,
        speaker_name="MR. ALLAN",
        speaker_role="EXAMINING_ATTORNEY",
        block_type=BlockType.QUESTION,
        text="Is this the first motor vehicle accident you've been involved in? Yes, sir. Is this the first one where you were injured?",
        raw_text="",
    )

    result = fix_qa_structure([block], job_config=cfg)

    assert [b.block_type for b in result] == [
        BlockType.QUESTION, BlockType.ANSWER, BlockType.QUESTION
    ]
    assert result[0].text == "Is this the first motor vehicle accident you've been involved in?"
    assert result[1].text == "Yes, sir."
    assert result[1].speaker_id == 1
    assert result[2].text == "Is this the first one where you were injured?"
    assert result[2].speaker_id == 2


def test_fix_qa_structure_preserves_examiner_continuation_after_short_answer():
    cfg = JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MR. ALLAN"},
        witness_id=1,
        examining_attorney_id=2,
    )
    block = Block(
        speaker_id=2,
        speaker_name="MR. ALLAN",
        speaker_role="EXAMINING_ATTORNEY",
        block_type=BlockType.QUESTION,
        text="Have you ever completed a deposition before? No. Just to go over a few things.",
        raw_text="",
    )

    result = fix_qa_structure([block], job_config=cfg)

    assert [b.block_type for b in result] == [
        BlockType.QUESTION, BlockType.ANSWER, BlockType.COLLOQUY
    ]
    assert result[0].text == "Have you ever completed a deposition before?"
    assert result[1].text == "No."
    assert result[1].speaker_id == 1
    assert result[2].text == "Just to go over a few things."
    assert result[2].speaker_id == 2


def test_fix_qa_structure_splits_answer_swallowing_next_question():
    cfg = JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MR. ALLAN"},
        witness_id=1,
        examining_attorney_id=2,
    )
    block = Block(
        speaker_id=1,
        speaker_name="THE WITNESS",
        speaker_role="WITNESS",
        block_type=BlockType.ANSWER,
        text="No, sir. Are you currently employed?",
        raw_text="",
    )

    result = fix_qa_structure([block], job_config=cfg)

    assert [b.block_type for b in result] == [BlockType.ANSWER, BlockType.QUESTION]
    assert result[0].text == "No, sir."
    assert result[0].speaker_id == 1
    assert result[1].text == "Are you currently employed?"
    assert result[1].speaker_id == 2


def test_fix_qa_structure_splits_answer_question_answer_chain():
    cfg = JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MR. ALLAN"},
        witness_id=1,
        examining_attorney_id=2,
    )
    block = Block(
        speaker_id=1,
        speaker_name="THE WITNESS",
        speaker_role="WITNESS",
        block_type=BlockType.ANSWER,
        text="Yes. Could you state your full name for the record, please? Matthew Allan Coger.",
        raw_text="",
    )

    result = fix_qa_structure([block], job_config=cfg)

    assert [b.block_type for b in result] == [
        BlockType.ANSWER, BlockType.QUESTION, BlockType.ANSWER
    ]
    assert result[0].text == "Yes."
    assert result[1].text == "Could you state your full name for the record, please?"
    assert result[1].speaker_id == 2
    assert result[2].text == "Matthew Allan Coger."
    assert result[2].speaker_id == 1


def test_fix_qa_structure_splits_answer_prefixed_question():
    """
    Step 3 / Case 1 final fragment: a QUESTION block whose first sentence is
    actually a witness reply ("I will. ...?"). split_answer_prefixed_questions
    should peel the answer off the front and leave the question.
    """
    cfg = JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MS. MALONEY"},
        witness_id=1,
        examining_attorney_id=2,
    )
    block = Block(
        speaker_id=2,
        speaker_name="MS. MALONEY",
        speaker_role="EXAMINING_ATTORNEY",
        block_type=BlockType.QUESTION,
        text="I will. Um, would you please state your full legal name for the record?",
        raw_text="",
    )

    result = fix_qa_structure([block], job_config=cfg)

    assert [b.block_type for b in result] == [BlockType.ANSWER, BlockType.QUESTION]
    assert result[0].text == "I will."
    assert result[0].speaker_id == 1
    assert result[1].text == "Um, would you please state your full legal name for the record?"
    assert result[1].speaker_id == 2


def test_fix_qa_structure_case1_full_chain_multi_pass_with_answer_prefixed_q():
    """
    Case 1 from the bleed trace: a single Q block contains three Q/A turns,
    the last of which leaves a witness reply ("I will.") fused to the next
    examiner question. After the patch:
      - 1st split_inline_answers peels off "Yes, I do."
      - 2nd split_inline_answers peels off "Yes. I will." (option-d keeps both
        sentences in the answer)
      - split_answer_prefixed_questions is not needed here because the prior
        pass already produced a clean Q tail.
    Expected shape: Q, A, Q, A, Q.
    """
    cfg = JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MS. MALONEY"},
        witness_id=1,
        examining_attorney_id=2,
    )
    block = Block(
        speaker_id=2,
        speaker_name="MS. MALONEY",
        speaker_role="EXAMINING_ATTORNEY",
        block_type=BlockType.QUESTION,
        text=(
            "my name is Michelle Maloney, I represent Hannah Kressman in this case. "
            "You understand that? Yes, I do. Okay. And Hannah goes by her maiden "
            "name now, Hannah Kuipers. If I refer to her as miss K. K. Will you "
            "understand who I'm talking about? Yes. I will. Um, would you please "
            "state your full legal name for the record?"
        ),
        raw_text="",
    )

    result = fix_qa_structure([block], job_config=cfg)

    types = [b.block_type for b in result]
    assert types == [
        BlockType.QUESTION, BlockType.ANSWER,
        BlockType.QUESTION, BlockType.ANSWER,
        BlockType.QUESTION,
    ]
    # Speaker round-trips correctly: examiner / witness / examiner / witness / examiner
    assert [b.speaker_id for b in result] == [2, 1, 2, 1, 2]
    # Multi-sentence answer kept together by option-d
    assert result[3].text == "Yes.  I will."


def test_fix_qa_structure_splits_witness_answer_with_transition_tail():
    """
    Case 4 from the bleed trace. A misdiarized witness ANSWER block contains
    a multi-sentence reply followed by a truncated examiner transition
    ("Okay. What about"). Option-d picks the latest answer-compatible
    boundary; the relaxed split_inline_questions_from_answers gate accepts
    transition-led continuations and emits them as COLLOQUY (the truncated
    fragment is not a complete question).
    """
    cfg = JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MS. MALONEY"},
        witness_id=1,
        examining_attorney_id=2,
    )
    block = Block(
        speaker_id=1,
        speaker_name="THE WITNESS",
        speaker_role="WITNESS",
        block_type=BlockType.ANSWER,
        text="Yes. I can access it. Okay. What about",
        raw_text="",
    )

    result = fix_qa_structure([block], job_config=cfg)

    assert [b.block_type for b in result] == [BlockType.ANSWER, BlockType.COLLOQUY]
    assert result[0].text == "Yes.  I can access it."
    assert result[0].speaker_id == 1
    assert result[1].text == "Okay.  What about"
    assert result[1].speaker_id == 2


def test_classify_blocks_examining_attorney_short_answer_after_question_is_rescued():
    """
    Step 1 regression: the previous guard `speaker_id != examining_attorney_id`
    in classifier._attorney_label_answer prevented short answers misdiarized
    onto the examining attorney from being re-attributed. After the patch,
    a 1-word "Yes." attributed to the examining attorney following a Q block
    is reclassified as ANSWER.
    """
    blocks = [
        Block(
            speaker_id=2,
            text="Are you a member of the Society for Maternal and Fetal Medicine?",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MS. MALONEY",
        ),
        Block(
            speaker_id=2,
            text="No.",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MS. MALONEY",
        ),
    ]

    results = classify_blocks(blocks, job_config=JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MS. MALONEY"},
        witness_id=1,
        examining_attorney_id=2,
        speaker_map_verified=True,
    ))

    assert results[0].block_type == BlockType.QUESTION
    assert results[1].block_type == BlockType.ANSWER


def test_classify_blocks_examining_attorney_non_answer_prefix_not_rescued():
    """
    Step 1 guardrail: the rescue path triggers only when
    _looks_like_answer_after_question returns True, which requires the text
    to start with an answer-token prefix (yes/no/right/correct/I do/etc.) or
    generic answer-start ("it's", "I'm", "my", ...). A Maloney transition
    that does NOT start with one of those — e.g. "Now let's move on." —
    must NOT be reclassified as an answer.

    This is the actual remaining guard after Step 1. Long examining-attorney
    transitions that DO start with an answer-token prefix (e.g.
    "Right. So tell me ...") are intentionally rescued under the trade-off
    the user accepted; the AI Pass 2 review is responsible for catching
    those false positives.
    """
    blocks = [
        Block(
            speaker_id=2,
            text="Did anything else happen that morning?",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MS. MALONEY",
        ),
        Block(
            speaker_id=2,
            text="Now let's move on to October second.",
            raw_text="",
            speaker_role="EXAMINING_ATTORNEY",
            speaker_name="MS. MALONEY",
        ),
    ]

    results = classify_blocks(blocks, job_config=JobConfig(
        speaker_map={1: "THE WITNESS", 2: "MS. MALONEY"},
        witness_id=1,
        examining_attorney_id=2,
        speaker_map_verified=True,
    ))

    assert results[0].block_type == BlockType.QUESTION
    # "Now ..." doesn't start with any answer-token prefix → rescue blocked.
    assert results[1].block_type != BlockType.ANSWER


def test_classify_blocks_witness_mislabel_question_becomes_question():
    blocks = [
        Block(
            speaker_id=1,
            text="Do you solemnly swear to tell the truth, the whole truth, and nothing but the truth so help you God? I do.",
            raw_text="",
            speaker_role="WITNESS",
            speaker_name="THE WITNESS",
        ),
    ]

    results = classify_blocks(blocks)

    assert results[0].block_type == BlockType.QUESTION


@pytest.mark.skip(reason="Imports JobConfigDialog from non-existent 'main' module — no equivalent in app.py")
def test_auto_fill_spellings_adds_reporter_variants(monkeypatch):
    pytest.importorskip("tkinter", reason="tkinter not available in headless environment")
    from main import JobConfigDialog

    class DummyVar:
        def __init__(self, value: str):
            self._value = value

        def get(self):
            return self._value

    class DummyBox:
        def __init__(self, value: str = ""):
            self.value = value

        def get(self, *_args):
            return self.value

        def delete(self, *_args):
            self.value = ""

        def insert(self, *_args):
            self.value = _args[-1]

    class DummyDialog:
        _parse_spellings = JobConfigDialog._parse_spellings
        _auto_fill_spellings = JobConfigDialog._auto_fill_spellings

        def __init__(self):
            self._fields = {
                "witness_name": DummyVar("Matthew Allan Coger"),
                "reporter_name": DummyVar("Miah Bardot"),
                "county": DummyVar("Bexar"),
            }
            self._spellings_box = DummyBox("")

    messages = []

    def _fake_info(title, message):
        messages.append((title, message))

    monkeypatch.setattr("main.messagebox.showinfo", _fake_info)
    dialog = DummyDialog()
    dialog._auto_fill_spellings()
    text = dialog._spellings_box.value
    assert "Miah Vardell = Miah Bardot" in text
    assert any(title == "Auto-Fill Complete" for title, _ in messages)
