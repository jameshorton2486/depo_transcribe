from spec_engine.models import Block, BlockType


def test_validate_rule_rejects_overly_broad_regex():
    from spec_engine.user_rule_store import _validate_rule

    valid, reason = _validate_rule({
        "type": "regex_replace",
        "pattern": ".*",
        "replacement": "x",
    })

    assert valid is False
    assert "too broad" in reason


def test_apply_user_rules_uses_safe_apply_when_state_present(monkeypatch):
    from spec_engine.corrections import CorrectionState
    from spec_engine.user_rule_store import apply_user_rules

    state = CorrectionState()
    state.record(
        "protected_rule",
        "subpoena deuces tikum",
        "subpoena duces tecum",
        protected_after="subpoena duces tecum",
    )

    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_active_rules",
        lambda: [
            {
                "id": "usr_999",
                "type": "exact_replace",
                "incorrect": "subpoena duces tecum",
                "correct": "bad replacement",
            }
        ],
    )

    text, records = apply_user_rules("subpoena duces tecum", block_index=0, state=state)

    assert text == "subpoena duces tecum"
    assert records == []


def test_validate_blocks_strict_mode_promotes_question_warning_to_error(monkeypatch):
    import config
    from spec_engine.validator import validate_blocks

    monkeypatch.setattr(config, "STRICT_MODE", True)
    result = validate_blocks([
        Block(speaker_id=2, text="Did you see it", raw_text="", block_type=BlockType.QUESTION)
    ])

    assert result.errors
    assert any("Question" in error for error in result.errors)


def test_validate_blocks_duplicate_warning_requires_close_timing():
    from spec_engine.validator import validate_blocks

    far_apart = validate_blocks([
        Block(speaker_id=1, text="I don't recall.", raw_text="", block_type=BlockType.ANSWER, meta={"start": 1.0}),
        Block(speaker_id=1, text="I don't recall.", raw_text="", block_type=BlockType.ANSWER, meta={"start": 5.0}),
    ])
    close_together = validate_blocks([
        Block(speaker_id=1, text="I don't recall.", raw_text="", block_type=BlockType.ANSWER, meta={"start": 1.0}),
        Block(speaker_id=1, text="I don't recall.", raw_text="", block_type=BlockType.ANSWER, meta={"start": 1.4}),
    ])

    assert not [w for w in far_apart.warnings if "duplicate" in w.lower()]
    assert [w for w in close_together.warnings if "duplicate" in w.lower()]
