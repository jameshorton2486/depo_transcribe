import sys
from types import SimpleNamespace

from core.config import AI_MODEL


def test_generate_rules_without_api_key_returns_safe_disabled_state(monkeypatch):
    from spec_engine import training_engine

    monkeypatch.setattr(training_engine, "ANTHROPIC_API_KEY", "")

    result = training_engine.generate_rules("wrong", "right")

    assert result["error"] is None
    assert result["rules"] == []
    assert "AI disabled" in result["flags"][0]


def test_validate_rules_rejects_verbatim_objection_and_short_regex():
    from spec_engine.training_engine import _validate_rules

    rules, flags = _validate_rules([
        {"type": "exact_replace", "incorrect": "uh", "correct": "er", "priority": 5},
        {"type": "exact_replace", "incorrect": "Objection form", "correct": "Objection. Form.", "priority": 5},
        {"type": "regex_replace", "pattern": "a", "replacement": "A", "priority": 5},
        {"type": "exact_replace", "incorrect": "subpena", "correct": "subpoena", "priority": 7},
    ])

    assert len(rules) == 1
    assert rules[0]["incorrect"] == "subpena"
    assert rules[0]["priority"] == 10
    assert len(flags) == 3


def test_deduplicate_rules_filters_existing_rule():
    from spec_engine.training_engine import _deduplicate_rules

    existing = [{"type": "exact_replace", "incorrect": "subpena", "correct": "subpoena"}]
    new_rules = [
        {"type": "exact_replace", "incorrect": "subpena", "correct": "subpoena"},
        {"type": "regex_replace", "pattern": r"\bokay\b", "replacement": "Okay"},
    ]

    filtered, flags = _deduplicate_rules(new_rules, existing)

    assert len(filtered) == 1
    assert filtered[0]["type"] == "regex_replace"
    assert flags == ["Skipped duplicate rule 1: already exists"]


def test_generate_rules_normalizes_priorities_and_filters_invalid(monkeypatch):
    from spec_engine import training_engine

    monkeypatch.setattr(training_engine, "ANTHROPIC_API_KEY", "test-key")
    captured = {}

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="""{
  "rules": [
    {"type": "exact_replace", "incorrect": "subpena", "correct": "subpoena", "priority": 7},
    {"type": "exact_replace", "incorrect": "yeah", "correct": "yes", "priority": 7},
    {"type": "regex_replace", "pattern": "\\\\bokay\\\\b", "replacement": "Okay", "priority": 48}
  ],
  "flags": ["AI noted ambiguity"]
}""")])

    class _Client:
        def __init__(self, api_key):
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_Client))
    monkeypatch.setattr("spec_engine.user_rule_store.load_all_rules", lambda: [
        {"type": "regex_replace", "pattern": r"\bokay\b", "replacement": "Okay"}
    ])

    result = training_engine.generate_rules("wrong", "right")

    assert result["error"] is None
    assert len(result["rules"]) == 1
    assert result["rules"][0]["incorrect"] == "subpena"
    assert result["rules"][0]["priority"] == 10
    assert captured["model"] == AI_MODEL
    assert any("verbatim-protected" in flag for flag in result["flags"])
    assert any("Skipped duplicate rule" in flag for flag in result["flags"])
    assert any("AI noted ambiguity" in flag for flag in result["flags"])
