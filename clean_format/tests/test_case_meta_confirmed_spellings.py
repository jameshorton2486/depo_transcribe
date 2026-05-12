"""Phase 2 - verify confirmed_spellings and deepgram_keyterms reach
the cleanup prompt via case_meta.

The audit at docs/audits/CASE_MUTATION_REPORT.md confirmed that 33
hand-curated confirmed_spellings entries were being persisted to
job_config.json and never reaching the cleanup prompt. These tests
pin the wiring fix.
"""

from __future__ import annotations

from clean_format.formatter import (
    _case_meta_for_prompt,
    build_case_meta_from_ufm,
    build_user_message,
)


class TestBuildCaseMetaFromUfm:
    def test_default_confirmed_spellings_is_empty_dict(self):
        case_meta = build_case_meta_from_ufm({"witness_name": "Test"})
        assert "confirmed_spellings" in case_meta
        assert case_meta["confirmed_spellings"] == {}

    def test_default_deepgram_keyterms_is_empty_list(self):
        case_meta = build_case_meta_from_ufm({"witness_name": "Test"})
        assert "deepgram_keyterms" in case_meta
        assert case_meta["deepgram_keyterms"] == []


class TestCaseMetaForPrompt:
    def test_confirmed_spellings_included_when_populated(self):
        case_meta = {
            "witness_name": "Test Witness",
            "confirmed_spellings": {"Pinrue": "Pinn", "Karam": "Karam"},
        }
        result = _case_meta_for_prompt(case_meta)
        assert "confirmed_spellings" in result
        assert result["confirmed_spellings"] == {"Pinrue": "Pinn", "Karam": "Karam"}

    def test_deepgram_keyterms_included_when_populated(self):
        case_meta = {
            "witness_name": "Test",
            "deepgram_keyterms": ["Pinn Road", "Alfred Karam"],
        }
        result = _case_meta_for_prompt(case_meta)
        assert "deepgram_keyterms" in result
        assert result["deepgram_keyterms"] == ["Pinn Road", "Alfred Karam"]

    def test_empty_confirmed_spellings_excluded(self):
        case_meta = {"witness_name": "Test", "confirmed_spellings": {}}
        result = _case_meta_for_prompt(case_meta)
        # Empty dict is filtered out by the existing allowlist logic.
        assert "confirmed_spellings" not in result

    def test_empty_deepgram_keyterms_excluded(self):
        case_meta = {"witness_name": "Test", "deepgram_keyterms": []}
        result = _case_meta_for_prompt(case_meta)
        assert "deepgram_keyterms" not in result

    def test_existing_keys_unchanged(self):
        case_meta = {
            "witness_name": "Test",
            "cause_number": "2025-CI-19595",
            "confirmed_spellings": {"foo": "bar"},
        }
        result = _case_meta_for_prompt(case_meta)
        assert result["witness_name"] == "Test"
        assert result["cause_number"] == "2025-CI-19595"
        assert result["confirmed_spellings"] == {"foo": "bar"}


class TestBuildUserMessageIncludesNewFields:
    def test_user_message_includes_confirmed_spellings_json(self):
        case_meta = {
            "witness_name": "Test",
            "confirmed_spellings": {"Pinrue": "Pinn"},
        }
        msg = build_user_message("chunk", case_meta, 1, 1)
        assert "confirmed_spellings" in msg
        assert "Pinrue" in msg
        assert "Pinn" in msg

    def test_user_message_includes_keyterms(self):
        case_meta = {
            "witness_name": "Test",
            "deepgram_keyterms": ["Pinn Road"],
        }
        msg = build_user_message("chunk", case_meta, 1, 1)
        assert "deepgram_keyterms" in msg
        assert "Pinn Road" in msg
