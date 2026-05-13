"""Parse Deepgram alt payloads into block dicts.

Step B.0 extension: each returned block dict carries an optional
`words` key containing the Deepgram word-level data that corresponds
to the block's text range. When the source data lacks the fields
needed for safe partitioning, `words` is None.

See docs/plans/_archive/verbatim_punctuation_plan_2026-05-12.md and
docs/plans/_archive/step_b0_word_carry_2026-05-12.md.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _partition_words_for_paragraph(
    all_words: list[dict[str, Any]],
    para: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Return the words from `all_words` that fall inside the paragraph's
    time range.

    Returns None when:
    - `all_words` is empty
    - The paragraph lacks `start` or `end`
    - The partition yields no matches

    The None fallback is deliberate. Downstream consumers (Step C/D)
    treat None as "no carried words for this block"; that is preferable
    to a partial or guessed list.
    """
    if not all_words:
        return None

    para_start = para.get("start")
    para_end = para.get("end")
    if para_start is None or para_end is None:
        return None

    matched: list[dict[str, Any]] = []
    for w in all_words:
        ws = w.get("start")
        we = w.get("end")
        if not isinstance(ws, (int, float)) or not isinstance(we, (int, float)):
            continue
        if ws >= para_start and we <= para_end:
            matched.append(w)
    return matched if matched else None


def build_blocks(alt):
    """Parse transcription data into structured blocks.

    Prioritizes paragraph-based parsing for better speaker grouping.
    Falls back to utterance-based parsing when no paragraphs are
    present.

    Step B.0: each block dict includes a `words` key. Value is a list
    of Deepgram word dicts when alignment to the block's time range
    succeeds, otherwise None.
    """
    blocks = []
    all_words = alt.get("words") or []

    # ================================
    # 🔥 PRIORITY 1 — PARAGRAPHS
    # ================================
    if "paragraphs" in alt and alt["paragraphs"].get("paragraphs"):
        logger.info("[BlockBuilder] Using paragraph-based parsing")

        for para in alt["paragraphs"]["paragraphs"]:
            speaker = para.get("speaker", "UNKNOWN")
            text = para.get("text", "").strip()

            if not text:
                continue

            words = _partition_words_for_paragraph(all_words, para)

            blocks.append({
                "speaker": speaker,
                "text": text,
                "type": "paragraph",
                "words": words,
            })

        return blocks

    # ================================
    # 🪵 FALLBACK — UTTERANCES
    # ================================
    if "utterances" in alt:
        logger.info("[BlockBuilder] Falling back to utterance-based parsing")

        for utt in alt["utterances"]:
            speaker = utt.get("speaker", "UNKNOWN")
            text = utt.get("text", "").strip()

            if not text:
                continue

            utt_words = utt.get("words") or None

            blocks.append({
                "speaker": speaker,
                "text": text,
                "type": "utterance",
                "words": utt_words,
            })

    return blocks
