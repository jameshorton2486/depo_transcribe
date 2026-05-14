"""Normalize spoken-form money and percent expressions.

Implements Morson's English Guide for Court Reporters Rules
189-195 (money) and Rule 199 (percent). Scope intentionally
limited to these rules; ages, times, fractions, decimals, and
other Morson's number rules remain deferred.

Conversions:

  * Rule 189 - "twenty dollars" -> "$20".
  * Rule 191 - "thirty cents" -> "30 cents".
  * Rule 193 - "twenty dollars and fifty cents" -> "$20.50".
  * Rule 194 - "two million dollars" -> "$2 million".
  * Rule 195 - "a million dollars" -> unchanged (indefinite).
  * Rule 199 - "fifty percent" -> "50 percent".

The pass is idempotent. It operates on TranscriptBlock.text
only; block structure, types, and other fields are preserved.

Cardinal-word parsing is delegated to
``date_normalization._parse_cardinal_0_99`` to avoid vocabulary
duplication. For amounts above 99 (hundreds, thousands,
millions, billions), additional parsing is implemented here
because date_normalization only handles 0-99.

Idiomatic ``cents on the dollar`` is suppressed by checking
whether the matched cents expression is immediately followed by
the phrase ``on the dollar`` within 3 tokens. The suppression
is exact-phrase; variants like ``cents on each dollar`` are not
caught and will still convert. Pinned by test.
"""

from __future__ import annotations

import re

from .date_normalization import _parse_cardinal_0_99
from .models import TranscriptBlock


# ----------------------------------------------------------------
# Cardinal vocabulary for amounts > 99
# ----------------------------------------------------------------

_SCALE_HUNDRED = "hundred"
_SCALE_THOUSAND = "thousand"
_SCALE_MILLION = "million"
_SCALE_BILLION = "billion"

_INDEFINITE_QUANTIFIERS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "several",
        "many",
        "few",
        "some",
        "various",
        "numerous",
        "multiple",
    }
)

_CENTS_IDIOM_SUFFIX = "on the dollar"


# ----------------------------------------------------------------
# Spoken-amount parsing
# ----------------------------------------------------------------

_CARDINAL_WORD_TOKEN = (
    r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|"
    r"twenty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"thirty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"forty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"fifty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"sixty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"seventy(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"eighty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"ninety(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?)"
)

_CARDINAL_AMOUNT = (
    rf"(?:{_CARDINAL_WORD_TOKEN}[\s-]+{_SCALE_THOUSAND}"
    rf"(?:[\s-]+(?:and[\s-]+)?(?:{_CARDINAL_WORD_TOKEN}[\s-]+{_SCALE_HUNDRED}"
    rf"(?:[\s-]+(?:and[\s-]+)?{_CARDINAL_WORD_TOKEN})?|{_CARDINAL_WORD_TOKEN}))?"
    rf"|{_CARDINAL_WORD_TOKEN}[\s-]+{_SCALE_HUNDRED}"
    rf"(?:[\s-]+(?:and[\s-]+)?{_CARDINAL_WORD_TOKEN})?"
    rf"|{_CARDINAL_WORD_TOKEN})"
)


def _parse_spoken_amount(text: str) -> int | None:
    """Parse a spoken cardinal amount (0..999,999) into an int."""
    stripped = text.strip().lower()
    if not stripped:
        return None

    if re.fullmatch(r"\d+(?:,\d{3})*", stripped):
        return int(stripped.replace(",", ""))

    tokens = [t for t in re.split(r"[\s-]+", stripped) if t and t != "and"]
    if not tokens:
        return None

    direct = _parse_cardinal_0_99(tokens)
    if direct is not None:
        return direct

    if _SCALE_THOUSAND in tokens:
        idx = tokens.index(_SCALE_THOUSAND)
        thousands_part = _parse_thousands_prefix(tokens[:idx])
        if thousands_part is None:
            return None
        rest = tokens[idx + 1 :]
        if not rest:
            return thousands_part * 1000
        rest_value = _parse_hundreds_or_less(rest)
        if rest_value is None:
            return None
        return thousands_part * 1000 + rest_value

    if _SCALE_HUNDRED in tokens:
        return _parse_hundreds_or_less(tokens)

    return None


def _parse_thousands_prefix(tokens: list[str]) -> int | None:
    """Parse the cardinal multiplier preceding 'thousand'."""
    if not tokens:
        return None
    if _SCALE_HUNDRED in tokens:
        return _parse_hundreds_or_less(tokens)
    return _parse_cardinal_0_99(tokens)


def _parse_hundreds_or_less(tokens: list[str]) -> int | None:
    """Parse tokens representing a value 0..999."""
    if not tokens:
        return None
    if _SCALE_HUNDRED in tokens:
        idx = tokens.index(_SCALE_HUNDRED)
        hundreds_word = tokens[:idx]
        if not hundreds_word:
            return None
        hundreds_value = _parse_cardinal_0_99(hundreds_word)
        if hundreds_value is None or not (1 <= hundreds_value <= 9):
            return None
        rest = tokens[idx + 1 :]
        if not rest:
            return hundreds_value * 100
        rest_value = _parse_cardinal_0_99(rest)
        if rest_value is None:
            return None
        return hundreds_value * 100 + rest_value
    return _parse_cardinal_0_99(tokens)


# ----------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------

def _format_dollar_amount(value: int) -> str:
    """Return '$<value>' with comma-grouping for thousands."""
    return f"${value:,}"


def _format_cents_two_digits(value: int) -> str:
    """Return zero-padded two-digit cents string ('05' for 5)."""
    return f"{value:02d}"


# ----------------------------------------------------------------
# Regex patterns
# ----------------------------------------------------------------

_DOLLARS_AND_CENTS_RE = re.compile(
    rf"\b(?P<dollars>{_CARDINAL_AMOUNT})[\s-]+dollars"
    rf"[\s-]+and[\s-]+(?P<cents>{_CARDINAL_WORD_TOKEN})[\s-]+cents\b",
    re.IGNORECASE,
)

_SCALE_DOLLARS_RE = re.compile(
    rf"\b(?P<prefix>{_CARDINAL_WORD_TOKEN})"
    rf"[\s-]+(?P<scale>{_SCALE_MILLION}|{_SCALE_BILLION})[\s-]+dollars\b",
    re.IGNORECASE,
)

_INDEFINITE_SCALE_DOLLARS_RE = re.compile(
    rf"\b(?P<quantifier>{'|'.join(sorted(_INDEFINITE_QUANTIFIERS))})"
    rf"[\s-]+(?P<scale>{_SCALE_MILLION}|{_SCALE_BILLION})[\s-]+dollars\b",
    re.IGNORECASE,
)

_DOLLARS_RE = re.compile(
    rf"\b(?P<amount>{_CARDINAL_AMOUNT})[\s-]+dollars\b",
    re.IGNORECASE,
)

_CENTS_RE = re.compile(
    rf"\b(?P<amount>{_CARDINAL_WORD_TOKEN})[\s-]+cents\b",
    re.IGNORECASE,
)

_PERCENT_RE = re.compile(
    rf"\b(?P<amount>{_CARDINAL_AMOUNT})[\s-]+percent\b",
    re.IGNORECASE,
)


# ----------------------------------------------------------------
# Match handlers
# ----------------------------------------------------------------

def _is_followed_by_cents_idiom(text: str, end_pos: int) -> bool:
    """True if the text immediately following end_pos is ``on the dollar``."""
    after = text[end_pos:].lstrip(" ,;:")
    return after.lower().startswith(_CENTS_IDIOM_SUFFIX)


def _handle_dollars_and_cents(
    text: str, match: re.Match[str]
) -> tuple[str, int] | None:
    dollars_value = _parse_spoken_amount(match.group("dollars"))
    cents_value = _parse_cardinal_0_99(
        [
            t
            for t in re.split(r"[\s-]+", match.group("cents").lower())
            if t and t != "and"
        ]
    )
    if dollars_value is None or cents_value is None:
        return None
    if not (0 <= cents_value <= 99):
        return None
    replacement = (
        f"{_format_dollar_amount(dollars_value)}."
        f"{_format_cents_two_digits(cents_value)}"
    )
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_scale_dollars(
    text: str, match: re.Match[str]
) -> tuple[str, int] | None:
    prefix_tokens = [
        t for t in re.split(r"[\s-]+", match.group("prefix").lower()) if t
    ]
    prefix_value = _parse_cardinal_0_99(prefix_tokens)
    if prefix_value is None:
        return None
    scale = match.group("scale").lower()
    replacement = f"${prefix_value} {scale}"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_dollars(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    amount_value = _parse_spoken_amount(match.group("amount"))
    if amount_value is None:
        return None
    replacement = _format_dollar_amount(amount_value)
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_cents(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    if _is_followed_by_cents_idiom(text, match.end()):
        return None
    amount_tokens = [
        t for t in re.split(r"[\s-]+", match.group("amount").lower()) if t
    ]
    amount_value = _parse_cardinal_0_99(amount_tokens)
    if amount_value is None:
        return None
    if not (1 <= amount_value <= 99):
        return None
    replacement = f"{amount_value} cents"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_percent(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    amount_value = _parse_spoken_amount(match.group("amount"))
    if amount_value is None:
        return None
    replacement = f"{amount_value} percent"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


# ----------------------------------------------------------------
# Text-level orchestration
# ----------------------------------------------------------------

def _indefinite_scale_spans(text: str) -> list[tuple[int, int]]:
    """Return spans of indefinite million/billion-dollar constructions."""
    return [
        (match.start(), match.end())
        for match in _INDEFINITE_SCALE_DOLLARS_RE.finditer(text)
    ]


def _position_in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    """True if pos is inside any of the given character spans."""
    return any(start <= pos < end for start, end in spans)


def _normalize_text(text: str) -> str:
    """Apply money and percent normalization to a single text string."""
    if not text:
        return text

    out = text

    pos = 0
    while True:
        match = _DOLLARS_AND_CENTS_RE.search(out, pos)
        if match is None:
            break
        result = _handle_dollars_and_cents(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result

    indefinite_spans = _indefinite_scale_spans(out)
    pos = 0
    while True:
        match = _SCALE_DOLLARS_RE.search(out, pos)
        if match is None:
            break
        if _position_in_spans(match.start(), indefinite_spans):
            pos = match.end()
            continue
        result = _handle_scale_dollars(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result
        indefinite_spans = _indefinite_scale_spans(out)

    indefinite_spans = _indefinite_scale_spans(out)
    pos = 0
    while True:
        match = _DOLLARS_RE.search(out, pos)
        if match is None:
            break
        if _position_in_spans(match.start(), indefinite_spans):
            pos = match.end()
            continue
        result = _handle_dollars(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result
        indefinite_spans = _indefinite_scale_spans(out)

    pos = 0
    while True:
        match = _CENTS_RE.search(out, pos)
        if match is None:
            break
        result = _handle_cents(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result

    pos = 0
    while True:
        match = _PERCENT_RE.search(out, pos)
        if match is None:
            break
        result = _handle_percent(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result

    return out


def normalize_money_and_percent(
    blocks: list[TranscriptBlock],
) -> list[TranscriptBlock]:
    """Apply money and percent normalization to every block."""
    if not blocks:
        return []
    result: list[TranscriptBlock] = []
    for block in blocks:
        new_text = _normalize_text(block.text or "")
        if new_text == block.text:
            result.append(block)
            continue
        result.append(
            TranscriptBlock(
                speaker=block.speaker,
                text=new_text,
                type=block.type,
                source_type=block.source_type,
                examiner=block.examiner,
                words=block.words,
            )
        )
    return result
