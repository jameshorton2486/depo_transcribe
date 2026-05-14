"""Collapse strict recess / off-the-record directive pairs.

Detects pairs of directive blocks like:

  (Recess taken.)
  ...
  (Back on the record.)

and collapses them into a single annotated directive:

  (Recess from 10:14 a.m. to 10:32 a.m.)

Matches Miah's professional output style as observed in the
Shaw deposition transcript (191216Shaw__5_.pdf, Texas, 2019).

Scope is intentionally narrow. The pass implements strict
exact-phrase matching on three opening forms and one closing
form. No fuzzy matching, no inference of variants, no semantic
normalization. Orphan openings, malformed pairs, and nested
pairs are left untouched -- visible uncertainty is safer than
inferred certainty.

Timestamp sourcing has a strict hierarchy:

  1. Directive block's own `words` field.
  2. Nearest immediately-adjacent block's first/last word time.
  3. Fall through -- pair is left unmerged.

No timeline reconstruction beyond the immediate neighbor.

Pairing is bounded by a maximum distance of 40 blocks between
opening and closing. Beyond that, the opening is considered
orphaned and left alone.

Idempotent.
"""

from __future__ import annotations

import re
from typing import Any

from .models import TranscriptBlock


_OPENING_TRIGGERS: dict[str, str] = {
    "(Recess taken.)": "Recess",
    "(Off the record.)": "Discussion off the record",
    "(Discussion held off the record.)": "Discussion off the record",
}

_CLOSING_TRIGGER: str = "(Back on the record.)"
_MAX_PAIRING_DISTANCE: int = 40

_DEPOSITION_START_RE = re.compile(
    r"^\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<marker>a\.m\.|p\.m\.)\s*$",
    re.IGNORECASE,
)


def _parse_deposition_start_seconds(start_time: str) -> int | None:
    """Parse a deposition start time like '8:00 a.m.' into seconds."""
    if not start_time:
        return None
    match = _DEPOSITION_START_RE.match(start_time)
    if match is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    marker = match.group("marker").lower()
    if not (1 <= hour <= 12) or not (0 <= minute <= 59):
        return None
    if marker == "a.m.":
        hour24 = 0 if hour == 12 else hour
    else:
        hour24 = 12 if hour == 12 else hour + 12
    return hour24 * 3600 + minute * 60


def _format_clock_time(seconds_since_midnight: int) -> str | None:
    """Format seconds-since-midnight into 'H:MM a.m.' / 'H:MM p.m.'."""
    if seconds_since_midnight < 0 or seconds_since_midnight >= 24 * 3600:
        return None
    total_minutes = seconds_since_midnight // 60
    hour24 = total_minutes // 60
    minute = total_minutes % 60
    if hour24 == 0:
        hour12 = 12
        marker = "a.m."
    elif hour24 < 12:
        hour12 = hour24
        marker = "a.m."
    elif hour24 == 12:
        hour12 = 12
        marker = "p.m."
    else:
        hour12 = hour24 - 12
        marker = "p.m."
    return f"{hour12}:{minute:02d} {marker}"


def _block_first_word_start(block: TranscriptBlock) -> float | None:
    """Return the start time of the first word in a block, or None."""
    words = getattr(block, "words", None)
    if not words:
        return None
    first = words[0]
    if isinstance(first, dict):
        start = first.get("start")
    else:
        start = getattr(first, "start", None)
    if not isinstance(start, (int, float)):
        return None
    return float(start)


def _block_last_word_end(block: TranscriptBlock) -> float | None:
    """Return the end time of the last word in a block, or None."""
    words = getattr(block, "words", None)
    if not words:
        return None
    last = words[-1]
    if isinstance(last, dict):
        end = last.get("end")
        if end is None:
            end = last.get("start")
    else:
        end = getattr(last, "end", None)
        if end is None:
            end = getattr(last, "start", None)
    if not isinstance(end, (int, float)):
        return None
    return float(end)


def _resolve_open_seconds(
    blocks: list[TranscriptBlock],
    open_index: int,
) -> float | None:
    """Resolve the start time offset for the opening directive."""
    direct = _block_first_word_start(blocks[open_index])
    if direct is not None:
        return direct
    if open_index > 0:
        neighbor = _block_last_word_end(blocks[open_index - 1])
        if neighbor is not None:
            return neighbor
    return None


def _resolve_close_seconds(
    blocks: list[TranscriptBlock],
    close_index: int,
) -> float | None:
    """Resolve the end time offset for the closing directive."""
    direct = _block_first_word_start(blocks[close_index])
    if direct is not None:
        return direct
    if close_index + 1 < len(blocks):
        neighbor = _block_first_word_start(blocks[close_index + 1])
        if neighbor is not None:
            return neighbor
    return None


def pair_recess_directives(
    blocks: list[TranscriptBlock],
    case_meta: dict[str, Any] | None = None,
) -> list[TranscriptBlock]:
    """Collapse strict recess / off-record directive pairs."""
    if not blocks:
        return []

    case_meta = case_meta or {}
    deposition_start = case_meta.get("deposition_start_time", "")
    deposition_start_seconds = _parse_deposition_start_seconds(deposition_start)

    result: list[TranscriptBlock] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]

        if block.type != "directive":
            result.append(block)
            i += 1
            continue

        text = (block.text or "").strip()
        if text not in _OPENING_TRIGGERS:
            result.append(block)
            i += 1
            continue

        close_index = None
        scan_limit = min(i + 1 + _MAX_PAIRING_DISTANCE, len(blocks))
        nested = False
        for j in range(i + 1, scan_limit):
            other = blocks[j]
            if other.type != "directive":
                continue
            other_text = (other.text or "").strip()
            if other_text in _OPENING_TRIGGERS:
                nested = True
                break
            if other_text == _CLOSING_TRIGGER:
                close_index = j
                break

        if nested or close_index is None:
            result.append(block)
            i += 1
            continue

        if deposition_start_seconds is None:
            result.append(block)
            i += 1
            continue

        start_offset = _resolve_open_seconds(blocks, i)
        end_offset = _resolve_close_seconds(blocks, close_index)

        if start_offset is None or end_offset is None:
            result.append(block)
            i += 1
            continue

        if end_offset < start_offset:
            result.append(block)
            i += 1
            continue

        start_str = _format_clock_time(
            deposition_start_seconds + int(start_offset)
        )
        end_str = _format_clock_time(
            deposition_start_seconds + int(end_offset)
        )

        if start_str is None or end_str is None:
            result.append(block)
            i += 1
            continue

        noun_phrase = _OPENING_TRIGGERS[text]
        merged_text = f"({noun_phrase} from {start_str} to {end_str})"

        merged_block = TranscriptBlock(
            speaker=block.speaker,
            text=merged_text,
            type="directive",
            source_type=block.source_type,
            examiner=None,
            words=block.words,
        )

        result.append(merged_block)
        for j in range(i + 1, close_index):
            result.append(blocks[j])
        i = close_index + 1

    return result
