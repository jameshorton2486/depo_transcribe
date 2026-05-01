"""Shared data structures for deterministic transcript enforcement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TranscriptBlock:
    speaker: str
    text: str
    type: str
    source_type: str = ""
    examiner: str | None = None

