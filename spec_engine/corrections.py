"""Text normalization only for deterministic transcript enforcement."""

from __future__ import annotations

from .models import TranscriptBlock


def normalize_text_blocks(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    """Trim block text without changing words, speaker identity, or structure."""
    normalized: list[TranscriptBlock] = []
    for block in blocks:
        normalized.append(
            TranscriptBlock(
                speaker=str(block.speaker or "").strip(),
                text=str(block.text or "").strip(),
                type=block.type,
                source_type=block.source_type,
                examiner=block.examiner,
            )
        )
    return normalized

