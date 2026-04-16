"""Regression tests for April 2026 correction-path hardening."""

from pathlib import Path

from spec_engine.corrections import clean_block, safe_apply
from spec_engine.models import Block, BlockType, JobConfig
from spec_engine.qa_fixer import _merge_orphaned_continuations


def _cfg() -> JobConfig:
    return JobConfig()


def _block(text: str, block_type: BlockType = BlockType.ANSWER, sid: int = 0) -> Block:
    return Block(
        raw_text=text,
        text=text,
        speaker_id=sid,
        block_type=block_type,
        words=[],
        flags=[],
        meta={},
    )


def test_standalone_answer_correct_not_merged():
    result = _merge_orphaned_continuations([
        _block("Were you driving?", BlockType.QUESTION, sid=1),
        _block("Correct.", BlockType.ANSWER, sid=0),
    ])
    assert len(result) == 2
    assert result[1].text == "Correct."


def test_standalone_answer_yes_not_merged():
    result = _merge_orphaned_continuations([
        _block("Is that right?", BlockType.QUESTION, sid=1),
        _block("Yes.", BlockType.ANSWER, sid=1),
    ])
    assert len(result) == 2
    assert result[1].text == "Yes."


def test_doctor_without_period_normalized():
    result = clean_block("Doctor Williams treated me.", _cfg())[0]
    assert "Dr. Williams" in result


def test_compound_hyphenation_added():
    result = clean_block("This was a pre existing condition.", _cfg())[0]
    assert "pre-existing" in result


def test_medical_term_normalized():
    result = clean_block("The MRI showed a thick hole sack impingement.", _cfg())[0]
    assert "thecal sac" in result


def test_objection_type_normalized():
    result = clean_block("Objection hearsay", _cfg())[0]
    assert result == "Objection.  Hearsay."


def test_caught_number_no_longer_becomes_cause_number():
    result = clean_block("This is caught number 2025CI19595.", _cfg())[0]
    assert "Cause Number" not in result
    assert "caught number" in result.lower()


def test_safe_apply_prints_skip_reason(capsys):
    original = "a" * 100
    result = safe_apply(original, "b" * 10, "test_rule", None, [], 0)
    captured = capsys.readouterr()
    assert result == original
    assert "RULE SKIPPED" in captured.out


def test_transcript_tab_no_longer_auto_runs_ai():
    source = Path("ui/tab_transcript.py").read_text(encoding="utf-8")
    assert "Running AI review..." not in source
    assert "AI Correcting…" not in source
