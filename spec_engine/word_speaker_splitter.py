"""Split utterance blocks when per-word speaker IDs indicate turn changes."""

from __future__ import annotations

from typing import List

from .models import Block


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

        runs: list[tuple[int | None, list]] = []
        for word in words:
            speaker = getattr(word, "speaker", None)
            if not runs or runs[-1][0] != speaker:
                runs.append((speaker, [word]))
            else:
                runs[-1][1].append(word)

        if len(runs) == 1:
            speaker = runs[0][0]
            if speaker is not None:
                block.speaker_id = speaker
            split_blocks.append(block)
            continue

        for idx, (speaker, run_words) in enumerate(runs):
            new_meta = dict(block.meta)
            if idx > 0:
                # Corrections are recorded at block level by earlier deterministic
                # passes. Duplicating them on every split fragment inflates
                # correction counts and logs.
                new_meta.pop("corrections", None)

            new_block = Block(
                text=" ".join(
                    (w.text or "").strip() for w in run_words if (w.text or "").strip()
                ),
                raw_text=" ".join(
                    (w.text or "").strip() for w in run_words if (w.text or "").strip()
                ),
                speaker_id=speaker if speaker is not None else block.speaker_id,
                speaker_name=block.speaker_name,
                speaker_role=block.speaker_role,
                block_type=block.block_type,
                words=list(run_words),
                flags=list(block.flags),
                meta=new_meta,
            )
            if idx > 0:
                new_block.meta["split_from_word_speaker"] = True
            split_blocks.append(new_block)

    return split_blocks
