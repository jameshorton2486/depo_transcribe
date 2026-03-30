"""
spec_engine/tests/test_ai_corrector.py

Tests for spec_engine/ai_corrector.py
All offline — no real API calls made.
Run: python -m pytest spec_engine/tests/test_ai_corrector.py -v
"""
import pytest
from spec_engine.ai_corrector import (
    _split_into_chunks,
    _renumber_scopist_flags,
    _build_user_prompt,
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
