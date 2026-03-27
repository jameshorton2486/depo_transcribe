"""
test_phase5_verification.py

Phase 5 Verification Test Suite — Formatter, Emitter, and Validation
Run with: python -m pytest spec_engine/tests/test_phase5_verification.py -v
"""

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from spec_engine.models import Block, BlockType
from spec_engine.validator import _normalize_for_compare, validate_blocks


class TestFix5A_EllipsisProtection:
    def test_ellipsis_not_double_spaced_before_capital(self):
        from formatter import normalize_sentence_spacing
        text = "Answer: . . . I do not recall."
        result = normalize_sentence_spacing(text)
        assert ". . ." in result
        assert ". . .  " not in result

    def test_ellipsis_count_unchanged(self):
        from formatter import normalize_sentence_spacing
        cases = [
            "He said . . . and paused.",
            "The answer was . . . unclear. Continuing.",
            "First . . . then . . . finally.",
        ]
        for text in cases:
            assert normalize_sentence_spacing(text).count(". . .") == text.count(". . .")

    def test_ellipsis_before_uppercase_preserved(self):
        from formatter import normalize_sentence_spacing
        text = "He said . . . Correct. And moved on."
        result = normalize_sentence_spacing(text)
        assert ". . ." in result
        assert ". . .  Correct" not in result

    def test_normal_sentence_spacing_still_works(self):
        from formatter import normalize_sentence_spacing
        text = "He answered. The question was clear."
        result = normalize_sentence_spacing(text)
        assert "answered.  The" in result

    def test_question_mark_spacing_still_works(self):
        from formatter import normalize_sentence_spacing
        text = "Did you see it? Yes, I did."
        result = normalize_sentence_spacing(text)
        assert "it?  Yes" in result


class TestFix5B_SkipCorrectionsParameter:
    def test_parameter_exists_in_signature(self):
        from formatter import format_transcript
        sig = inspect.signature(format_transcript)
        assert "skip_corrections_already_applied" in sig.parameters

    def test_parameter_defaults_false(self):
        from formatter import format_transcript
        sig = inspect.signature(format_transcript)
        assert sig.parameters["skip_corrections_already_applied"].default is False

    def test_existing_callers_unaffected(self):
        from formatter import format_transcript
        result = format_transcript("Q. Did you witness the incident?", use_qa_format=True)
        assert isinstance(result, str)

    def test_skip_flag_callable_without_error(self):
        from formatter import format_transcript
        result = format_transcript(
            "A. I was on I-10 near downtown.",
            skip_corrections_already_applied=True,
        )
        assert isinstance(result, str)

    def test_skip_flag_does_not_apply_highway_normalization(self):
        from formatter import format_transcript
        text = "A. I was on I 35 near downtown."
        result_normal = format_transcript(text, use_qa_format=False)
        result_skip = format_transcript(
            text, use_qa_format=False, skip_corrections_already_applied=True
        )
        assert "I-35" not in result_skip
        assert "I-35" in result_normal

    def test_non_skip_operations_still_run_with_flag(self):
        from formatter import format_transcript
        text = "Q. Did you witness this. A. yes."
        result = format_transcript(
            text, use_qa_format=False, skip_corrections_already_applied=True
        )
        assert isinstance(result, str) and len(result) > 0


class TestFix5C_EmitSpLineSingleSpace:
    def test_two_space_colon_bold_label(self):
        from spec_engine.emitter import create_document, emit_sp_line
        doc = create_document()
        emit_sp_line(doc, "MR. BOYCE:  Objection. Form.")
        bold_runs = [r.text for r in doc.paragraphs[0].runs if r.bold]
        assert bold_runs
        assert any("BOYCE" in r for r in bold_runs)

    def test_single_space_colon_bold_label(self):
        from spec_engine.emitter import create_document, emit_sp_line
        doc = create_document()
        emit_sp_line(doc, "MR. BOYCE: Objection. Form.")
        bold_runs = [r.text for r in doc.paragraphs[0].runs if r.bold]
        assert bold_runs
        assert any("BOYCE" in r for r in bold_runs)

    def test_single_space_text_uses_two_spaces_after_colon_in_output(self):
        from spec_engine.emitter import create_document, emit_sp_line
        doc = create_document()
        emit_sp_line(doc, "MR. BOYCE: Objection. Form.")
        plain_runs = [r.text for r in doc.paragraphs[0].runs if not r.bold]
        text_runs = [r for r in plain_runs if "Objection" in r]
        assert text_runs
        assert text_runs[0].startswith("  ")

    def test_no_colon_emits_without_error(self):
        from spec_engine.emitter import create_document, emit_sp_line
        doc = create_document()
        emit_sp_line(doc, "THE REPORTER continued speaking.")
        assert len(doc.paragraphs) == 1

    def test_reporter_label_bold(self):
        from spec_engine.emitter import create_document, emit_sp_line
        for sep in [":  ", ": "]:
            doc = create_document()
            emit_sp_line(doc, f"THE REPORTER{sep}You are under oath.")
            bold_runs = [r.text for r in doc.paragraphs[0].runs if r.bold]
            assert bold_runs


class TestFix5D_SharedTabStopHelper:
    def test_standard_tabs_constant_exists(self):
        from spec_engine.emitter import _STANDARD_TABS
        assert _STANDARD_TABS is not None

    def test_standard_tabs_contains_correct_values(self):
        from spec_engine.emitter import TAB_360, TAB_900, TAB_1440, TAB_2160, _STANDARD_TABS
        assert _STANDARD_TABS == [TAB_360, TAB_900, TAB_1440, TAB_2160]

    def test_apply_standard_tabs_helper_exists(self):
        from spec_engine.emitter import _apply_standard_tabs
        assert callable(_apply_standard_tabs)

    def test_emit_line_numbered_uses_shared_helper(self):
        from spec_engine.emitter import emit_line_numbered
        src = inspect.getsource(emit_line_numbered)
        assert "_apply_standard_tabs(" in src
        assert "for stop_twips in [TAB_360" not in src

    def test_numbered_emitter_still_produces_correct_output(self):
        from spec_engine.emitter import (
            LineNumberTracker,
            QAPairTracker,
            create_document,
            emit_line_numbered,
        )
        from spec_engine.models import LineType

        doc = create_document()
        tracker = LineNumberTracker()
        qa = QAPairTracker()
        emit_line_numbered(doc, LineType.Q, "Did you witness this?", tracker, qa)
        emit_line_numbered(doc, LineType.A, "Yes, I did.", tracker, qa)
        assert len(doc.paragraphs) == 2
        q_text = "".join(r.text for r in doc.paragraphs[0].runs)
        a_text = "".join(r.text for r in doc.paragraphs[1].runs)
        assert "Q." in q_text
        assert "A." in a_text


class TestFix5E_LinesPerPageDocumentation:
    def test_lines_per_page_value_unchanged(self):
        from spec_engine.emitter import LineNumberTracker
        assert LineNumberTracker.LINES_PER_PAGE == 25

    def test_lines_per_page_has_derivation_comment(self):
        from spec_engine.emitter import LineNumberTracker
        src = inspect.getsource(LineNumberTracker)
        has_derivation = any(
            keyword in src
            for keyword in ["margin", "Usable", "derivation", "11 inch", "11.0", "9.0"]
        )
        assert has_derivation

    def test_line_number_tracker_still_functions(self):
        from spec_engine.emitter import LineNumberTracker
        tracker = LineNumberTracker(start_page=3)
        for expected_line in range(1, 26):
            page, line = tracker.next()
            assert page == 3
            assert line == expected_line
        page, line = tracker.next()
        assert page == 4
        assert line == 1


class TestFix5F_NormalizeForCompare:
    def test_period_vs_question_mark_differ(self):
        assert _normalize_for_compare("Yes.") != _normalize_for_compare("Yes?")

    def test_identical_text_still_matches(self):
        assert _normalize_for_compare("Yes.") == _normalize_for_compare("Yes.")
        assert _normalize_for_compare("I do not recall.") == _normalize_for_compare(
            "I do not recall."
        )

    def test_period_preserved_in_normalized(self):
        assert _normalize_for_compare("I don't know.").endswith(".")

    def test_question_mark_preserved_in_normalized(self):
        assert _normalize_for_compare("Did you see it?").endswith("?")

    def test_other_punctuation_still_stripped(self):
        result = _normalize_for_compare("I don't, recall—it.")
        assert "'" not in result
        assert "," not in result
        assert "—" not in result
        assert "." in result

    def test_near_duplicate_detection_distinguishes_punctuation(self):
        b1 = Block(speaker_id=1, text="Yes.", raw_text="", block_type=BlockType.ANSWER)
        b2 = Block(speaker_id=1, text="Yes?", raw_text="", block_type=BlockType.ANSWER)
        result = validate_blocks([b1, b2])
        dup_warnings = [w for w in result.warnings if "duplicate" in w.lower()]
        assert not dup_warnings


class TestFix5G_ColloquySpeakerRoleValidation:
    def test_colloquy_with_witness_role_warns(self):
        b = Block(
            speaker_id=1,
            text="I do not recall seeing that.",
            raw_text="",
            block_type=BlockType.COLLOQUY,
            speaker_role="WITNESS",
        )
        result = validate_blocks([b])
        assert [w for w in result.warnings if "COLLOQUY" in w]

    def test_speaker_with_witness_role_warns(self):
        b = Block(
            speaker_id=1,
            text="THE WITNESS:  Something was said.",
            raw_text="",
            block_type=BlockType.SPEAKER,
            speaker_role="WITNESS",
        )
        result = validate_blocks([b])
        assert [w for w in result.warnings if "SPEAKER" in w]

    def test_colloquy_with_attorney_role_no_warning(self):
        b = Block(
            speaker_id=2,
            text="Let me rephrase that.",
            raw_text="",
            block_type=BlockType.COLLOQUY,
            speaker_role="EXAMINING_ATTORNEY",
        )
        result = validate_blocks([b])
        assert not [w for w in result.warnings if "COLLOQUY" in w]

    def test_answer_with_witness_role_no_warning(self):
        b = Block(
            speaker_id=1,
            text="Yes, I did.",
            raw_text="",
            block_type=BlockType.ANSWER,
            speaker_role="WITNESS",
        )
        result = validate_blocks([b])
        role_warns = [
            w
            for w in result.warnings
            if "WITNESS" in w and "COLLOQUY" not in w and "SPEAKER" not in w
        ]
        assert not role_warns

    def test_colloquy_with_empty_role_no_warning(self):
        b = Block(
            speaker_id=0,
            text="Let me clarify.",
            raw_text="",
            block_type=BlockType.COLLOQUY,
            speaker_role="",
        )
        result = validate_blocks([b])
        assert not [w for w in result.warnings if "COLLOQUY" in w]


class TestFix5H_TerminalPunctuationValidation:
    def test_question_without_mark_warns(self):
        b = Block(speaker_id=2, text="Did you see the spill", raw_text="", block_type=BlockType.QUESTION)
        result = validate_blocks([b])
        q_warns = [w for w in result.warnings if "Question" in w]
        assert q_warns
        assert "?" in q_warns[0]

    def test_question_with_mark_no_warning(self):
        b = Block(speaker_id=2, text="Did you see the spill?", raw_text="", block_type=BlockType.QUESTION)
        result = validate_blocks([b])
        q_warns = [w for w in result.warnings if "Question" in w and "?" in w]
        assert not q_warns

    def test_answer_without_terminal_punctuation_warns(self):
        b = Block(speaker_id=1, text="Yes I did", raw_text="", block_type=BlockType.ANSWER)
        result = validate_blocks([b])
        assert [w for w in result.warnings if "Answer" in w]

    def test_answer_with_period_no_warning(self):
        b = Block(speaker_id=1, text="Yes, I did.", raw_text="", block_type=BlockType.ANSWER)
        result = validate_blocks([b])
        a_warns = [w for w in result.warnings if "Answer" in w and "punctuation" in w]
        assert not a_warns

    def test_answer_with_exclamation_no_warning(self):
        b = Block(speaker_id=1, text="Absolutely not!", raw_text="", block_type=BlockType.ANSWER)
        result = validate_blocks([b])
        a_warns = [w for w in result.warnings if "Answer" in w and "punctuation" in w]
        assert not a_warns

    def test_answer_with_question_mark_no_warning(self):
        b = Block(
            speaker_id=1,
            text="Are you sure that's right?",
            raw_text="",
            block_type=BlockType.ANSWER,
        )
        result = validate_blocks([b])
        a_warns = [w for w in result.warnings if "Answer" in w and "punctuation" in w]
        assert not a_warns

    def test_empty_block_text_not_warned(self):
        b = Block(speaker_id=1, text="", raw_text="", block_type=BlockType.ANSWER)
        result = validate_blocks([b])
        a_warns = [w for w in result.warnings if "Answer" in w and "punctuation" in w]
        assert not a_warns

    def test_all_correct_blocks_produce_no_punctuation_warnings(self):
        q = Block(
            speaker_id=2,
            text="Did you witness the incident?",
            raw_text="",
            block_type=BlockType.QUESTION,
            speaker_role="EXAMINING_ATTORNEY",
        )
        a = Block(
            speaker_id=1,
            text="Yes, I was there.",
            raw_text="",
            block_type=BlockType.ANSWER,
            speaker_role="WITNESS",
        )
        result = validate_blocks([q, a])
        punc_warns = [
            w
            for w in result.warnings
            if "Question" in w and "?" in w or "Answer" in w and "punctuation" in w
        ]
        assert not punc_warns


class TestPhase5ExitGate:
    def test_ellipsis_not_double_spaced(self):
        from formatter import normalize_sentence_spacing
        result = normalize_sentence_spacing("Witness said . . . Yes.")
        assert ". . .  " not in result
        assert ". . ." in result

    def test_format_transcript_has_skip_parameter(self):
        from formatter import format_transcript
        sig = inspect.signature(format_transcript)
        assert "skip_corrections_already_applied" in sig.parameters

    def test_sp_single_space_produces_bold(self):
        from spec_engine.emitter import create_document, emit_sp_line
        doc = create_document()
        emit_sp_line(doc, "MR. BOYCE: Objection.")
        assert any(r.bold for r in doc.paragraphs[0].runs)

    def test_standard_tabs_constant_exists(self):
        from spec_engine.emitter import _STANDARD_TABS
        assert len(_STANDARD_TABS) == 4

    def test_lines_per_page_is_25(self):
        from spec_engine.emitter import LineNumberTracker
        assert LineNumberTracker.LINES_PER_PAGE == 25

    def test_yes_period_vs_question_differ(self):
        assert _normalize_for_compare("Yes.") != _normalize_for_compare("Yes?")

    def test_colloquy_witness_warns(self):
        b = Block(speaker_id=1, text="Test.", raw_text="", block_type=BlockType.COLLOQUY, speaker_role="WITNESS")
        result = validate_blocks([b])
        assert any("COLLOQUY" in w for w in result.warnings)

    def test_question_without_mark_warns(self):
        b = Block(speaker_id=2, text="Did you see it", raw_text="", block_type=BlockType.QUESTION)
        result = validate_blocks([b])
        assert any("Question" in w for w in result.warnings)
