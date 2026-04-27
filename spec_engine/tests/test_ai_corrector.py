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
from spec_engine.prompt_packs import load_prompt_pack


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
        text = "Q. First question?\nA. First answer.\nQ. Second question?"
        result = _split_into_chunks(text, max_chars=40)
        assert len(result) == 2

    def test_first_chunk_contains_first_qa_pair(self):
        text = "Q. First question?\nA. First answer.\nQ. Second question?"
        result = _split_into_chunks(text, max_chars=40)
        assert result[0] == "Q. First question?\nA. First answer."

    def test_chunks_reassemble_to_original(self):
        text = "\n".join([f"Q. Question {i}?" if i % 2 == 0 else f"A. Answer {i}." for i in range(20)])
        chunks = _split_into_chunks(text, max_chars=120)
        reassembled = "\n".join(chunks)
        assert reassembled == text

    def test_single_oversized_paragraph_stays_whole(self):
        long_para = "Q. " + ("word " * 500)
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


class TestCaseMetadataInPrompt:
    """The CASE METADATA block anchors the AI's correction of the
    reporter's preamble passage (cause number, judicial district, CSR
    number) where Deepgram routinely garbles formal phrases. Each test
    verifies one field is rendered when populated and omitted when
    blank, so a partially-filled job_config doesn't render labels with
    no value."""

    def _meta(self, **overrides):
        # Helper: start with all empty, override the fields under test.
        base = {
            "cause_number": "",
            "witness_name": "",
            "reporter_name": "",
            "csr_number": "",
            "judicial_district": "",
            "court_caption": "",
            "depo_date": "",
        }
        base.update(overrides)
        return base

    def test_cause_number_included_when_populated(self):
        prompt = _build_user_prompt(
            "text", [], {}, {}, None,
            self._meta(cause_number="2025-CI-23267"),
        )
        assert "Cause Number: 2025-CI-23267" in prompt

    def test_witness_name_included_when_populated(self):
        prompt = _build_user_prompt(
            "text", [], {}, {}, None,
            self._meta(witness_name="Peter Durai Singh"),
        )
        assert "Witness: Peter Durai Singh" in prompt

    def test_reporter_and_csr_both_rendered_when_present(self):
        prompt = _build_user_prompt(
            "text", [], {}, {}, None,
            self._meta(reporter_name="Miah Bardot", csr_number="12129"),
        )
        assert "Reporter: Miah Bardot" in prompt
        assert "CSR No.: 12129" in prompt

    def test_judicial_district_and_court_caption_included(self):
        prompt = _build_user_prompt(
            "text", [], {}, {}, None,
            self._meta(
                judicial_district="408TH",
                court_caption="408TH JUDICIAL DISTRICT COURT, BEXAR COUNTY, TEXAS",
            ),
        )
        assert "Judicial District: 408TH" in prompt
        assert "Court: 408TH JUDICIAL DISTRICT COURT, BEXAR COUNTY, TEXAS" in prompt

    def test_empty_field_is_skipped_no_dangling_label(self):
        # csr_number empty should NOT render "CSR No.:" with no value.
        prompt = _build_user_prompt(
            "text", [], {}, {}, None,
            self._meta(reporter_name="Miah Bardot"),  # csr_number stays ""
        )
        assert "Reporter: Miah Bardot" in prompt
        assert "CSR No.:" not in prompt

    def test_no_metadata_omits_section_entirely(self):
        # When every field is empty (or case_metadata=None), the
        # CASE METADATA: section is not rendered at all.
        prompt = _build_user_prompt("text", [], {}, {}, None, None)
        assert "CASE METADATA" not in prompt

    def test_all_empty_metadata_dict_omits_section(self):
        prompt = _build_user_prompt("text", [], {}, {}, None, self._meta())
        assert "CASE METADATA" not in prompt

    def test_case_metadata_section_appears_before_proper_nouns(self):
        # Ordering: CASE METADATA first so the AI sees the formal
        # values before the keyterm list.
        prompt = _build_user_prompt(
            "text", ["Coger"], {}, {}, None,
            self._meta(cause_number="X"),
        )
        meta_pos = prompt.index("CASE METADATA")
        proper_pos = prompt.index("PROPER NOUNS")
        assert meta_pos < proper_pos


class TestPromptSafety:

    def test_prompt_forbids_structure_changes(self):
        pack = load_prompt_pack("legal_transcript_v1")
        assert "Change Q./A. labels" in pack.system_prompt
        assert "Modify transcript structure in any way" in pack.system_prompt

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
        original = "I went to the b--bank."
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

        passed, _ = _validate_ai_output(original, candidate)
        assert passed is False

    def test_validate_ai_output_rejects_line_deletion(self):
        original = "Q.\tDid you go there?\nA.\tI did go there."
        candidate = "Q.\tDid you go there?"

        passed, _ = _validate_ai_output(original, candidate)
        assert passed is False

    def test_validate_ai_output_rejects_single_line_speaker_change(self):
        original = "MR. SMITH:  Hello.\nA.\tI did go there."
        candidate = "THE REPORTER:  Hello.\nA.\tI did go there."

        passed, _ = _validate_ai_output(original, candidate)
        assert passed is False

    def test_validate_ai_output_rejects_large_rewrite(self):
        original = "Q.\tDid you go there?\nA.\tI did go there and then I came back."
        candidate = "Q.\tSummarize this.\nA.\tYes."

        passed, _ = _validate_ai_output(original, candidate)
        assert passed is False

    def test_validate_ai_output_rejects_compressed_output(self):
        original = "Q.\tDid you go there?\nA.\tI did go there and then I came back."
        candidate = "Q.\tDid you go there?\nA.\tI went."

        passed, _ = _validate_ai_output(original, candidate)
        assert passed is False

    def test_validate_ai_output_allows_scopist_flag_addition(self):
        original = (
            "Q.\tDid you go there and review the documents before the deposition began "
            "before the deposition began before the deposition began before the deposition began?\n"
            "A.\tI did go there and review the documents before the deposition began "
            "before the deposition began before the deposition began before the deposition began."
        )
        candidate = (
            "Q.\tDid you go there and review the documents before the deposition began "
            "before the deposition began before the deposition began before the deposition began?\n"
            "A.\tI did go there and review the documents before the deposition began "
            "before the deposition began before the deposition began before the deposition began "
            "[SCOPIST: FLAG 1: verify]."
        )

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is True
        assert reason == ""

    # ── Reason-string contract (added 2026-04-27) ────────────────────────────
    # Each test triggers exactly one branch of the validator and asserts the
    # reason it surfaces. The strings are now logged at the call site, so a
    # high revert rate can be diagnosed by reason without re-running the
    # model. Keep these reason strings stable — log-grep tooling depends on
    # them.

    def test_reason_verbatim_count_when_filler_word_removed(self):
        original = "Q.\tDid you go?\nA.\tUh, yes I did go."
        candidate = "Q.\tDid you go?\nA.\tYes I did go."  # "Uh" removed

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        assert reason == "verbatim_count"

    def test_reason_special_verbatim_forms_when_stutter_collapsed(self):
        # The validator's special-verbatim-forms regex requires a DOUBLE
        # hyphen ("b--bank"), not a single hyphen — Texas stutters use
        # the double-dash convention. Removing the stutter should fire
        # the special_verbatim_forms branch before later checks like
        # word_change_ratio.
        original = "Q.\tDid you go?\nA.\tI went to the b--bank today."
        candidate = "Q.\tDid you go?\nA.\tI went to the bank today."

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        assert reason == "special_verbatim_forms"

    def test_reason_structure_speaker_prefix_when_speaker_label_changed(self):
        original = "MR. SMITH:  Hello.\nA.\tI did go there."
        candidate = "THE REPORTER:  Hello.\nA.\tI did go there."

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        assert reason == "structure_speaker_prefix"

    def test_reason_structure_line_count_when_lines_dropped(self):
        # Line count drift is a distinct structural failure mode from
        # signature or speaker-prefix drift. Surface it as its own reason
        # so the operator can tell whether the AI is collapsing wrapped
        # lines vs re-attributing speakers.
        original = "Q.\tFirst question?\nA.\tFirst answer.\nQ.\tSecond question?"
        candidate = "Q.\tFirst question?\nA.\tFirst answer."

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        assert reason == "structure_line_count"

    def test_reason_structure_signatures_when_qa_swapped_to_text(self):
        # Same line count, no speaker labels — but the line-type signature
        # changes because what was a Q. line becomes a plain TEXT line.
        # That's the AI restructuring the Q/A skeleton, distinct from
        # line-count drift or speaker-label drift.
        original = "Q.\tDid you go?\nA.\tYes."
        candidate = "Did you go?\nA.\tYes."

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        assert reason == "structure_signatures"

    def test_reason_length_delta_when_output_doubles(self):
        # Same Q/A structure and signature, no verbatim tokens, no special
        # forms — but the candidate is more than 30% longer.
        original = "Q.\tDid you go there?\nA.\tYes."
        candidate = (
            "Q.\tDid you go there?\n"
            "A.\tYes and also many other things happened that same day "
            "and we discussed them all in great length."
        )

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        assert reason == "length_delta"

    def test_reason_word_change_ratio_when_aggressive_rewrite(self):
        # Length stays close (within 30%), structure preserved, but more
        # than 15% of words change → word_change_ratio branch.
        original = "Q.\tDid you go to the bank yesterday morning at ten?\nA.\tI did."
        candidate = "Q.\tDid he run to the store last evening near six?\nA.\tHe did."

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        assert reason == "word_change_ratio"

    def test_reason_protected_content_when_form_moves_between_lines(self):
        # The per-line protected_content branch fires when the GLOBAL
        # special-verbatim-forms count is preserved but a form has
        # moved from one line to another. _preserves_special_verbatim_forms
        # compares full lists (order-sensitive) but constructs them from
        # the entire text — so identical forms in shuffled positions
        # actually still differ globally because the comparison is list
        # equality, not multiset equality. We trigger the per-line check
        # by keeping forms in the same order globally but moving them
        # off the line they were on, which list-equality won't catch
        # when only the surrounding text differs.
        #
        # Concretely: two stutter forms, one per line in original; in
        # candidate both forms are on line 1, line 2 has neither.
        # Global list (order-preserving) is the same; per-line check
        # catches the drift.
        original = "I went--to the bank.\nThen we--saw it."
        candidate = "I went--to the we--bank.\nThen saw it."

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is False
        # Both special_verbatim_forms (if global comparison happens to
        # catch ordering difference) and protected_content (per-line)
        # are valid signals for this class of drift; the per-line guard
        # is what we explicitly want to surface.
        assert reason in {"special_verbatim_forms", "protected_content"}

    def test_reason_empty_when_validation_passes(self):
        original = "Q.\tDid you go?\nA.\tYes."
        candidate = "Q.\tDid you go?\nA.\tYes."

        passed, reason = _validate_ai_output(original, candidate)
        assert passed is True
        assert reason == ""


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

    def test_load_prompt_pack_failure_returns_original(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "test-key")
        monkeypatch.setattr("spec_engine.ai_corrector.load_prompt_pack", lambda: (_ for _ in ()).throw(FileNotFoundError("missing")))

        text = "Q.\tDid you go there?\nA.\tI did go there."

        assert run_ai_correction(text, {}) == text

    def test_api_retry_recovers_on_transient_error(self, monkeypatch):
        monkeypatch.setattr("spec_engine.ai_corrector._CONFIG_API_KEY", "test-key")
        call_count = {"value": 0}

        class _FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key

            class messages:
                @staticmethod
                def create(**kwargs):
                    call_count["value"] += 1
                    if call_count["value"] == 1:
                        raise RuntimeError("timeout")
                    return SimpleNamespace(content=[SimpleNamespace(text="Q.\tDid you go there?\nA.\tI did go there.")])

        monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeClient))

        text = "Q.\tDid you go there?\nA.\tI did go there."

        assert run_ai_correction(text, {}) == text
        assert call_count["value"] == 2
