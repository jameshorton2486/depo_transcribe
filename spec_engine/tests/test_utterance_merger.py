"""
Tests for spec_engine.utterance_merger.

Coverage targets:
  - merge / non-merge decisions on punctuation boundaries
  - speaker-change boundary respect
  - gap-ceiling safety check
  - Caram-style fragment cascade
  - word, timing, corrections, and audit metadata preservation
  - stale split metadata removal
  - idempotency and input immutability
"""

from __future__ import annotations

from typing import List, Optional

from spec_engine.models import Block, Word
from spec_engine.utterance_merger import (
    MAX_MERGE_GAP_SECONDS,
    merge_fragmented_utterances,
)


def _word(text: str, start: float, end: float, speaker: Optional[int] = None) -> Word:
    return Word(text=text, start=start, end=end, confidence=0.95, speaker=speaker)


def _block(
    text: str,
    speaker_id: Optional[int],
    *,
    start: Optional[float] = None,
    end: Optional[float] = None,
    words: Optional[List[Word]] = None,
    meta: Optional[dict] = None,
) -> Block:
    if words is None and start is not None and end is not None:
        words = [_word(text or "x", start, end, speaker_id)]
    if words is None:
        words = []
    full_meta = dict(meta or {})
    if start is not None and "start" not in full_meta:
        full_meta["start"] = start
    if end is not None and "end" not in full_meta:
        full_meta["end"] = end
    return Block(
        text=text,
        raw_text=text,
        speaker_id=speaker_id,
        words=words,
        meta=full_meta,
    )


def test_empty_input_returns_empty_list():
    assert merge_fragmented_utterances([]) == []


def test_single_block_input_returned_unchanged():
    block = _block("hello", 1, start=1.0, end=1.5)
    result = merge_fragmented_utterances([block])
    assert len(result) == 1
    assert result[0].text == "hello"
    assert result[0].speaker_id == 1
    assert "merge_reason" not in result[0].meta


def test_merge_two_fragments_with_no_punctuation():
    a = _block("Have you, uh,", 1, start=1.0, end=2.0)
    b = _block("reviewed any documents?", 1, start=2.5, end=3.5)
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 1
    assert result[0].text == "Have you, uh, reviewed any documents?"
    assert result[0].meta["merge_reason"] == "utt_split_fragment_coalesce"
    assert result[0].meta["merged_from_count"] == 2


def test_no_merge_when_prev_ends_with_period():
    a = _block("That is correct.", 1, start=1.0, end=2.0)
    b = _block("And then what?", 1, start=2.2, end=3.0)
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 2


def test_no_merge_across_speaker_change():
    a = _block("Have you, uh,", 1, start=1.0, end=2.0)
    b = _block("Yes, I have.", 0, start=2.2, end=3.0)
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 2
    assert [r.speaker_id for r in result] == [1, 0]


def test_no_merge_when_gap_exceeds_ceiling():
    a = _block("Have you, uh,", 1, start=1.0, end=2.0)
    b = _block("reviewed?", 1, start=2.0 + MAX_MERGE_GAP_SECONDS + 0.5, end=10.0)
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 2


def test_merge_when_gap_under_ceiling():
    a = _block("Have you, uh,", 1, start=1.0, end=2.0)
    b = _block("reviewed?", 1, start=2.0 + MAX_MERGE_GAP_SECONDS - 0.1, end=4.0)
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 1


def test_caram_six_fragment_cascade_merges_into_one():
    fragments = [
        _block("Yes. Okay. And", 1, start=1.0, end=2.0),
        _block("then I have", 1, start=2.3, end=2.8),
        _block("documentation in the record on page 1 41, um, that,", 1, start=3.0, end=5.0),
        _block("let's see,", 1, start=5.3, end=5.8),
        _block("at", 1, start=6.0, end=6.2),
        _block("Doctor. Anders is still attempting to rotate the baby in the pelvis.", 1, start=6.5, end=11.0),
    ]
    result = merge_fragmented_utterances(fragments)
    assert len(result) == 1
    assert result[0].text.startswith("Yes. Okay. And then I have")
    assert result[0].text.endswith("rotate the baby in the pelvis.")
    assert result[0].meta["merged_from_count"] == 6
    assert result[0].meta["start"] == 1.0
    assert result[0].meta["end"] == 11.0


def test_merged_block_concatenates_word_lists_and_corrections_audit():
    a = _block(
        "Have you, uh,",
        1,
        start=1.0,
        end=2.0,
        meta={"corrections": [{"original": "doctor", "corrected": "Doctor"}]},
    )
    b = _block(
        "reviewed?",
        1,
        start=2.3,
        end=3.0,
        meta={"corrections": [{"original": "Karam", "corrected": "Caram"}]},
    )
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 1
    assert result[0].meta["corrections"] == [
        {"original": "doctor", "corrected": "Doctor"},
        {"original": "Karam", "corrected": "Caram"},
    ]


def test_merged_block_takes_earliest_start_latest_end():
    a = _block("Have you, uh,", 1, start=10.0, end=11.0)
    b = _block("reviewed?", 1, start=11.3, end=11.8)
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 1
    assert result[0].meta["start"] == 10.0
    assert result[0].meta["end"] == 11.8


def test_merge_drops_stale_split_metadata_from_fragments():
    a = _block(
        "Have you, uh,",
        1,
        start=1.0,
        end=2.0,
        meta={
            "split_reason": "per_word_speaker_drift",
            "split_from_word_speaker": True,
            "split_sub_index": 0,
            "split_total_subs": 2,
            "original_block_speaker_id": 2,
        },
    )
    b = _block(
        "reviewed?",
        1,
        start=2.3,
        end=3.0,
        meta={
            "split_reason": "per_word_speaker_drift",
            "split_from_word_speaker": True,
            "split_sub_index": 1,
            "split_total_subs": 2,
            "original_block_speaker_id": 2,
        },
    )
    result = merge_fragmented_utterances([a, b])
    assert len(result) == 1
    assert "split_reason" not in result[0].meta
    assert "split_from_word_speaker" not in result[0].meta
    assert "split_sub_index" not in result[0].meta
    assert "split_total_subs" not in result[0].meta
    assert "original_block_speaker_id" not in result[0].meta
    assert result[0].meta["merge_reason"] == "utt_split_fragment_coalesce"


def test_input_blocks_are_not_mutated():
    a = _block("Have you, uh,", 1, start=1.0, end=2.0, meta={"corrections": [{"x": 1}]})
    b = _block("reviewed?", 1, start=2.3, end=3.0)
    original_a_text = a.text
    original_a_meta = dict(a.meta)
    original_b_text = b.text

    _ = merge_fragmented_utterances([a, b])

    assert a.text == original_a_text
    assert a.meta == original_a_meta
    assert b.text == original_b_text


def test_idempotent_running_twice_equals_running_once():
    fragments = [
        _block("First,", 1, start=1.0, end=1.5),
        _block("then second,", 1, start=1.7, end=2.5),
        _block("then third.", 1, start=2.7, end=3.5),
        _block("Different turn.", 0, start=4.0, end=4.5),
    ]
    once = merge_fragmented_utterances(fragments)
    twice = merge_fragmented_utterances(once)
    assert len(once) == len(twice)
    for a, b in zip(once, twice):
        assert a.text == b.text
        assert a.speaker_id == b.speaker_id
        assert a.meta.get("merged_from_count") == b.meta.get("merged_from_count")
