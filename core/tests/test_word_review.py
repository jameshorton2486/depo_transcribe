"""Tests for core/word_review.py — Phase 1 of the proofreading review
system. Pure-function helpers over Deepgram word-level data; no UI, no
transcript mutation."""
from __future__ import annotations

import copy

import pytest

from core.word_review import WordReviewItem, build_review_items


def _word(
    word: str = "the",
    confidence: float = 0.99,
    *,
    punctuated_word: str | None = None,
    start: float = 1.0,
    end: float = 1.5,
    speaker: int | None = 0,
) -> dict:
    """Minimal Deepgram-shape word dict for tests. Mirrors the fields
    saved into the per-run JSON by core/job_runner.py."""
    raw: dict = {
        "word": word,
        "confidence": confidence,
        "start": start,
        "end": end,
    }
    if punctuated_word is not None:
        raw["punctuated_word"] = punctuated_word
    if speaker is not None:
        raw["speaker"] = speaker
    return raw


def test_below_threshold_words_become_review_items():
    words = [
        _word("Caram", confidence=0.62),
        _word("Karam", confidence=0.55, punctuated_word="Karam,"),
    ]
    items = build_review_items(words, threshold=0.75)
    assert len(items) == 2
    assert all(isinstance(item, WordReviewItem) for item in items)
    assert [item.word for item in items] == ["Caram", "Karam"]
    # Each item's `index` is its position in the resulting list.
    assert [item.index for item in items] == [0, 1]


def test_above_threshold_words_are_ignored():
    words = [
        _word("the", confidence=0.99),
        _word("witness", confidence=0.90),
        _word("Caram", confidence=0.62),
    ]
    items = build_review_items(words, threshold=0.75)
    assert len(items) == 1
    assert items[0].word == "Caram"


def test_threshold_is_strictly_below():
    """A word with confidence exactly equal to the threshold is NOT
    flagged. Only confidence < threshold qualifies."""
    items = build_review_items([_word(confidence=0.75)], threshold=0.75)
    assert items == []


def test_punctuated_word_is_preferred_when_available():
    words = [
        _word("karam", confidence=0.5, punctuated_word="Karam,"),
        _word("yes", confidence=0.5, punctuated_word=""),
    ]
    items = build_review_items(words)
    # First word: punctuated form wins.
    assert items[0].word == "karam"
    assert items[0].punctuated_word == "Karam,"
    # Empty punctuated_word should fall back to the bare word.
    assert items[1].punctuated_word == "yes"


def test_punctuated_word_falls_back_to_word_when_missing():
    words = [_word("karam", confidence=0.5)]  # no punctuated_word key
    items = build_review_items(words)
    assert items[0].punctuated_word == "karam"


def test_timestamps_are_preserved():
    words = [_word(confidence=0.5, start=12.34, end=12.78)]
    items = build_review_items(words)
    assert items[0].start == pytest.approx(12.34)
    assert items[0].end == pytest.approx(12.78)


def test_missing_speaker_is_allowed():
    words = [_word(confidence=0.5, speaker=None)]
    items = build_review_items(words)
    assert items[0].speaker is None


def test_speaker_is_coerced_to_int_when_present():
    words = [
        _word(confidence=0.5, speaker=0),
        _word(confidence=0.5, speaker="2"),
    ]
    items = build_review_items(words)
    assert items[0].speaker == 0
    assert items[1].speaker == 2


def test_unparseable_speaker_becomes_none():
    raw = _word(confidence=0.5)
    raw["speaker"] = "not-a-number"
    items = build_review_items([raw])
    assert items[0].speaker is None


def test_empty_words_list_returns_empty():
    assert build_review_items([]) == []
    assert build_review_items(None) == []  # type: ignore[arg-type]


def test_input_dictionaries_are_not_mutated():
    """The helper must not modify the caller's word dicts. We snapshot
    the input via deepcopy and assert equality after the call."""
    words = [
        _word("Caram", confidence=0.62, punctuated_word="Caram,", speaker=1),
        _word("the", confidence=0.99),
    ]
    snapshot = copy.deepcopy(words)
    build_review_items(words)
    assert words == snapshot


def test_words_missing_confidence_are_skipped():
    """A word entry without a 'confidence' key is treated as
    not-low-confidence (assumed 1.0). This avoids surfacing
    punctuation-only sentinel rows that lack scoring."""
    raw = {"word": "the", "start": 1.0, "end": 1.2}
    items = build_review_items([raw], threshold=0.5)
    assert items == []


def test_non_dict_entries_are_skipped():
    items = build_review_items(["bogus", None, _word(confidence=0.5)])  # type: ignore[list-item]
    assert len(items) == 1
    assert items[0].word == "the"


def test_threshold_at_one_flags_everything():
    """Edge: threshold=1.0 means every confidence < 1.0 is flagged.
    A word with confidence=1.0 still passes through cleanly."""
    words = [
        _word("a", confidence=0.99),
        _word("b", confidence=1.0),
        _word("c", confidence=0.0),
    ]
    items = build_review_items(words, threshold=1.0)
    assert [item.word for item in items] == ["a", "c"]
