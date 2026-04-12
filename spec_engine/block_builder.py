"""
pipeline.block_builder

Convert Deepgram JSON into structured Block objects.
This is the foundation of the block-based transcript pipeline.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from spec_engine.models import Block, Word
from spec_engine.speaker_resolver import normalize_speaker_id


def build_blocks_from_deepgram(deepgram_json: Dict[str, Any]) -> List[Block]:
    """
    Convert Deepgram utterances into structured blocks.
    """
    if "utterances" not in deepgram_json:
        raise ValueError(
            "Deepgram response missing 'utterances'. "
            "Ensure 'utterances=True' is enabled in API options."
        )

    utterances = deepgram_json.get("utterances") or []
    blocks: List[Block] = []

    for utterance in utterances:
        transcript = (utterance.get("transcript") or "").strip()
        if not transcript:
            continue
        speaker = utterance.get("speaker")
        blocks.append(
            Block(
                raw_text=utterance.get("transcript", ""),
                text=transcript,
                speaker_id=None if speaker is None else normalize_speaker_id(speaker),
                words=[
                    Word(
                        text=w.get("word", "") or "",
                        start=w.get("start") if w.get("start") is not None else 0.0,
                        end=w.get("end") if w.get("end") is not None else (
                            w.get("start") if w.get("start") is not None else 0.0
                        ),
                        confidence=w.get("confidence"),
                        speaker=w.get("speaker"),
                    )
                    for w in (utterance.get("words") or [])
                    if (w.get("word") or "").strip()
                ],
                meta={
                    "start": utterance.get("start"),
                    "end": utterance.get("end"),
                    "confidence": utterance.get("confidence"),
                },
            )
        )

    if not blocks:
        raise RuntimeError(
            "block_builder received no utterances-backed blocks; pipeline invalid."
        )

    return blocks


_TEXT_ABBREV_RE = re.compile(
    r'\b(Dr|Mr|Mrs|Ms|Jr|Sr|vs|No|Vol|Dept|Corp|Inc|Ltd|P\.C|PLLC)\.$',
    re.IGNORECASE,
)
_TEXT_SPLIT_RE = re.compile(r'(?<=[.?!])\s+(?=[A-Z])')


def build_blocks_from_text(raw_text: str) -> List[Block]:
    """
    Recover a minimal block stream from plain transcript text.
    This is a pipeline fallback, not a UI concern.
    """
    stripped = (raw_text or "").strip()
    if not stripped:
        raise ValueError("No transcript text provided.")

    parts = _TEXT_SPLIT_RE.split(stripped)
    blocks: List[Block] = []
    buffer = ""

    for part in parts:
        if buffer and _TEXT_ABBREV_RE.search(buffer.rstrip()):
            buffer = (buffer + " " + part).strip()
            continue
        if buffer:
            blocks.append(
                Block(
                    raw_text=buffer,
                    text=buffer,
                    speaker_id=None,
                    meta={"source": "sentence_split_fallback"},
                )
            )
        buffer = part.strip()

    if buffer:
        blocks.append(
            Block(
                raw_text=buffer,
                text=buffer,
                speaker_id=None,
                meta={"source": "sentence_split_fallback"},
            )
        )

    return blocks or [
        Block(
            raw_text=stripped,
            text=stripped,
            speaker_id=None,
            meta={"source": "sentence_split_fallback"},
        )
    ]
