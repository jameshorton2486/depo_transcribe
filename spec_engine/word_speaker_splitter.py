"""Split utterance blocks when per-word speaker IDs indicate turn changes."""

from __future__ import annotations

import copy
import re
from typing import List

from .models import Block, Word
from .qa_fixer import STANDALONE_ANSWER_WORDS


MIN_FOREIGN_RUN_WORDS = 2
_WORD_CLEAN_RE = re.compile(r"^[\W_]+|[\W_]+$")


def _run_text(words: list[Word]) -> str:
    return " ".join((w.text or "").strip() for w in words if (w.text or "").strip())


def _copy_meta(block: Block) -> dict:
    return dict(block.meta) if isinstance(block.meta, dict) else {}


def _normalize_word_token(text: str) -> str:
    return _WORD_CLEAN_RE.sub("", (text or "").strip().lower())


def _is_standalone_answer_run(run_words: list[Word]) -> bool:
    tokens = [_normalize_word_token(word.text or "") for word in run_words]
    tokens = [token for token in tokens if token]
    if not tokens:
        return False
    return all(token in STANDALONE_ANSWER_WORDS for token in tokens)


def _should_preserve_split_run(run_words: list[Word]) -> bool:
    return len(run_words) >= MIN_FOREIGN_RUN_WORDS or _is_standalone_answer_run(run_words)


def _retag_block(block: Block, speaker_id: int) -> Block:
    retagged = copy.deepcopy(block)
    retagged.speaker_id = speaker_id
    retagged.meta = _copy_meta(block)
    retagged.meta["split_reason"] = "per_word_speaker_retag"
    retagged.meta["split_from_word_speaker"] = True
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


def _merge_pending_noise(
    consolidated: list[tuple[int | None, list[Word]]],
    pending_noise: list[Word],
) -> list[tuple[int | None, list[Word]]]:
    if not pending_noise:
        return consolidated
    if not consolidated:
        return consolidated

    speaker, words = consolidated[0]
    consolidated[0] = (speaker, list(pending_noise) + list(words))
    return consolidated


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
            if speaker is not None and speaker != block.speaker_id and _should_preserve_split_run(runs[0][1]):
                split_blocks.append(_retag_block(block, speaker))
            else:
                split_blocks.append(block)
            continue

        consolidated: list[tuple[int | None, list[Word]]] = []
        pending_noise: list[Word] = []

        for speaker, run_words in runs:
            run_words = list(run_words)
            if block.speaker_id is not None and speaker == block.speaker_id:
                if pending_noise:
                    run_words = list(pending_noise) + run_words
                    pending_noise = []
                consolidated.append((speaker, run_words))
                continue

            if _should_preserve_split_run(run_words):
                if pending_noise:
                    run_words = list(pending_noise) + run_words
                    pending_noise = []
                consolidated.append((speaker, run_words))
                continue

            if consolidated:
                prev_speaker, prev_words = consolidated[-1]
                consolidated[-1] = (prev_speaker, prev_words + run_words)
            else:
                pending_noise.extend(run_words)

        consolidated = _merge_pending_noise(consolidated, pending_noise)
        if not consolidated:
            split_blocks.append(block)
            continue

        merged: list[tuple[int | None, list[Word]]] = []
        for speaker, run_words in consolidated:
            if merged and merged[-1][0] == speaker:
                merged[-1] = (speaker, merged[-1][1] + run_words)
            else:
                merged.append((speaker, run_words))
        consolidated = merged

        if len(consolidated) == 1:
            speaker, run_words = consolidated[0]
            if speaker is not None and speaker != block.speaker_id and _should_preserve_split_run(run_words):
                split_blocks.append(_retag_block(block, speaker))
            else:
                split_blocks.append(block)
            continue

        total_subs = len(consolidated)
        for idx, (speaker, run_words) in enumerate(consolidated):
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
