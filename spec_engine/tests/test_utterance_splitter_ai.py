"""Tests for the AI splitter logic in spec_engine.utterance_splitter.

All AI calls are mocked. No network access required.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from spec_engine.utterance_splitter import (
    SplitterMetadata,
    _strip_code_fences,
    _validate_splits,
    split_utterances,
)


def _ai_response(text: str) -> Any:
    """Build a mock object that mimics anthropic.types.Message."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _client_with_responses(*responses: str) -> MagicMock:
    """Build a mock Anthropic client whose messages.create returns
    successive responses on each call."""
    client = MagicMock()
    client.messages.create.side_effect = [_ai_response(r) for r in responses]
    return client


def _utt(text: str) -> dict:
    return {"speaker": 1, "speaker_label": "Speaker 1", "transcript": text}


# ── _strip_code_fences ────────────────────────────────────────────────────────


class TestStripCodeFences:
    def test_no_fences(self):
        assert _strip_code_fences('[{"text": "x", "type": "colloquy"}]') == \
               '[{"text": "x", "type": "colloquy"}]'

    def test_json_fences(self):
        raw = '```json\n[{"text": "x", "type": "colloquy"}]\n```'
        assert _strip_code_fences(raw) == '[{"text": "x", "type": "colloquy"}]'

    def test_bare_fences(self):
        raw = '```\n[{"text": "x", "type": "colloquy"}]\n```'
        assert _strip_code_fences(raw) == '[{"text": "x", "type": "colloquy"}]'


# ── _validate_splits ──────────────────────────────────────────────────────────


class TestValidateSplits:
    def test_valid_two_part_split(self):
        original = "Did you see it? Yes I did."
        splits = [
            {"text": "Did you see it?", "type": "question"},
            {"text": "Yes I did.", "type": "answer"},
        ]
        ok, reason = _validate_splits(original, splits)
        assert ok, reason

    def test_word_added_fails(self):
        original = "Did you see it?"
        splits = [{"text": "Did you really see it?", "type": "question"}]
        ok, _ = _validate_splits(original, splits)
        assert ok is False

    def test_empty_text_fails(self):
        ok, _ = _validate_splits("hello", [{"text": "", "type": "colloquy"}])
        assert ok is False

    def test_invalid_type_fails(self):
        ok, _ = _validate_splits(
            "hello",
            [{"text": "hello", "type": "directive"}],
        )
        assert ok is False

    def test_missing_keys_fails(self):
        ok, _ = _validate_splits("hello", [{"text": "hello"}])
        assert ok is False

    def test_empty_list_fails(self):
        ok, _ = _validate_splits("hello", [])
        assert ok is False

    def test_whitespace_normalization_passes(self):
        # Splits with extra spaces around them, joined with single space,
        # should still match the original.
        original = "Did you see it? Yes I did."
        splits = [
            {"text": "  Did you see it?  ", "type": "question"},
            {"text": "Yes I did.  ", "type": "answer"},
        ]
        ok, _ = _validate_splits(original, splits)
        assert ok


# ── split_utterances behavior ─────────────────────────────────────────────────


class TestSplitUtterancesNonFlagged:
    def test_non_flagged_passes_through(self):
        # Short utterance, never flagged.
        utts = [_utt("Yes.")]
        client = MagicMock()  # should never be called
        out, meta = split_utterances(utts, client=client)
        assert out == utts
        assert meta.flagged_count == 0
        assert meta.ai_calls == 0
        client.messages.create.assert_not_called()


class TestSplitUtterancesFlagged:
    _MERGED = (
        "Have not viewed or read the depositions of Doctor Green or Doctor Fisher? "
        "No, have not. Have you spoken with them about their depositions? I have not."
    )

    def test_successful_split(self):
        ai_json = json.dumps([
            {"text": "Have not viewed or read the depositions of Doctor Green or Doctor Fisher?", "type": "question"},
            {"text": "No, have not.", "type": "answer"},
            {"text": "Have you spoken with them about their depositions?", "type": "question"},
            {"text": "I have not.", "type": "answer"},
        ])
        utts = [_utt(self._MERGED)]
        client = _client_with_responses(ai_json)
        out, meta = split_utterances(utts, client=client)

        assert meta.flagged_count == 1
        assert meta.ai_calls == 1
        assert meta.validation_failures == 0
        assert len(out) == 4
        assert out[0]["_split_source"] == "ai"
        assert out[0]["_split_type_hint"] == "question"
        assert out[3]["_split_type_hint"] == "answer"
        # Speaker metadata is inherited.
        assert out[0]["speaker"] == 1

    def test_invalid_json_falls_back(self):
        utts = [_utt(self._MERGED)]
        client = _client_with_responses("not valid json {")
        out, meta = split_utterances(utts, client=client)
        assert out == utts
        assert meta.ai_calls == 1
        assert meta.validation_failures == 1

    def test_word_added_falls_back(self):
        bad_json = json.dumps([
            {"text": "Have not viewed or read the depositions of Doctor Green or Doctor Fisher?", "type": "question"},
            {"text": "Absolutely not, have not.", "type": "answer"},   # added "Absolutely"
            {"text": "Have you spoken with them about their depositions?", "type": "question"},
            {"text": "I have not.", "type": "answer"},
        ])
        utts = [_utt(self._MERGED)]
        client = _client_with_responses(bad_json)
        out, meta = split_utterances(utts, client=client)
        assert out == utts
        assert meta.validation_failures == 1

    def test_single_element_array_treated_as_noop(self):
        ai_json = json.dumps([
            {"text": self._MERGED, "type": "colloquy"},
        ])
        utts = [_utt(self._MERGED)]
        client = _client_with_responses(ai_json)
        out, meta = split_utterances(utts, client=client)
        # Single-element AI response = no-op; original utterance preserved.
        assert len(out) == 1
        assert out[0] == utts[0]
        assert meta.ai_calls == 1
        assert meta.validation_failures == 0

    def test_cache_hit_avoids_second_call(self):
        ai_json = json.dumps([
            {"text": "Have not viewed or read the depositions of Doctor Green or Doctor Fisher?", "type": "question"},
            {"text": "No, have not.", "type": "answer"},
            {"text": "Have you spoken with them about their depositions?", "type": "question"},
            {"text": "I have not.", "type": "answer"},
        ])
        # Two identical merged utterances.
        utts = [_utt(self._MERGED), _utt(self._MERGED)]
        client = _client_with_responses(ai_json)  # only one response prepared
        out, meta = split_utterances(utts, client=client)
        assert meta.ai_calls == 1
        assert meta.cache_hits == 1
        # 4 splits per merged input × 2 = 8 outputs
        assert len(out) == 8


class TestSplitUtterancesCostCap:
    _MERGED_A = (
        "Did you see the report on Tuesday? Yes I did see it. "
        "How long did it take you to read it through? About an hour."
    )
    _MERGED_B = (
        "Where were you on Friday afternoon? At my office. "
        "Who else was there with you that day? My assistant Sarah was there."
    )
    _MERGED_C = (
        "Have you ever been deposed before this case? Yes once. "
        "When was that prior deposition taken? About three years ago in Dallas."
    )

    def test_cap_one_processes_one(self):
        # Three flagged utterances, cap at 1.
        utts = [
            _utt(self._MERGED_A),
            _utt(self._MERGED_B),
            _utt(self._MERGED_C),
        ]
        ai_json_a = json.dumps([
            {"text": "Did you see the report on Tuesday?", "type": "question"},
            {"text": "Yes I did see it.", "type": "answer"},
            {"text": "How long did it take you to read it through?", "type": "question"},
            {"text": "About an hour.", "type": "answer"},
        ])
        # Only one AI response will be needed; the other two should not invoke.
        client = _client_with_responses(ai_json_a)
        out, meta = split_utterances(utts, max_ai_calls=1, client=client)
        assert meta.ai_calls == 1
        assert meta.skipped_over_cap == 2
        # First utterance produced 4 splits; other two passed through unchanged.
        assert len(out) == 4 + 1 + 1
        assert client.messages.create.call_count == 1
