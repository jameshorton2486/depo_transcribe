"""
End-to-end state machine test for the Training tab.

Walks the full user journey across panels — empty library, propose
rules from Step 02, approve into the library, toggle a rule off,
delete a rule — with every external dependency mocked:

  - spec_engine.user_rule_store.load_all_rules    → reads `fake_store`
  - spec_engine.user_rule_store.add_rules         → appends to fake_store
  - spec_engine.user_rule_store.set_rule_enabled  → mutates fake_store
  - spec_engine.user_rule_store.delete_rule       → mutates fake_store
  - tkinter.messagebox.askyesno                   → always True

The Anthropic API call is bypassed by invoking _on_generate_done
directly with canned proposed rules — the threading layer in
_on_generate is fire-and-forget and out of scope here.

Per-commit tests cover each panel in isolation; this test is the
safety net for the orchestration between them.
"""

import customtkinter as ctk
import pytest

from ui._components import DOT_DISABLED, DOT_ENABLED
from ui.tab_training import TrainingTab


@pytest.fixture
def tab(root):
    t = TrainingTab(root)
    yield t
    t.destroy()


@pytest.fixture
def fake_store():
    """Mutable list that mocks intercept and mutate. Empty per test."""
    return []


@pytest.fixture
def patched_store(monkeypatch, fake_store):
    """Wire the user_rule_store API onto fake_store. Returns the
    list of recorded calls for assertions that need to verify call
    sequencing."""
    record: dict[str, list] = {"add": [], "delete": [], "toggle": []}

    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: list(fake_store),
    )

    def add(new_rules):
        record["add"].append(list(new_rules))
        fake_store.extend(new_rules)
        return len(new_rules)

    monkeypatch.setattr("spec_engine.user_rule_store.add_rules", add)

    def set_enabled(rid, enabled):
        record["toggle"].append((rid, enabled))
        for rule in fake_store:
            if rule.get("id") == rid:
                rule["enabled"] = bool(enabled)
                return True
        return False

    monkeypatch.setattr(
        "spec_engine.user_rule_store.set_rule_enabled", set_enabled
    )

    def delete(rid):
        record["delete"].append(rid)
        for i, rule in enumerate(fake_store):
            if rule.get("id") == rid:
                del fake_store[i]
                return True
        return False

    monkeypatch.setattr("spec_engine.user_rule_store.delete_rule", delete)
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *_a, **_k: True
    )
    return record


def _exact(rule_id, before, after, *, enabled=True):
    return {
        "id": rule_id,
        "type": "exact_replace",
        "incorrect": before,
        "correct": after,
        "enabled": enabled,
    }


def _find_card(container, rule_id):
    for card in container.winfo_children():
        if hasattr(card, "id_label") and card.id_label.cget("text") == rule_id:
            return card
    return None


def test_full_flow_empty_propose_approve_toggle_delete(tab, fake_store, patched_store):
    # ── Phase 1: empty library ──────────────────────────────────────────
    tab._refresh_active_rules()
    assert tab._library_count_pill.text_label.cget("text") == "0 rules"
    assert tab._step_03.winfo_manager() == ""  # Step 03 hidden at startup

    # ── Phase 2: simulate Anthropic returning proposed rules ────────────
    proposed = [
        _exact("usr_001", "Coger", "Koger"),
        _exact("usr_002", "depo", "deposition"),
    ]
    tab._on_generate_done({"error": None, "rules": proposed, "flags": []})

    # Step 03 visible with two proposed cards. Approve unlocked.
    assert tab._step_03.winfo_manager() == "pack"
    assert len(tab._proposed_rules_container.winfo_children()) == 2
    assert tab._approve_btn.cget("state") == "normal"

    # Library still empty — proposed rules don't land in it until approve.
    assert tab._library_count_pill.text_label.cget("text") == "0 rules"
    assert fake_store == []

    # ── Phase 3: approve & save ─────────────────────────────────────────
    tab._on_approve()

    assert patched_store["add"] == [proposed]  # add_rules called with the batch
    assert tab._step_03.winfo_manager() == ""  # Step 03 collapsed
    assert tab._approve_btn.cget("state") == "disabled"
    assert tab._library_count_pill.text_label.cget("text") == "2 rules"
    assert len(tab._active_rules_container.winfo_children()) == 2
    assert len(fake_store) == 2

    # ── Phase 4: toggle usr_001 off ─────────────────────────────────────
    tab._on_toggle_rule("usr_001", False)

    assert ("usr_001", False) in patched_store["toggle"]
    target = next(r for r in fake_store if r["id"] == "usr_001")
    assert target["enabled"] is False

    # Library still shows 2 cards — toggle is not delete.
    assert tab._library_count_pill.text_label.cget("text") == "2 rules"
    assert len(tab._active_rules_container.winfo_children()) == 2

    # The disabled card's dot repainted to slate; the other stayed emerald.
    usr_001_card = _find_card(tab._active_rules_container, "usr_001")
    usr_002_card = _find_card(tab._active_rules_container, "usr_002")
    assert usr_001_card.dot.cget("fg_color") == DOT_DISABLED
    assert usr_002_card.dot.cget("fg_color") == DOT_ENABLED

    # ── Phase 5: delete usr_002 ─────────────────────────────────────────
    tab._on_delete_rule("usr_002")

    assert "usr_002" in patched_store["delete"]
    assert len(fake_store) == 1
    assert fake_store[0]["id"] == "usr_001"

    # Library now shows one card.
    assert tab._library_count_pill.text_label.cget("text") == "1 rule"
    assert len(tab._active_rules_container.winfo_children()) == 1
    assert _find_card(tab._active_rules_container, "usr_002") is None
    assert _find_card(tab._active_rules_container, "usr_001") is not None


def test_full_flow_approve_handles_validation_failure(tab, monkeypatch):
    # add_rules raises ValueError when a rule fails validation. The UI
    # must surface it via the status row without crashing or clearing
    # the proposed-rules buffer.
    proposed = [_exact("usr_001", "uh", "uhm")]  # touches verbatim word
    tab._on_generate_done({"error": None, "rules": proposed, "flags": []})

    def add(_rules):
        raise ValueError("exact_replace touches a verbatim-protected word")

    monkeypatch.setattr("spec_engine.user_rule_store.add_rules", add)
    tab._on_approve()

    # Status reflects the error.
    assert "Save failed" in tab._status_label.cget("text")
    # Step 03 stays visible — the user should be able to edit the
    # textbox or just clear, rather than losing their batch silently.
    assert tab._step_03.winfo_manager() == "pack"


def test_full_flow_delete_cancel_keeps_rule(tab, fake_store, monkeypatch):
    # User clicks delete, then cancels the confirmation. Store
    # untouched, library unchanged.
    fake_store.extend([_exact("usr_001", "Coger", "Koger")])
    monkeypatch.setattr(
        "spec_engine.user_rule_store.load_all_rules",
        lambda: list(fake_store),
    )
    delete_calls = []
    monkeypatch.setattr(
        "spec_engine.user_rule_store.delete_rule",
        lambda rid: delete_calls.append(rid) or True,
    )
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *_a, **_k: False
    )

    tab._refresh_active_rules()
    tab._on_delete_rule("usr_001")

    assert delete_calls == []
    assert len(fake_store) == 1
    assert len(tab._active_rules_container.winfo_children()) == 1


def test_full_flow_clear_after_propose_resets_step_03_only(tab, fake_store, patched_store):
    # Pre-populate the library, then propose, then clear. Library must
    # stay populated; only the proposed batch and Step 03 should reset.
    fake_store.append(_exact("usr_existing", "depo", "deposition"))
    tab._refresh_active_rules()
    assert len(tab._active_rules_container.winfo_children()) == 1

    proposed = [_exact("usr_new", "Coger", "Koger")]
    tab._on_generate_done({"error": None, "rules": proposed, "flags": []})
    assert tab._step_03.winfo_manager() == "pack"

    tab._on_clear()

    assert tab._step_03.winfo_manager() == ""
    assert tab._proposed_rules == []
    # Library untouched.
    assert len(tab._active_rules_container.winfo_children()) == 1
    assert fake_store[0]["id"] == "usr_existing"
