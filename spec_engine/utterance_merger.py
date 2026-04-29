"""
spec_engine/utterance_merger.py

Re-fuses consecutive same-speaker blocks that Deepgram fragmented at
within-turn pauses. Runs early in the pipeline, before any text
correction or classification stage.

WHY THIS EXISTS
---------------
With `utt_split` set aggressively, Deepgram emits a new utterance every
time inter-word silence exceeds the threshold. For a single attorney
sentence with normal disfluencies, the result is a fragmentation cascade.
Downstream classifier, Q/A repair, and paragraph splitter all inherit
this fragmentation; none of them merge fragments back together.

This stage walks the block list and merges consecutive blocks where ALL
of these conditions hold:

  1. Same speaker_id.
  2. The prior block's text does NOT end on terminal punctuation
     (.?!), meaning the speaker had not finished a sentence.
  3. The inter-block gap is below MAX_MERGE_GAP_SECONDS — a safety
     ceiling to avoid merging across genuinely long pauses.

DESIGN NOTES
------------
- Conservative AND-of-conditions: false positives (merging two real
  turns) are catastrophic for legal record integrity; false negatives
  (failing to merge a fragment) just leave the existing visual
  fragmentation in place.
- Operates on data already in the block stream — no new API calls,
  no model inference, no regex on text content.
- Preserves all per-word data, timing, and corrections audit by
  combining word lists, taking the earliest start and latest end, and
  concatenating any block-level corrections lists.
- Removes stale split metadata when blocks are merged so the merged
  block has a single, accurate audit shape.
- Idempotent: running the stage twice on the same blocks produces the
  same result as running it once.

INSERTION POINT
---------------
Run AFTER `split_mixed_speaker_utterances` (so word-level speaker
disagreements have already been resolved into per-speaker blocks) and
BEFORE `apply_corrections` (so text-correction stages see coalesced
attorney/witness turns rather than utt_split cascades). See
`spec_engine/processor.py::process_blocks`.

LAYER COMPLIANCE
----------------
This file lives entirely inside `spec_engine/`. No `pipeline/`, `core/`,
`ui/`, or `ufm_engine/` symbols are imported or modified.
"""

from __future__ import annotations

import copy
from typing import List, Optional

from .models import Block


# Inter-block gap ceiling. Larger than typical utt_split fragmentation
# gaps but smaller than typical turn-change pauses.
MAX_MERGE_GAP_SECONDS = 1.5

# Characters considered terminal — if the prior block's last significant
# character is one of these, do not merge.
_TERMINAL_PUNCT = ".?!"

# Trailing characters to strip when finding the last "real" character.
_STRIPPABLE_TRAILING = "\"'\u201C\u201D\u2018\u2019)]} \t\r\n"

# Ellipsis variants — these END a fragment but signal CONTINUATION.
_ELLIPSIS_TOKENS = ("...", "\u2026")

_STALE_SPLIT_META_KEYS = (
    "split_reason",
    "split_from_word_speaker",
    "split_sub_index",
    "split_total_subs",
    "original_block_speaker_id",
)


def _ends_with_continuation(text: str) -> bool:
    """
    Return True if `text` ends in a way that suggests the speaker had
    not finished their thought.
    """
    if not text:
        return False
    stripped = text.rstrip()
    while stripped and stripped[-1] in _STRIPPABLE_TRAILING:
        stripped = stripped[:-1]
    if not stripped:
        return False
    for token in _ELLIPSIS_TOKENS:
        if stripped.endswith(token):
            return True
    return stripped[-1] not in _TERMINAL_PUNCT


def _block_end_time(block: Block) -> Optional[float]:
    """Return the latest known end-time for the block, or None."""
    words = getattr(block, "words", None) or []
    if words and words[-1].end is not None:
        return float(words[-1].end)
    meta = getattr(block, "meta", None) or {}
    end = meta.get("end")
    if end is not None:
        return float(end)
    return None


def _block_start_time(block: Block) -> Optional[float]:
    """Return the earliest known start-time for the block, or None."""
    words = getattr(block, "words", None) or []
    if words and words[0].start is not None:
        return float(words[0].start)
    meta = getattr(block, "meta", None) or {}
    start = meta.get("start")
    if start is not None:
        return float(start)
    return None


def _gap_seconds(prev: Block, current: Block) -> Optional[float]:
    """Return the gap (in seconds) between `prev` and `current`."""
    prev_end = _block_end_time(prev)
    current_start = _block_start_time(current)
    if prev_end is None or current_start is None:
        return None
    return current_start - prev_end


def _same_speaker(prev: Block, current: Block) -> bool:
    """Return True if both blocks carry the same non-None speaker_id."""
    prev_speaker = getattr(prev, "speaker_id", None)
    current_speaker = getattr(current, "speaker_id", None)
    if prev_speaker is None or current_speaker is None:
        return False
    return prev_speaker == current_speaker


def _should_merge(prev: Block, current: Block) -> bool:
    """Decide whether `current` should be merged into `prev`."""
    if not _same_speaker(prev, current):
        return False
    if not _ends_with_continuation(getattr(prev, "text", "") or ""):
        return False
    gap = _gap_seconds(prev, current)
    if gap is not None and gap > MAX_MERGE_GAP_SECONDS:
        return False
    return True


def _merge_text(prev_text: str, current_text: str) -> str:
    """Combine two text fragments with a single intervening space."""
    left = (prev_text or "").rstrip()
    right = (current_text or "").lstrip()
    if not left:
        return right
    if not right:
        return left
    return f"{left} {right}"


def _merge_into(prev: Block, current: Block) -> Block:
    """Return a new Block representing the merge of `current` into `prev`."""
    merged = copy.deepcopy(prev)

    merged.text = _merge_text(prev.text, current.text)
    merged.raw_text = merged.text

    prev_words = list(getattr(prev, "words", None) or [])
    current_words = list(getattr(current, "words", None) or [])
    merged.words = prev_words + current_words

    merged.meta = dict(getattr(prev, "meta", None) or {})
    current_meta = dict(getattr(current, "meta", None) or {})

    # Merging supersedes any prior split audit trail. Keep the merge
    # provenance, but remove stale split-specific metadata.
    for key in _STALE_SPLIT_META_KEYS:
        merged.meta.pop(key, None)

    prev_start = _block_start_time(prev)
    current_end = _block_end_time(current)
    if prev_start is not None:
        merged.meta["start"] = prev_start
    if current_end is not None:
        merged.meta["end"] = current_end

    prev_corrections = merged.meta.get("corrections")
    current_corrections = current_meta.get("corrections")
    if prev_corrections or current_corrections:
        merged.meta["corrections"] = list(prev_corrections or []) + list(
            current_corrections or []
        )

    prev_count = int(merged.meta.get("merged_from_count", 1) or 1)
    current_count = int(current_meta.get("merged_from_count", 1) or 1)
    merged.meta["merged_from_count"] = prev_count + current_count
    merged.meta["merge_reason"] = "utt_split_fragment_coalesce"

    return merged


def merge_fragmented_utterances(blocks: List[Block]) -> List[Block]:
    """
    Coalesce consecutive same-speaker blocks that Deepgram fragmented
    at within-turn pauses.
    """
    if not blocks:
        return []

    result: List[Block] = [copy.deepcopy(blocks[0])]
    for current in blocks[1:]:
        prev = result[-1]
        if _should_merge(prev, current):
            result[-1] = _merge_into(prev, current)
        else:
            result.append(copy.deepcopy(current))

    return result
