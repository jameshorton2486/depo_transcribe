from __future__ import annotations

import pytest

from pipeline.assembler import ROLE_SEQUENCE
from spec_engine.classifier import ClassifierState, classify_block, classify_blocks
from spec_engine.models import Block, BlockType, JobConfig, LineType
from spec_engine.qa_fixer import (
    _merge_orphaned_continuations,
    _remove_near_duplicate_blocks,
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
    )
    d2 = Block(
        speaker_id=1,
        text="I did not see any spill at that time really.",
        raw_text="",
        block_type=BlockType.ANSWER,
    )
    deduped = _remove_near_duplicate_blocks([d1, d2])
    assert len(deduped) == 1
    assert deduped[0].text == d2.text


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
