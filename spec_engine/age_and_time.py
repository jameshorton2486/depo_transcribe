"""Normalize spoken-form ages and clock times.

Implements Morson's English Guide for Court Reporters Rule 175
(ages), Rules 184-186 (clock time with a.m./p.m.), Rule 185
(noon/midnight), Rule 187 (o'clock - stays spelled), and
Rule 188 (military time).

Conversions:

  * Rule 175 - "fifty-six years old" -> "56 years old".
  * Rule 184/186 - "three p.m." -> "3 p.m.";
    "three thirty p.m." -> "3:30 p.m.".
  * Rule 185 - "twelve noon" -> "12 noon"; bare "noon"
    unchanged.
  * Rule 187 - "three o'clock" stays "three o'clock".
  * Rule 188 - "fifteen hundred hours" -> "1500 hours".

Bare hour+minute forms without an explicit time marker pass
through unchanged. Acknowledged conservative trade-off; see
module-level note on the disambiguation rule.

The pass is idempotent. It operates on TranscriptBlock.text
only; block structure, types, and other fields are preserved.

Cardinal-word parsing for 0..99 is delegated to
``date_normalization._parse_cardinal_0_99``. No vocabulary
duplication.
"""

from __future__ import annotations

import re

from .date_normalization import _parse_cardinal_0_99
from .models import TranscriptBlock


_MIN_AGE = 1
_MAX_AGE = 120

_MIN_HOUR_12 = 1
_MAX_HOUR_12 = 12

_MIN_HOUR_24 = 0
_MAX_HOUR_24 = 23

_MIN_MINUTE = 0
_MAX_MINUTE = 59

_TIME_PREPOSITIONS: frozenset[str] = frozenset(
    {
        "at",
        "around",
        "about",
        "by",
        "before",
        "after",
        "until",
        "since",
    }
)

_TRAILING_TIME_MARKERS: frozenset[str] = frozenset(
    {
        "a.m.",
        "p.m.",
        "am",
        "pm",
        "hours",
    }
)


_CARDINAL_0_99 = (
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
    r"ninety(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"one[\s-]+hundred(?:[\s-]+and[\s-]+(?:"
    r"one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|"
    r"twenty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?))?"
    r")"
)

_HOUR_WORD = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve)"
)

_MILITARY_HOUR = (
    r"(?:oh[-\s](?:zero|one|two|three|four|five|six|seven|eight|nine)|"
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|"
    r"twenty(?:[-\s](?:one|two|three))?))"
)

_MINUTE_WORD = (
    r"(?:oh[-\s](?:zero|one|two|three|four|five|six|seven|eight|nine)|"
    r"zero|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|"
    r"twenty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"thirty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"forty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?|"
    r"fifty(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?)"
)

_AMPM = r"(?:a\.m\.|p\.m\.|a\.\s*m\.|p\.\s*m\.|am|pm)"
_OCLOCK = r"o['']clock"
_NOON = r"noon"
_MIDNIGHT = r"midnight"


_AGE_YEARS_OLD_RE = re.compile(
    rf"\b(?P<age>{_CARDINAL_0_99})[\s-]+years?[\s-]+old\b",
    re.IGNORECASE,
)

_AGE_YEARS_OF_AGE_RE = re.compile(
    rf"\b(?P<age>{_CARDINAL_0_99})[\s-]+years?[\s-]+of[\s-]+age\b",
    re.IGNORECASE,
)

_AGE_PREFIX_RE = re.compile(
    rf"\bage[\s-]+(?P<age>{_CARDINAL_0_99})\b",
    re.IGNORECASE,
)

_HOUR_AMPM_RE = re.compile(
    rf"\b(?P<hour>{_HOUR_WORD})[\s-]*(?P<ampm>{_AMPM})",
    re.IGNORECASE,
)

_HOUR_MINUTE_AMPM_RE = re.compile(
    rf"\b(?P<hour>{_HOUR_WORD})[\s-]+(?P<minute>{_MINUTE_WORD})"
    rf"[\s-]*(?P<ampm>{_AMPM})",
    re.IGNORECASE,
)

_TWELVE_NOON_MIDNIGHT_RE = re.compile(
    rf"\btwelve[\s-]+(?P<marker>{_NOON}|{_MIDNIGHT})\b",
    re.IGNORECASE,
)

_HOUR_OCLOCK_RE = re.compile(
    rf"\b{_HOUR_WORD}[\s-]+{_OCLOCK}\b",
    re.IGNORECASE,
)

_MILITARY_HUNDRED_RE = re.compile(
    rf"\b(?P<hour>{_MILITARY_HOUR})[\s-]+hundred[\s-]+hours\b",
    re.IGNORECASE,
)

_MILITARY_HHMM_RE = re.compile(
    rf"\b(?P<hour>{_MILITARY_HOUR})[\s-]+(?P<minute>{_MINUTE_WORD})"
    r"[\s-]+hours\b",
    re.IGNORECASE,
)


def _parse_cardinal(text: str) -> int | None:
    """Parse 0..99 plus 'one hundred' constructions up to 119."""
    stripped = text.strip().lower()
    if not stripped:
        return None
    tokens = [t for t in re.split(r"[\s-]+", stripped) if t and t != "and"]
    if not tokens:
        return None

    if "hundred" in tokens:
        idx = tokens.index("hundred")
        hundreds_word = tokens[:idx]
        if not hundreds_word:
            return None
        hundreds_value = _parse_cardinal_0_99(hundreds_word)
        if hundreds_value is None or hundreds_value != 1:
            return None
        rest = tokens[idx + 1 :]
        if not rest:
            return 100
        rest_value = _parse_cardinal_0_99(rest)
        if rest_value is None:
            return None
        return 100 + rest_value

    return _parse_cardinal_0_99(tokens)


def _parse_minute(text: str) -> int | None:
    """Parse a minute word into 0..59. Accepts 'oh five' style."""
    stripped = text.strip().lower()
    if not stripped:
        return None
    tokens = [t for t in re.split(r"[\s-]+", stripped) if t]
    if not tokens:
        return None
    if tokens[0] == "oh" and len(tokens) == 2:
        unit = _parse_cardinal_0_99([tokens[1]])
        if unit is None or not (0 <= unit <= 9):
            return None
        return unit
    value = _parse_cardinal_0_99(tokens)
    if value is None:
        return None
    if not (_MIN_MINUTE <= value <= _MAX_MINUTE):
        return None
    return value


def _parse_military_hour(text: str) -> int | None:
    """Parse a military hour word into 0..23."""
    stripped = text.strip().lower()
    if not stripped:
        return None
    tokens = [t for t in re.split(r"[-\s]+", stripped) if t]
    if not tokens:
        return None
    if tokens[0] == "oh" and len(tokens) == 2:
        unit = _parse_cardinal_0_99([tokens[1]])
        if unit is None or not (0 <= unit <= 9):
            return None
        return unit
    value = _parse_cardinal_0_99(tokens)
    if value is None:
        return None
    if not (_MIN_HOUR_24 <= value <= _MAX_HOUR_24):
        return None
    return value


def _normalize_ampm(ampm_raw: str) -> str:
    """Normalize input casing into 'a.m.' / 'p.m.' output form."""
    stripped = ampm_raw.strip().lower().replace(" ", "")
    if stripped in {"am", "a.m."}:
        return "a.m."
    if stripped in {"pm", "p.m."}:
        return "p.m."
    return ampm_raw


def _handle_age(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    """Handle a single age-pattern match."""
    age_value = _parse_cardinal(match.group("age"))
    if age_value is None or not (_MIN_AGE <= age_value <= _MAX_AGE):
        return None
    full = match.group(0)
    age_token = match.group("age")
    age_idx = full.lower().find(age_token.lower())
    if age_idx == -1:
        return None
    new_full = full[:age_idx] + str(age_value) + full[age_idx + len(age_token) :]
    new_text = text[: match.start()] + new_full + text[match.end() :]
    return new_text, match.start() + len(new_full)


def _handle_hour_ampm(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    hour_value = _parse_cardinal(match.group("hour"))
    if hour_value is None or not (_MIN_HOUR_12 <= hour_value <= _MAX_HOUR_12):
        return None
    ampm = _normalize_ampm(match.group("ampm"))
    replacement = f"{hour_value} {ampm}"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_hour_minute_ampm(
    text: str, match: re.Match[str]
) -> tuple[str, int] | None:
    hour_value = _parse_cardinal(match.group("hour"))
    minute_value = _parse_minute(match.group("minute"))
    if hour_value is None or not (_MIN_HOUR_12 <= hour_value <= _MAX_HOUR_12):
        return None
    if minute_value is None:
        return None
    ampm = _normalize_ampm(match.group("ampm"))
    replacement = f"{hour_value}:{minute_value:02d} {ampm}"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_twelve_noon_midnight(
    text: str, match: re.Match[str]
) -> tuple[str, int] | None:
    marker = match.group("marker").lower()
    replacement = f"12 {marker}"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_military_hundred(
    text: str, match: re.Match[str]
) -> tuple[str, int] | None:
    hour_value = _parse_military_hour(match.group("hour"))
    if hour_value is None:
        return None
    replacement = f"{hour_value:02d}00 hours"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _handle_military_hhmm(text: str, match: re.Match[str]) -> tuple[str, int] | None:
    hour_value = _parse_military_hour(match.group("hour"))
    minute_value = _parse_minute(match.group("minute"))
    if hour_value is None or minute_value is None:
        return None
    replacement = f"{hour_value:02d}{minute_value:02d} hours"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, match.start() + len(replacement)


def _oclock_spans(text: str) -> list[tuple[int, int]]:
    """Spans of '<hour> o'clock' constructions."""
    return [(m.start(), m.end()) for m in _HOUR_OCLOCK_RE.finditer(text)]


def _position_in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _normalize_text(text: str) -> str:
    """Apply age and time normalization to a single text string."""
    if not text:
        return text

    out = text

    pos = 0
    while True:
        match = _AGE_YEARS_OLD_RE.search(out, pos)
        if match is None:
            break
        result = _handle_age(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result

    pos = 0
    while True:
        match = _AGE_YEARS_OF_AGE_RE.search(out, pos)
        if match is None:
            break
        result = _handle_age(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result

    pos = 0
    while True:
        match = _AGE_PREFIX_RE.search(out, pos)
        if match is None:
            break
        result = _handle_age(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result

    pos = 0
    while True:
        match = _TWELVE_NOON_MIDNIGHT_RE.search(out, pos)
        if match is None:
            break
        result = _handle_twelve_noon_midnight(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result

    inhibit_spans = _oclock_spans(out)

    pos = 0
    while True:
        match = _MILITARY_HUNDRED_RE.search(out, pos)
        if match is None:
            break
        if _position_in_spans(match.start(), inhibit_spans):
            pos = match.end()
            continue
        result = _handle_military_hundred(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result
        inhibit_spans = _oclock_spans(out)

    pos = 0
    while True:
        match = _MILITARY_HHMM_RE.search(out, pos)
        if match is None:
            break
        if _position_in_spans(match.start(), inhibit_spans):
            pos = match.end()
            continue
        result = _handle_military_hhmm(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result
        inhibit_spans = _oclock_spans(out)

    pos = 0
    while True:
        match = _HOUR_MINUTE_AMPM_RE.search(out, pos)
        if match is None:
            break
        if _position_in_spans(match.start(), inhibit_spans):
            pos = match.end()
            continue
        result = _handle_hour_minute_ampm(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result
        inhibit_spans = _oclock_spans(out)

    pos = 0
    while True:
        match = _HOUR_AMPM_RE.search(out, pos)
        if match is None:
            break
        if _position_in_spans(match.start(), inhibit_spans):
            pos = match.end()
            continue
        result = _handle_hour_ampm(out, match)
        if result is None:
            pos = match.end()
            continue
        out, pos = result
        inhibit_spans = _oclock_spans(out)

    return out


def normalize_ages_and_times(
    blocks: list[TranscriptBlock],
) -> list[TranscriptBlock]:
    """Apply age and time normalization to every block."""
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
