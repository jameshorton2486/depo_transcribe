"""Exhibit-marker emission pass.

Detects examiner statements that introduce an exhibit and emits a
UFM Section 3.16(a) compliant directive block "(Exhibit N marked)"
immediately after the introducing block. Introducing blocks pass
through unchanged.

Runs after speaker normalization, before the emitter. The
companion fix in speaker_mapper.normalize_directive_text ensures
the emitted directive text is not rewritten as a BY-line.
"""

from __future__ import annotations

import re

from .models import TranscriptBlock


# Detection pattern. Matches either:
# - a marking/introducing verb followed by an article and
#   "Exhibit N", or
# - a self-correction form like "this one is exhibit 8".
# Pure references like "looking at Exhibit 1" do not trigger.
EXHIBIT_INTRO_PATTERN = re.compile(
    r"(?:"
    r"(?:mark(?:ing|ed)?|introduc(?:e|ing|ed))"
    r"\s+(?:this|that|the|it|to\s+you)\s+"
    r"(?:as\s+)?"
    r"|(?:this|that)\s+one\s+is\s+"
    r")"
    r"(?:plaintiff'?s|defendant'?s|defense)?\s*"
    r"exhibit\s+"
    r"(?P<num>\d+|[A-Za-z](?=[\s.,;?!]|$))",
    re.IGNORECASE,
)

# Already-emitted marker recognizer for idempotence.
_EXISTING_MARKER_PATTERN = re.compile(
    r"^\s*\(Exhibit\s+\w+\s+marked\)\s*$"
)


def _canonical_number(raw: str) -> str:
    """Render captured exhibit identifier in canonical form.

    Digit identifiers pass through as-is. Letter identifiers are
    uppercased so "a" -> "A".
    """
    return raw.upper() if raw.isalpha() else raw


def _find_last_introduced_exhibit(text: str) -> str | None:
    """Return the canonical exhibit identifier from the LAST
    introducing match in the text, or None if no match.

    Multiple matches in one block are common when an examiner
    self-corrects mid-statement (e.g. "introduce Exhibit 8...
    actually, this one is exhibit A. Sorry, this one is exhibit
    8."). The last match is what the examiner actually settled on.
    """
    matches = list(EXHIBIT_INTRO_PATTERN.finditer(text or ""))
    if not matches:
        return None
    return _canonical_number(matches[-1].group("num"))


def _is_existing_marker(block: TranscriptBlock | None) -> bool:
    if block is None or block.type != "directive":
        return False
    return bool(_EXISTING_MARKER_PATTERN.match(block.text or ""))


def emit_exhibit_markers(
    blocks: list[TranscriptBlock],
) -> list[TranscriptBlock]:
    """Insert (Exhibit N marked) directive blocks after blocks
    that introduce an exhibit.

    Idempotent. Running the pass twice produces the same output as
    running it once: if the block immediately after a trigger is
    already an exhibit-marker directive, no new marker is emitted.
    """
    if not blocks:
        return []

    result: list[TranscriptBlock] = []
    for index, block in enumerate(blocks):
        result.append(block)

        identifier = _find_last_introduced_exhibit(block.text or "")
        if identifier is None:
            continue

        # Idempotence: skip if the next block in the input is
        # already this marker.
        next_block = blocks[index + 1] if index + 1 < len(blocks) else None
        if _is_existing_marker(next_block):
            continue

        result.append(
            TranscriptBlock(
                speaker="",
                text=f"(Exhibit {identifier} marked)",
                type="directive",
            )
        )

    return result
