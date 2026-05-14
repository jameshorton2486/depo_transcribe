"""Split misattributed objections from merged question/colloquy blocks.

When Deepgram bundles a question and a subsequent objection into
a single utterance under one speaker (the examining attorney),
the result is a block whose text contains an embedded
"Objection." mid-stream. The examining attorney does not object
to their own questions; this is two speakers' speech merged into
one block.

This pass detects the pattern and splits the block in two:

  1. The original block, truncated to the text BEFORE the
     objection sentence boundary. Speaker, type, examiner, and
     other fields are preserved unchanged.
  2. A new ``colloquy`` block holding the objection text from
     the sentence boundary onward. Its ``speaker`` is the
     sentinel ``(SPEAKER UNVERIFIED)`` so the rendered output
     conspicuously flags the attribution for manual review.

This pass deliberately does NOT try to identify the correct
objecting attorney. A participant identity layer for that does
not yet exist. The sentinel speaker makes the uncertainty
visible rather than confidently wrong; Miah's scopist review
fills in the correct name.

Trigger conditions (ALL must hold for a split to fire):

  1. Block type is ``question`` or ``colloquy``.
  2. Case-insensitive regex ``\\bobjection\\b[\\.\\,:]?`` matches
     in the block text at a position AT OR AFTER character
     ``_MIN_OBJECTION_OFFSET`` (10) from the block start. A
     match earlier than this means the block likely IS the
     objection itself, not a merged one.
  3. At least ``_MIN_PRECEDING_TEXT`` (20) characters of
     non-whitespace text precede the match start. This filters
     out blocks where the speaker says one word and then
     objects - likely a real attorney's quick objection in
     their own (correctly attributed) block.
  4. First match only. No recursive splitting; if the colloquy
     half itself contains a second objection it stays intact.
  5. Split point is the start of the sentence containing the
     match. Found by looking backward for ``.``, ``?``, or
     ``!`` followed by whitespace; if none is found, split is
     suppressed (would produce an empty pre-text).

A note on the regex and what it does (and does not) filter:

The regex ``\\bobjection\\b[\\.\\,:]?`` requires "objection" as a
whole word, optionally followed by ``.``, ``,``, or ``:``. This
alone does NOT filter out phrases like "no objection",
"subject to objection", or "without objection" — those still
contain "objection" as a whole word.

Two filtering layers handle those phrases:

  1. The 10-char offset threshold catches phrases at the very
     start of a block (e.g. "Without objection, the exhibit is
     admitted." — "objection" at position 8, below the
     threshold).
  2. The phrase-window exclusion (``_EXCLUDED_OBJECTION_PHRASES``)
     catches mid-block uses by checking a ±_PHRASE_WINDOW-character
     window around the match for known colloquy phrases. When
     a phrase is found in the window, the split is suppressed.

Trade-off accepted: a genuinely merged block whose first match
sits within the phrase window of one of these strings will also
be suppressed. Rare in practice; the alternative (firing on
normal colloquy) produces output that reads as a system bug.

The 10 and 20 thresholds are conservative first-pass values. If
review feedback shows false positives or missed splits, tune
from real evidence rather than speculation.
"""

from __future__ import annotations

import re

from .models import TranscriptBlock


# Only attorney-speech conversational blocks are eligible.
# Answer, directive, and oath blocks are never split - the
# pattern we're correcting only arises in attorney-speech blocks
# that Deepgram mis-merged.
_SPLIT_TARGET_TYPES = frozenset({"question", "colloquy"})

# Minimum offset (in characters) from the start of block text at
# which an "objection" match is allowed to fire. A match at or
# very near the start means the block IS the objection, not a
# merged one.
_MIN_OBJECTION_OFFSET = 10

# Minimum length of non-whitespace text preceding the match.
# Prevents splitting blocks where the speaker says a single word
# and then objects in their own correctly-attributed block.
_MIN_PRECEDING_TEXT = 20

# Sentinel speaker label for the split-off objection block.
# Conspicuous by design; Miah replaces with the correct opposing
# counsel name during manual review.
SENTINEL_SPEAKER = "(SPEAKER UNVERIFIED)"

# Objection-start detector. "objection" as a whole word,
# optionally followed by . , or :. Case-insensitive.
_OBJECTION_RE = re.compile(r"\bobjection\b[\.\,:]?", re.IGNORECASE)
_EXCLUDED_OBJECTION_PHRASES = (
    "no objection",
    "without objection",
    "subject to objection",
)

# Half-width of the lookaround window around the match position
# (in characters). 25 is enough to catch "subject to objection"
# (11 chars before the match) with margin, while staying narrow
# enough that distant uses elsewhere in the block don't
# accidentally suppress a real merge.
_PHRASE_WINDOW = 25

# Sentence boundary: ., ?, or ! followed by one or more
# whitespace characters.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.?!]\s+")


def _find_sentence_start(text: str, position: int) -> int | None:
    """Return the start index of the sentence containing ``position``.

    Looks backward from ``position`` for the most recent sentence
    boundary (``.``, ``?``, or ``!`` followed by whitespace) and
    returns the character index AFTER that whitespace.

    Returns ``None`` when no boundary is found. This signals the
    caller to suppress the split rather than splitting at the
    block start (which would produce an empty pre-text and lose
    the original block).
    """
    if position <= 0:
        return None
    search_region = text[:position]
    last_match = None
    for match in _SENTENCE_BOUNDARY_RE.finditer(search_region):
        last_match = match
    if last_match is None:
        return None
    return last_match.end()


def _split_block(block: TranscriptBlock) -> list[TranscriptBlock] | None:
    """Return ``[original_truncated, sentinel_colloquy]`` if the
    block should split, else ``None``.

    Returns ``None`` for any reason the trigger conditions are
    not met (no match, match too early, insufficient preceding
    text, no sentence boundary found, empty pre or post text).
    """
    text = block.text or ""

    match = _OBJECTION_RE.search(text)
    if match is None:
        return None

    match_start = match.start()

    if match_start < _MIN_OBJECTION_OFFSET:
        return None

    # Phrase-based exclusion. If "objection" here is part of a
    # normal colloquy phrase ("no objection", "without objection",
    # "subject to objection"), this is not a merged-objection
    # defect - it is the block's speaker discussing the concept
    # of objection. Suppress the split.
    #
    # Trade-off: a genuinely merged block whose first match
    # happens to sit within _PHRASE_WINDOW chars of one of these
    # phrases will also be suppressed. Rare in practice; pinned
    # by test_merged_block_with_nearby_colloquy_phrase_suppressed.
    lowered = text.lower()
    window = lowered[
        max(0, match_start - _PHRASE_WINDOW) : match_start + _PHRASE_WINDOW
    ]
    for phrase in _EXCLUDED_OBJECTION_PHRASES:
        if phrase in window:
            return None

    sentence_start = _find_sentence_start(text, match_start)
    if sentence_start is None:
        return None

    preceding_stripped = text[:match_start].strip()
    pre_text = text[:sentence_start].rstrip()
    post_text = text[sentence_start:].lstrip()

    # Short but complete question sentences are still valid split
    # targets. The generic 20-char floor remains for everything
    # else so quick in-block objections do not get over-split.
    if len(preceding_stripped) < _MIN_PRECEDING_TEXT and not pre_text.endswith(("?", "!")):
        return None

    if not pre_text or not post_text:
        return None

    original_truncated = TranscriptBlock(
        speaker=block.speaker,
        text=pre_text,
        type=block.type,
        source_type=block.source_type,
        examiner=block.examiner,
        words=block.words,
    )
    sentinel_colloquy = TranscriptBlock(
        speaker=SENTINEL_SPEAKER,
        text=post_text,
        type="colloquy",
        source_type=block.source_type,
        examiner=None,
        words=None,
    )
    return [original_truncated, sentinel_colloquy]


def split_misattributed_objections(
    blocks: list[TranscriptBlock],
) -> list[TranscriptBlock]:
    """Split question/colloquy blocks that contain an embedded
    objection mid-stream.

    See module docstring for trigger conditions and design
    rationale. First match only - no recursive splitting.
    """
    if not blocks:
        return []

    result: list[TranscriptBlock] = []
    for block in blocks:
        if block.type in _SPLIT_TARGET_TYPES:
            split = _split_block(block)
            if split is not None:
                result.extend(split)
                continue
        result.append(block)
    return result
