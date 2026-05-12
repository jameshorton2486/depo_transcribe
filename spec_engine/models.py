"""Shared data structures for deterministic transcript enforcement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TranscriptWord:
    """Single Deepgram word with timing, confidence, and speaker metadata.

    Added in Step B.0 of the verbatim-punctuation plan
    (docs/plans/verbatim_punctuation_plan_2026-05-12.md) to enable
    low-confidence highlighting (Steps C and D) and future audio-sync
    review.

    Field shapes follow the documented Deepgram Nova-3 word object.
    `punctuated_word` is populated by Deepgram when smart_format=True.
    `speaker` carries the post-speaker_mapper label after Step B.1; in
    B.0, it carries Deepgram's raw speaker index unchanged.
    """

    text: str
    start: float
    end: float
    confidence: float
    speaker: str | int | None = None
    punctuated_word: str | None = None


@dataclass(slots=True)
class TranscriptBlock:
    speaker: str
    text: str
    type: str
    source_type: str = ""
    examiner: str | None = None
    # Step B.0: optional word-level metadata. Default None means "no
    # carried words" — either the source lacked the data, or a future
    # qa_fixer step (B.1) couldn't align words to the post-cleanup
    # text. Existing callers using the 5-arg constructor remain valid.
    words: list[TranscriptWord] | None = None
