"""
spec_engine/tests/test_ai_corrector.py

Tests for spec_engine/ai_corrector.py
All offline — no real API calls made.
Run: python -m pytest spec_engine/tests/test_ai_corrector.py -v
"""
import sys
from types import SimpleNamespace

import pytest
from spec_engine.ai_corrector import (
    TRANSCRIPT_CORRECTION_SYSTEM_PROMPT,
    _protect_verbatim,
    _validate_ai_output,
    _preserves_special_verbatim_forms,
    _preserves_structure,
    _restore_verbatim,
    _split_into_chunks,
    _renumber_scopist_flags,
    _build_user_prompt,
    run_ai_correction,
)


class TestSplitIntoChunks:

    def test_short_text_is_single_chunk(self):
        text = "Speaker 1: Short text."
        result = _split_into_chunks(text, max_chars=1000)
        assert len(result) == 1

    def test_short_text_content_unchanged(self):
        text = "Speaker 1: Short text."
        result = _split_into_chunks(text, max_chars=1000)
        assert result[0] == text

    def test_splits_at_paragraph_boundary(self):
        para1 = "A" * 100
        para2 = "B" * 100
        text = para1 + "\n\n" + para2
        result = _split_into_chunks(text, max_chars=150)
        assert len(result) == 2

    def test_first_chunk_contains_first_paragraph(self):
        para1 = "A" * 100
        para2 = "B" * 100
        text = para1 + "\n\n" + para2
        result = _split_into_chunks(text, max_chars=150)
        assert para1 in result[0]

    def test_chunks_reassemble_to_original(self):
        text = "\n\n".join([f"Paragraph {i}: " + "x" * 50 for i in range(10)])
        chunks = _split_into_chunks(text, max_chars=300)
        reassembled = "\n\n".join(chunks)
        assert reassembled == text

    def test_single_oversized_paragraph_stays_whole(self):
        long_para = "word " * 500
        result = _split_into_chunks(long_para, max_chars=100)
        assert len(result) == 1


class TestRenumberScopistFlags:

    def test_renumbers_from_one(self):
        text = "text [SCOPIST: FLAG 5: something] more [SCOPIST: FLAG 12: other]"
        result = _renumber_scopist_flags(text)
        assert "[SCOPIST: FLAG 1:" in result

    def test_second_flag_becomes_two(self):
        text = "text [SCOPIST: FLAG 5: something] more [SCOPIST: FLAG 12: other]"
        result = _renumber_scopist_flags(text)
        assert "[SCOPIST: FLAG 2:" in result

    def test_original_numbers_removed(self):
        text = "text [SCOPIST: FLAG 5: something]"
        result = _renumber_scopist_flags(text)
        assert "[SCOPIST: FLAG 5:" not in result

    def test_no_flags_text_unchanged(self):
        text = "Clean transcript text with no flags."
        assert _renumber_scopist_flags(text) == text

    def test_single_flag_becomes_flag_1(self):
        text = "text [SCOPIST: FLAG 99: verify this]"
        result = _renumber_scopist_flags(text)
        assert "[SCOPIST: FLAG 1:" in result


class TestBuildUserPrompt:

    def test_includes_proper_nouns(self):
        prompt = _build_user_prompt("text", ["Coger", "Murphy Oil"], {}, {})
        assert "Coger" in prompt

    def test_includes_second_proper_noun(self):
        prompt = _build_user_prompt("text", ["Coger", "Murphy Oil"], {}, {})
        assert "Murphy Oil" in prompt

    def test_includes_speaker_map_name(self):
        prompt = _build_user_prompt("text", [], {0: "THE WITNESS"}, {})
        assert "THE WITNESS" in prompt

    def test_includes_transcript_text(self):
        prompt = _build_user_prompt("Did you go there?", [], {}, {})
        assert "Did you go there?" in prompt

    def test_empty_context_still_includes_text(self):
        prompt = _build_user_prompt("Some testimony.", [], {}, {})
        assert "Some testimony." in prompt

    def test_confirmed_spellings_included(self):
        prompt = _build_user_prompt("text", [], {}, {"Cogger": "Coger"})
        assert "Coger" in prompt


class TestPromptSafety:

    def test_prompt_forbids_structure_changes(self):
        assert "Change Q./A. labels" in TRANSCRIPT_CORRECTION_SYSTEM_PROMPT
        assert "Modify transcript structure in any way" in TRANSCRIPT_CORRECTION_SYSTEM_PROMPT

    def test_speaker_label_change_fails_structure_check(self):
        original = "MR. SMITH:  Hello."
        candidate = "THE REPORTER:  Hello."

        assert _preserves_structure(original, candidate) is False


class TestVerbatimProtection:

    def test_protect_restore_verbatim_round_trip(self):
        original = "uh yeah um nope"
        protected_text, protected = _protect_verbatim(original)

        assert "__VERBATIM_0__" in protected_text
        assert _restore_verbatim(protected_text, protected) == original

    def test_stutter_change_fails_special_verbatim_check(self):
        original = "I went to the b-bank."
        candidate = "I went to the bank."

        assert _preserves_special_verbatim_forms(original, candidate) is False

    def test_false_start_change_fails_special_verbatim_check(self):
        original = "I -- I went there."
        candidate = "I went there."

        assert _preserves_special_verbatim_forms(original, candidate) is False


class TestValidationLayer:

    def test_validate_ai_output_rejects_partial_stutter_removal(self):
        original = "Q.\tDid you go there?\nA.\tI went to the b-bank."
        candidate = "Q.\tDid you go there?\nA.\tI went to the bank."

        assert _validate_ai_output(original, candidate) is False

    def test_validate_ai_output_rejects_line_deletion(self):
        original = "Q.\tDid you go there?\nA.\tI did go there."
        candidate = "Q.\tDid you go there?"

        assert _validate_ai_output(original, candidate) is False

    def test_validate_ai_output_rejects_single_line_speaker_change(self):
        original = "MR. SMITH:  Hello.\nA.\tI did go there."
        candidate = "THE REPORTER:  Hello.\nA.\tI did go there."

        assert _validate_ai_output(original, candidate) is False

    def test_validate_ai_output_rejects_large_rewrite(self):
        original = "Q.\tDid you go there?\nA.\tI did go there and then I came back."
        candidate = "Q.\tSummarize this.\nA.\tYes."

        assert _validate_ai_output(original, candidate) is False

    def test_validate_ai_output_rejects_compressed_output(self):
        original = "Q.\tDid you go there?\nA.\tI did go there and then I came back."
        candidate = "Q.\tDid you go there?\nA.\tI went."

        assert _validate_ai_output(original, candidate) is False


class TestRunAICorrection:

    def test_no_api_key_returns_original_text(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        text = "Q.\tDid you go there?\nA.\tuh yeah."

        assert run_ai_correction(text, {}) == text

    def test_destructive_ai_output_reverts_to_original_chunk(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "test-key")

        class _FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key

            class messages:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(content=[SimpleNamespace(text="Short.")])

        monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeClient))

        text = "Q.\tDid you go there?\nA.\tI did go there."

        assert run_ai_correction(text, {}) == text

    def test_structure_changing_ai_output_reverts_to_original_chunk(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "test-key")

        class _FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key

            class messages:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(content=[SimpleNamespace(text="A.\tI did go there.\nQ.\tDid you go there?")])

        monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeClient))

        text = "Q.\tDid you go there?\nA.\tI did go there."

        assert run_ai_correction(text, {}) == text

    def test_missing_protected_verbatim_reverts_to_original_chunk(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "test-key")

        class _FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key

            class messages:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(content=[SimpleNamespace(text="Q.\tDid you go there?\nA.\tI did.")])

        monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeClient))

        text = "Q.\tDid you go there?\nA.\tuh yeah."

        assert run_ai_correction(text, {}) == text

    def test_stutter_changing_ai_output_reverts_to_original_chunk(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "test-key")

        class _FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key

            class messages:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(content=[SimpleNamespace(text="Q.\tDid you go there?\nA.\tI went to the bank.")])

        monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeClient))

        text = "Q.\tDid you go there?\nA.\tb-bank."

        assert run_ai_correction(text, {}) == text

    def test_prompt_pack_temperature_is_passed_to_api(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "test-key")
        captured = {}

        class _FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key

            class messages:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(content=[SimpleNamespace(text="Q.\tDid you go there?\nA.\tI did go there.")])

        monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeClient))

        text = "Q.\tDid you go there?\nA.\tI did go there."

        assert run_ai_correction(text, {}) == text
        assert captured["temperature"] == 0.0
