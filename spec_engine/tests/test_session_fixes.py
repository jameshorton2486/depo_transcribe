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


def test_safe_apply_logs_skip_reason(caplog):
    """safe_apply emits a WARNING log when it rejects a too-short rewrite.

    Contract change: previously this used print() to stdout, which polluted
    production logs and bypassed handler config. The implementation now
    routes the same skip diagnostic through the spec_engine.corrections
    logger at WARNING level. The test was renamed and switched from capsys
    to caplog to match.
    """
    import logging

    original = "a" * 100
    with caplog.at_level(logging.WARNING, logger="spec_engine.corrections"):
        result = safe_apply(original, "b" * 10, "test_rule", None, [], 0)
    assert result == original
    assert any(
        "SKIPPED" in record.message and "test_rule" in record.message
        for record in caplog.records
    )


def test_transcript_tab_no_longer_auto_runs_ai():
    """Run Corrections must not auto-chain into AI correction.

    AI is a user-initiated action (the ✨ AI Correct button) and must not
    fire automatically from _on_corrections_done. The button label string
    'AI Correcting…' is permitted because it is a button state, not an
    auto-run marker.
    """
    import re
    source = Path("ui/tab_transcript.py").read_text(encoding="utf-8")

    # Old auto-run status string must stay gone
    assert "Running AI review..." not in source

    # _on_corrections_done must not call into the AI pipeline
    match = re.search(
        r"def _on_corrections_done\(.*?\):(.*?)(?=\n    def |\nclass )",
        source,
        re.DOTALL,
    )
    assert match, "_on_corrections_done not found in ui/tab_transcript.py"
    body = match.group(1)
    assert "_start_ai_correction" not in body, (
        "_on_corrections_done must not trigger _start_ai_correction; "
        "AI correction must remain user-initiated."
    )
    assert "_on_ai_correct_clicked" not in body, (
        "_on_corrections_done must not trigger _on_ai_correct_clicked."
    )
