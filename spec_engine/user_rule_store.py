"""
spec_engine/user_rule_store.py

Persistent storage and application of user-trained correction rules.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).parent / "user_rules.json"
RULES_VERSION = 1
VERBATIM_PROTECTED = frozenset([
    "uh", "um", "ah", "uh-huh", "uh-uh",
    "yeah", "yep", "yup", "nope", "nah",
    "mm-hmm", "mhmm", "gonna", "wanna", "gotta",
])


def _load_rules_payload() -> list[dict]:
    if not RULES_PATH.exists():
        return []

    try:
        payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("user_rule_store: failed to read %s: %s", RULES_PATH, exc)
        return []

    rules = payload.get("rules", []) if isinstance(payload, dict) else []
    if not isinstance(rules, list):
        logger.warning("user_rule_store: malformed rules payload in %s", RULES_PATH)
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def _rule_sort_key(rule: dict) -> tuple[int, str]:
    priority = rule.get("priority", 50)
    if not isinstance(priority, int):
        priority = 50
    return priority, str(rule.get("id", ""))


def load_active_rules() -> list[dict]:
    rules = [rule for rule in _load_rules_payload() if rule.get("enabled", True)]
    return sorted(rules, key=_rule_sort_key)


def load_all_rules() -> list[dict]:
    return sorted(_load_rules_payload(), key=_rule_sort_key)


def save_rules(rules: list[dict]) -> None:
    failures: list[str] = []
    for rule in rules:
        valid, reason = _validate_rule(rule)
        if not valid:
            failures.append(f"{rule.get('id', '<new>')}: {reason}")

    if failures:
        raise ValueError("; ".join(failures))

    payload = {"version": RULES_VERSION, "rules": rules}
    tmp_path = RULES_PATH.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(RULES_PATH)


def add_rules(new_rules: list[dict]) -> int:
    existing_rules = load_all_rules()
    next_id = _next_rule_number(existing_rules)
    added = 0

    for incoming in new_rules:
        if not isinstance(incoming, dict):
            raise ValueError("new rule is not a dict")

        rule = dict(incoming)
        rule.setdefault("enabled", True)
        rule.setdefault("priority", 50)
        rule.setdefault("created_at", datetime.now().isoformat())
        rule["id"] = f"usr_{next_id:03d}"

        valid, reason = _validate_rule(rule)
        if not valid:
            raise ValueError(reason)

        if _is_duplicate(rule, existing_rules):
            continue

        existing_rules.append(rule)
        next_id += 1
        added += 1

    save_rules(existing_rules)
    return added


def _next_rule_number(rules: list[dict]) -> int:
    next_id = 1
    for rule in rules:
        match = re.fullmatch(r"usr_(\d{3,})", str(rule.get("id", "")))
        if match:
            next_id = max(next_id, int(match.group(1)) + 1)
    return next_id


def _is_duplicate(rule: dict, existing_rules: list[dict]) -> bool:
    if rule.get("type") == "exact_replace":
        candidate = (rule.get("incorrect"), rule.get("correct"))
        return any(
            existing.get("type") == "exact_replace"
            and (existing.get("incorrect"), existing.get("correct")) == candidate
            for existing in existing_rules
        )

    candidate = (rule.get("pattern"), rule.get("replacement"))
    return any(
        existing.get("type") == "regex_replace"
        and (existing.get("pattern"), existing.get("replacement")) == candidate
        for existing in existing_rules
    )


def _validate_rule(rule: dict) -> tuple[bool, str]:
    rule_type = rule.get("type")
    if rule_type == "exact_replace":
        incorrect = rule.get("incorrect")
        correct = rule.get("correct")
        if not isinstance(incorrect, str) or not incorrect.strip():
            return False, "exact_replace.incorrect must be a non-empty string"
        if not isinstance(correct, str):
            return False, "exact_replace.correct must be a string"
        if incorrect == correct:
            return False, "exact_replace is a no-op"
        if incorrect.strip().lower() in VERBATIM_PROTECTED:
            return False, "exact_replace touches a verbatim-protected word"
        if incorrect.strip().lower().startswith("objection"):
            return False, "exact_replace may not target objection text"
        if correct == "" and any(char.isalnum() for char in incorrect):
            return False, "exact_replace may not delete bare words"
        return True, ""

    if rule_type == "regex_replace":
        pattern = rule.get("pattern")
        replacement = rule.get("replacement")
        if not isinstance(pattern, str) or not pattern.strip():
            return False, "regex_replace.pattern must be a non-empty string"
        if not isinstance(replacement, str):
            return False, "regex_replace.replacement must be a string"
        if pattern.strip() in {".*", ".+", r"\w+"}:
            return False, "regex_replace.pattern is too broad"
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            return False, f"regex_replace.pattern failed to compile: {exc}"
        for word in VERBATIM_PROTECTED:
            try:
                if compiled.fullmatch(word):
                    return False, "regex_replace matches a verbatim-protected word"
            except re.error as exc:
                return False, f"regex_replace.pattern failed during validation: {exc}"
        return True, ""

    return False, "unknown rule type"


def apply_user_rules(
    text: str,
    block_index: int = 0,
    state=None,
    active_rules: list[dict] | None = None,
) -> tuple[str, list]:
    from .models import CorrectionRecord

    records: list[CorrectionRecord] = []
    current_text = text
    rules = active_rules if active_rules is not None else load_active_rules()

    for rule in rules:
        before = current_text
        try:
            if rule.get("type") == "exact_replace":
                new_text = current_text.replace(
                    str(rule["incorrect"]),
                    str(rule["correct"]),
                )
            elif rule.get("type") == "regex_replace":
                new_text = re.sub(
                    str(rule["pattern"]),
                    str(rule["replacement"]),
                    current_text,
                )
            else:
                continue
        except Exception as exc:
            logger.warning("user_rule_store: failed rule %s: %s", rule.get("id", "?"), exc)
            continue

        if state is not None:
            from .corrections import safe_apply

            current_text = safe_apply(
                current_text,
                new_text,
                f"user_rule:{rule.get('id', '?')}",
                state,
                records,
                block_index,
                protected_after=str(rule.get("correct") or rule.get("replacement") or "").strip() or None,
            )
        elif new_text != before:
            logger.debug("user_rule_store: applied %s to block %d", rule.get("id", "?"), block_index)
            records.append(CorrectionRecord(
                original=before,
                corrected=new_text,
                pattern=f"user_rule:{rule.get('id', '?')}",
                block_index=block_index,
            ))
            current_text = new_text

    return current_text, records


def delete_rule(rule_id: str) -> bool:
    """
    Remove a rule by id. Returns True if a rule was removed, False if
    the id was not found. The write goes through save_rules so the
    operation is atomic and inherits its validation pass — a corrupt
    rule already in the store will fail the save, same as add_rules.
    """
    rules = load_all_rules()
    remaining = [rule for rule in rules if rule.get("id") != rule_id]
    if len(remaining) == len(rules):
        return False
    save_rules(remaining)
    return True


def set_rule_enabled(rule_id: str, enabled: bool) -> bool:
    """
    Toggle a rule's `enabled` state. Returns True if the rule was found
    (regardless of whether the file was rewritten), False if the id was
    not found. A call that would not change state is treated as a no-op
    and skips the disk write — protects against rapid-clicking the
    library's enable dot from spamming .tmp rewrites.

    Missing `enabled` key is treated as True, mirroring load_active_rules.
    """
    rules = load_all_rules()
    target = next((rule for rule in rules if rule.get("id") == rule_id), None)
    if target is None:
        return False
    if bool(target.get("enabled", True)) == bool(enabled):
        logger.debug("set_rule_enabled: %s already %s, no-op", rule_id, enabled)
        return True
    target["enabled"] = bool(enabled)
    save_rules(rules)
    return True


def get_rules_summary() -> str:
    if not RULES_PATH.exists():
        return "No rules file — generate rules in the Training tab."

    rules = load_all_rules()
    active_count = sum(1 for rule in rules if rule.get("enabled", True))
    disabled_count = len(rules) - active_count
    return f"{len(rules)} rules ({active_count} active, {disabled_count} disabled)"
