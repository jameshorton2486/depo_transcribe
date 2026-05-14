"""Normalize spoken-form years and dates to traditional figure forms.

Court-reporting tradition (Morson's English Guide Rule 179) writes
complete dates with figures for the day and year. Deepgram
transcribes verbatim, so spoken forms like "May seventh, nineteen
sixty-eight" appear in the block stream and must be normalized
before final emission.

Scope (Defect #4):

  * Standalone years: "nineteen sixty-eight" -> "1968",
    "two thousand twenty-four" -> "2024", and context-aware
    "twenty twenty-four" -> "2024".
  * Complete dates (Rule 179): "May seventh, nineteen sixty-eight"
    -> "May 7, 1968", "May seventh" -> "May 7".
  * "Day of Month" form (Rule 180): "the seventh of May, nineteen
    sixty-eight" -> "the 7th of May, 1968" - ordinal preserved
    when day precedes month.
  * Stripping ordinal suffix in standard date order: "May 7th,
    1968" -> "May 7, 1968".
  * Month casing normalization when converting: "may seventh
    nineteen sixty-eight" -> "May 7, 1968".

Out of scope (deferred to future defects):

  * Ages, money, percent, times, fractions, decimals, dimensions,
    medical measurements, centuries, decades, ordinals outside
    date contexts, sentence-start spell-out rule, numbers 1-10
    base rule, and any other Morson's number rule not listed
    above.

The pass is idempotent: running on already-normalized text
produces the same output. The pass operates on
TranscriptBlock.text only - it does not split, merge, reorder,
or re-type blocks.

A note on verbatim integrity. Morson's "Time Out for a Date With
Numbers" essay flags the digit-vs-spelled-out choice as a
working-reporter discretion, not an objective rule. This project
has chosen the traditional digit format for dates and years.
Filler words, repetitions, and self-corrections remain
unaltered - that is the verbatim rule. Format conversion of
dates is a separate stylistic choice consistent with Morson's
Rule 179.
"""

from __future__ import annotations

import re

from .models import TranscriptBlock


_CARDINAL_UNITS: dict[str, int] = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

_CARDINAL_TENS: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_ORDINAL_DAYS: dict[str, int] = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "twenty-first": 21,
    "twenty first": 21,
    "twenty-second": 22,
    "twenty second": 22,
    "twenty-third": 23,
    "twenty third": 23,
    "twenty-fourth": 24,
    "twenty fourth": 24,
    "twenty-fifth": 25,
    "twenty fifth": 25,
    "twenty-sixth": 26,
    "twenty sixth": 26,
    "twenty-seventh": 27,
    "twenty seventh": 27,
    "twenty-eighth": 28,
    "twenty eighth": 28,
    "twenty-ninth": 29,
    "twenty ninth": 29,
    "thirtieth": 30,
    "thirty-first": 31,
    "thirty first": 31,
}

_MONTHS: tuple[str, ...] = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_MONTHS_LOWER: frozenset[str] = frozenset(m.lower() for m in _MONTHS)
_MONTHS_CANONICAL: dict[str, str] = {m.lower(): m for m in _MONTHS}

_DATE_PREPOSITIONS: frozenset[str] = frozenset(
    {
        "in",
        "on",
        "during",
        "since",
        "until",
        "by",
        "before",
        "after",
        "from",
        "to",
        "of",
        "circa",
        "around",
        "about",
    }
)

_MIN_DAY = 1
_MAX_DAY = 31
_PREP_WINDOW_BEFORE_TOKENS = 3
_MONTH_WINDOW_TOKENS = 5


def _parse_cardinal_0_99(words: list[str]) -> int | None:
    """Parse 1-2 spoken cardinal tokens into 0..99, or None."""
    if not words:
        return None
    if len(words) == 1:
        token = words[0]
        if token in _CARDINAL_UNITS:
            return _CARDINAL_UNITS[token]
        if token in _CARDINAL_TENS:
            return _CARDINAL_TENS[token]
        if "-" in token:
            left, _, right = token.partition("-")
            if left in _CARDINAL_TENS and right in _CARDINAL_UNITS:
                unit = _CARDINAL_UNITS[right]
                if 1 <= unit <= 9:
                    return _CARDINAL_TENS[left] + unit
        return None
    if len(words) == 2:
        left, right = words
        if left in _CARDINAL_TENS and right in _CARDINAL_UNITS:
            unit = _CARDINAL_UNITS[right]
            if 1 <= unit <= 9:
                return _CARDINAL_TENS[left] + unit
        if left == "oh" and right in _CARDINAL_UNITS and 1 <= _CARDINAL_UNITS[right] <= 9:
            return _CARDINAL_UNITS[right]
        return None
    return None


def _parse_ordinal_day(text: str) -> int | None:
    return _ORDINAL_DAYS.get(text.strip().lower())


def _parse_cardinal_day(text: str) -> int | None:
    words = re.split(r"\s+", text.strip().lower())
    value = _parse_cardinal_0_99(words)
    if value is None:
        return None
    if _MIN_DAY <= value <= _MAX_DAY:
        return value
    return None


def _parse_day_form(text: str) -> tuple[int, bool] | None:
    ordinal = _parse_ordinal_day(text)
    if ordinal is not None:
        return ordinal, True
    cardinal = _parse_cardinal_day(text)
    if cardinal is not None:
        return cardinal, False
    return None


def _parse_year_form(text: str) -> int | None:
    stripped = text.strip().lower()
    if not stripped:
        return None
    if re.fullmatch(r"\d{4}", stripped):
        year = int(stripped)
        if 1000 <= year <= 2999:
            return year
        return None

    tokens = [t for t in re.split(r"[\s-]+", stripped) if t]
    if not tokens:
        return None

    if len(tokens) >= 3 and tokens[0] == "nineteen" and tokens[1] == "hundred":
        remainder = [t for t in tokens[2:] if t != "and"]
        nn = _parse_cardinal_0_99(remainder)
        if nn is not None:
            return 1900 + nn
        return None

    if tokens[0] == "nineteen" and len(tokens) >= 2:
        nn = _parse_cardinal_0_99(tokens[1:])
        if nn is not None:
            return 1900 + nn
        return None

    if len(tokens) >= 2 and tokens[0] == "two" and tokens[1] == "thousand":
        remainder = [t for t in tokens[2:] if t != "and"]
        if not remainder:
            return 2000
        nn = _parse_cardinal_0_99(remainder)
        if nn is not None:
            return 2000 + nn
        return None

    if tokens[0] == "twenty" and len(tokens) >= 2:
        nn = _parse_cardinal_0_99(tokens[1:])
        if nn is not None and 0 <= nn <= 99:
            return 2000 + nn
        return None

    return None


_DAY_ORDINAL_ALTS = "|".join(
    re.escape(key) for key in sorted(_ORDINAL_DAYS.keys(), key=len, reverse=True)
)
_DAY_CARDINAL_ALTS = (
    r"thirty(?:[-\s]one)?|"
    r"twenty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"nineteen|eighteen|seventeen|sixteen|fifteen|fourteen|thirteen|"
    r"twelve|eleven|ten|"
    r"nine|eight|seven|six|five|four|three|two|one"
)

_DAY_DIGIT = r"(?P<day_digit>\d{1,2})(?P<day_suffix>st|nd|rd|th)?"
_DAY_SPOKEN = rf"(?P<day_ordinal>{_DAY_ORDINAL_ALTS})|(?P<day_cardinal>{_DAY_CARDINAL_ALTS})"

_YEAR_DIGIT = r"\d{4}"
_YEAR_CARDINAL_ALTS = (
    r"ninety(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"eighty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"seventy(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"sixty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"fifty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"forty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"thirty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"twenty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"nineteen|eighteen|seventeen|sixteen|fifteen|fourteen|thirteen|"
    r"twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one"
)
_YEAR_SPOKEN = (
    r"nineteen(?:[\s-]+hundred(?:[\s-]+and)?)?(?:[\s-]+(?:"
    + _YEAR_CARDINAL_ALTS
    + r"))"
    r"|two[\s-]+thousand(?:[\s-]+and)?(?:[\s-]+(?:"
    + _YEAR_CARDINAL_ALTS
    + r"))?"
    r"|twenty[\s-]+(?:"
    r"oh[\s-]+(?:one|two|three|four|five|six|seven|eight|nine)|"
    + _YEAR_CARDINAL_ALTS
    + r")"
)
_YEAR_ANY = rf"(?P<year>{_YEAR_SPOKEN}|{_YEAR_DIGIT})"

_MONTH_NAMES_ALT = "|".join(_MONTHS)

_STANDARD_DATE_RE = re.compile(
    rf"\b(?P<month>{_MONTH_NAMES_ALT})\s+"
    rf"(?:{_DAY_SPOKEN}|{_DAY_DIGIT})"
    rf"(?:\s*,?\s*{_YEAR_ANY})?\b",
    re.IGNORECASE,
)

_DAY_OF_MONTH_RE = re.compile(
    r"\bthe\s+"
    rf"(?:(?P<day_ord>{_DAY_ORDINAL_ALTS})|"
    rf"(?P<day_card>{_DAY_CARDINAL_ALTS})|"
    r"(?P<day_dig>\d{1,2})(?P<day_dig_suffix>st|nd|rd|th)?)"
    rf"\s+of\s+(?P<month>{_MONTH_NAMES_ALT})"
    rf"(?:\s*,?\s*{_YEAR_ANY})?\b",
    re.IGNORECASE,
)

_STANDALONE_YEAR_RE = re.compile(
    rf"\b(?P<year>{_YEAR_SPOKEN})\b",
    re.IGNORECASE,
)

_TOKEN_SPLIT_RE = re.compile(r"\s+")


def _has_year_context(text: str, span_start: int, span_end: int) -> bool:
    before_text = text[:span_start]
    after_text = text[span_end:]
    before_tokens = [t for t in _TOKEN_SPLIT_RE.split(before_text) if t]
    after_tokens = [t for t in _TOKEN_SPLIT_RE.split(after_text) if t]

    for raw in before_tokens[-_PREP_WINDOW_BEFORE_TOKENS:]:
        token = raw.strip(".,;:!?\"'()[]").lower()
        if token in _DATE_PREPOSITIONS:
            return True

    for raw in before_tokens[-_MONTH_WINDOW_TOKENS:] + after_tokens[:_MONTH_WINDOW_TOKENS]:
        token = raw.strip(".,;:!?\"'()[]").lower()
        if token in _MONTHS_LOWER:
            return True

    return False


def _is_ambiguous_twenty_year(year_text: str) -> bool:
    stripped = year_text.strip().lower()
    return stripped.startswith("twenty") and not stripped.startswith("twenty hundred")


def _normalize_standalone_year_at(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    year_text = match.group("year")
    if _is_ambiguous_twenty_year(year_text) and not _has_year_context(text, match.start(), match.end()):
        return None
    year_value = _parse_year_form(year_text)
    if year_value is None:
        return None
    replacement = str(year_value)
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _normalize_standard_date_at(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    month = _MONTHS_CANONICAL[match.group("month").lower()]

    day_value: int | None = None
    if match.group("day_ordinal"):
        day_value = _parse_ordinal_day(match.group("day_ordinal"))
    elif match.group("day_cardinal"):
        day_value = _parse_cardinal_day(match.group("day_cardinal"))
    elif match.group("day_digit"):
        day_value = int(match.group("day_digit"))

    if day_value is None or not (_MIN_DAY <= day_value <= _MAX_DAY):
        return None

    year_value: int | None = None
    if match.group("year"):
        year_value = _parse_year_form(match.group("year"))
        if year_value is None:
            return None

    replacement = f"{month} {day_value}"
    if year_value is not None:
        replacement += f", {year_value}"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _ordinal_suffix(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return "th"
    last = day % 10
    if last == 1:
        return "st"
    if last == 2:
        return "nd"
    if last == 3:
        return "rd"
    return "th"


def _normalize_day_of_month_at(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    month = _MONTHS_CANONICAL[match.group("month").lower()]

    day_value: int | None = None
    if match.group("day_ord"):
        day_value = _parse_ordinal_day(match.group("day_ord"))
    elif match.group("day_card"):
        day_value = _parse_cardinal_day(match.group("day_card"))
    elif match.group("day_dig"):
        day_value = int(match.group("day_dig"))

    if day_value is None or not (_MIN_DAY <= day_value <= _MAX_DAY):
        return None

    year_value: int | None = None
    if match.group("year"):
        year_value = _parse_year_form(match.group("year"))
        if year_value is None:
            return None

    replacement = f"the {day_value}{_ordinal_suffix(day_value)} of {month}"
    if year_value is not None:
        replacement += f", {year_value}"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _normalize_text(text: str) -> str:
    if not text:
        return text

    out = text
    pos = 0
    while True:
        match = _DAY_OF_MONTH_RE.search(out, pos)
        if match is None:
            break
        normalized = _normalize_day_of_month_at(out, match)
        if normalized is None:
            pos = match.end()
            continue
        out, pos = normalized

    pos = 0
    while True:
        match = _STANDARD_DATE_RE.search(out, pos)
        if match is None:
            break
        normalized = _normalize_standard_date_at(out, match)
        if normalized is None:
            pos = match.end()
            continue
        out, pos = normalized

    pos = 0
    while True:
        match = _STANDALONE_YEAR_RE.search(out, pos)
        if match is None:
            break
        normalized = _normalize_standalone_year_at(out, match)
        if normalized is None:
            pos = match.end()
            continue
        out, pos = normalized

    return out


def normalize_dates_and_years(
    blocks: list[TranscriptBlock],
) -> list[TranscriptBlock]:
    """Apply date and year normalization to every block in the list."""
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
