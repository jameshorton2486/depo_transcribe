"""
Unit tests for delete_rule and set_rule_enabled in user_rule_store.

Each test redirects RULES_PATH to a per-test tmp file so the real
spec_engine/user_rules.json is never touched.
"""

import json

import pytest

from spec_engine import user_rule_store


@pytest.fixture
def isolated_rules_path(monkeypatch, tmp_path):
    rules_path = tmp_path / "test_rules.json"
    monkeypatch.setattr(user_rule_store, "RULES_PATH", rules_path)
    return rules_path


def _seed(rules_path, rules):
    payload = {"version": user_rule_store.RULES_VERSION, "rules": rules}
    rules_path.write_text(json.dumps(payload), encoding="utf-8")


def _load(rules_path):
    return json.loads(rules_path.read_text(encoding="utf-8"))["rules"]


def _exact(id_, incorrect, correct, **extras):
    rule = {"id": id_, "type": "exact_replace", "incorrect": incorrect, "correct": correct}
    rule.update(extras)
    return rule


# ── delete_rule ──────────────────────────────────────────────────────────────

def test_delete_rule_removes_existing_returns_true(isolated_rules_path):
    _seed(isolated_rules_path, [
        _exact("usr_001", "Coger", "Koger"),
        _exact("usr_002", "depo", "deposition"),
    ])
    assert user_rule_store.delete_rule("usr_001") is True


def test_delete_rule_removes_existing_persists_to_disk(isolated_rules_path):
    _seed(isolated_rules_path, [
        _exact("usr_001", "Coger", "Koger"),
        _exact("usr_002", "depo", "deposition"),
    ])
    user_rule_store.delete_rule("usr_001")
    assert [r["id"] for r in _load(isolated_rules_path)] == ["usr_002"]


def test_delete_rule_not_found_returns_false(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger")])
    assert user_rule_store.delete_rule("usr_999") is False


def test_delete_rule_not_found_does_not_modify_file(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger")])
    user_rule_store.delete_rule("usr_999")
    assert len(_load(isolated_rules_path)) == 1


def test_delete_rule_missing_file_returns_false(isolated_rules_path):
    # No file written — delete on an empty store is a clean no-op.
    assert user_rule_store.delete_rule("usr_001") is False


def test_delete_rule_is_idempotent_on_repeat(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger")])
    user_rule_store.delete_rule("usr_001")
    assert user_rule_store.delete_rule("usr_001") is False


def test_delete_rule_preserves_other_rules(isolated_rules_path):
    _seed(isolated_rules_path, [
        _exact("usr_001", "Coger", "Koger"),
        _exact("usr_002", "depo", "deposition"),
        _exact("usr_003", "wittness", "witness"),
    ])
    user_rule_store.delete_rule("usr_002")
    assert [r["id"] for r in _load(isolated_rules_path)] == ["usr_001", "usr_003"]


def test_delete_rule_leaves_no_tmp_file_after_save(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger")])
    user_rule_store.delete_rule("usr_001")
    tmp_file = isolated_rules_path.with_suffix(".tmp")
    assert not tmp_file.exists()


# ── set_rule_enabled ─────────────────────────────────────────────────────────

def test_set_rule_enabled_disables_active_rule_returns_true(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    assert user_rule_store.set_rule_enabled("usr_001", False) is True


def test_set_rule_enabled_disables_active_rule_persists(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    user_rule_store.set_rule_enabled("usr_001", False)
    assert _load(isolated_rules_path)[0]["enabled"] is False


def test_set_rule_enabled_enables_disabled_rule(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=False)])
    user_rule_store.set_rule_enabled("usr_001", True)
    assert _load(isolated_rules_path)[0]["enabled"] is True


def test_set_rule_enabled_not_found_returns_false(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    assert user_rule_store.set_rule_enabled("usr_999", False) is False


def test_set_rule_enabled_not_found_does_not_modify_file(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    user_rule_store.set_rule_enabled("usr_999", False)
    assert _load(isolated_rules_path)[0]["enabled"] is True


def test_set_rule_enabled_no_op_returns_true(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    assert user_rule_store.set_rule_enabled("usr_001", True) is True


def test_set_rule_enabled_no_op_skips_disk_write(isolated_rules_path, monkeypatch):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    save_calls = []
    real_save = user_rule_store.save_rules
    monkeypatch.setattr(
        user_rule_store,
        "save_rules",
        lambda rules: (save_calls.append(rules) or real_save(rules)),
    )
    user_rule_store.set_rule_enabled("usr_001", True)
    assert save_calls == []


def test_set_rule_enabled_preserves_other_rules(isolated_rules_path):
    _seed(isolated_rules_path, [
        _exact("usr_001", "Coger", "Koger", enabled=True),
        _exact("usr_002", "depo", "deposition", enabled=True),
    ])
    user_rule_store.set_rule_enabled("usr_001", False)
    by_id = {r["id"]: r for r in _load(isolated_rules_path)}
    assert by_id["usr_001"]["enabled"] is False
    assert by_id["usr_002"]["enabled"] is True


def test_set_rule_enabled_idempotent_when_repeated(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    user_rule_store.set_rule_enabled("usr_001", False)
    user_rule_store.set_rule_enabled("usr_001", False)
    assert _load(isolated_rules_path)[0]["enabled"] is False


def test_set_rule_enabled_treats_missing_enabled_as_true(isolated_rules_path, monkeypatch):
    # load_active_rules reads `rule.get("enabled", True)`. set_rule_enabled
    # mirrors that default — so calling set_rule_enabled(id, True) on a
    # rule with no explicit "enabled" key is a no-op (no rewrite).
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger")])
    save_calls = []
    real_save = user_rule_store.save_rules
    monkeypatch.setattr(
        user_rule_store,
        "save_rules",
        lambda rules: (save_calls.append(rules) or real_save(rules)),
    )
    assert user_rule_store.set_rule_enabled("usr_001", True) is True
    assert save_calls == []


def test_set_rule_enabled_leaves_no_tmp_file_after_save(isolated_rules_path):
    _seed(isolated_rules_path, [_exact("usr_001", "Coger", "Koger", enabled=True)])
    user_rule_store.set_rule_enabled("usr_001", False)
    tmp_file = isolated_rules_path.with_suffix(".tmp")
    assert not tmp_file.exists()
