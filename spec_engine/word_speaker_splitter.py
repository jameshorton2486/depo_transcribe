"""Split utterance blocks when per-word speaker IDs indicate turn changes."""

from __future__ import annotations

import copy
from typing import List

from .models import Block, Word


def _run_text(words: list[Word]) -> str:
    return " ".join((w.text or "").strip() for w in words if (w.text or "").strip())


def _copy_meta(block: Block) -> dict:
    return dict(block.meta) if isinstance(block.meta, dict) else {}


def _retag_block(block: Block, speaker_id: int) -> Block:
    retagged = copy.deepcopy(block)
    retagged.speaker_id = speaker_id
    retagged.meta = _copy_meta(block)
    retagged.meta["split_reason"] = "per_word_speaker_retag"
    retagged.meta["original_block_speaker_id"] = block.speaker_id
    return retagged


def _split_block(
    block: Block,
    speaker_id: int | None,
    run_words: list[Word],
    *,
    sub_index: int,
    total_subs: int,
) -> Block:
    split_meta = _copy_meta(block)
    split_meta["split_reason"] = "per_word_speaker_drift"
    split_meta["split_sub_index"] = sub_index
    split_meta["split_total_subs"] = total_subs
    if sub_index > 0:
        # Corrections are recorded at block level by earlier deterministic
        # passes. Duplicating them on every split fragment inflates correction
        # counts and logs.
        split_meta.pop("corrections", None)
        split_meta["split_from_word_speaker"] = True

    text = _run_text(run_words)
    new_block = Block(
        text=text,
        raw_text=text,
        speaker_id=speaker_id if speaker_id is not None else block.speaker_id,
        speaker_name=block.speaker_name,
        speaker_role=block.speaker_role,
        block_type=block.block_type,
        words=list(run_words),
        flags=list(block.flags),
        meta=split_meta,
    )
    if run_words:
        if run_words[0].start is not None:
            new_block.meta["start"] = run_words[0].start
        if run_words[-1].end is not None:
            new_block.meta["end"] = run_words[-1].end
    return new_block


def split_mixed_speaker_utterances(blocks: List[Block]) -> List[Block]:
    """Split blocks at speaker-boundary runs derived from Word.speaker values."""
    split_blocks: list[Block] = []

    for block in blocks:
        words = list(getattr(block, "words", []) or [])
        if not words:
            split_blocks.append(block)
            continue

        if not any(getattr(word, "speaker", None) is not None for word in words):
            split_blocks.append(block)
            continue

        runs: list[tuple[int | None, list[Word]]] = []
        for word in words:
            speaker = getattr(word, "speaker", None)
            if not runs or runs[-1][0] != speaker:
                runs.append((speaker, [word]))
            else:
                runs[-1][1].append(word)

        if len(runs) == 1:
            speaker = runs[0][0]
            if speaker is not None and speaker != block.speaker_id:
                split_blocks.append(_retag_block(block, speaker))
            else:
                split_blocks.append(block)
            continue

        total_subs = len(runs)
        for idx, (speaker, run_words) in enumerate(runs):
            split_blocks.append(
                _split_block(
                    block,
                    speaker,
                    run_words,
                    sub_index=idx,
                    total_subs=total_subs,
                )
            )

    return split_blocks
