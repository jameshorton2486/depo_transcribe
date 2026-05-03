"""
Regex-based case vocabulary extraction and evaluation helpers.

Used as a conservative fallback when AI intake parsing is unavailable.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app_logging import get_logger

logger = get_logger(__name__)

_LEGAL_DICTIONARY_PATH = Path(__file__).parent / "legal_dictionary.json"
_legal_dictionary_cache: dict[str, str] | None = None


def load_legal_dictionary() -> dict[str, str]:
    """Return the hand-maintained baseline mishearings → corrections map.

    Loaded once and cached. Empty dict if the file is missing or malformed.
    Per-case NOD spellings should override these at the corrections layer
    (see spec_engine.corrections._build_corrections_map).
    """
    global _legal_dictionary_cache
    if _legal_dictionary_cache is not None:
        return _legal_dictionary_cache

    if not _LEGAL_DICTIONARY_PATH.exists():
        _legal_dictionary_cache = {}
        return _legal_dictionary_cache

    try:
        with open(_LEGAL_DICTIONARY_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.warning("[LegalDict] Failed to load %s: %s", _LEGAL_DICTIONARY_PATH, exc)
        _legal_dictionary_cache = {}
        return _legal_dictionary_cache

    spellings = data.get("spellings", {}) if isinstance(data, dict) else {}
    if not isinstance(spellings, dict):
        logger.warning("[LegalDict] 'spellings' must be an object; ignoring")
        _legal_dictionary_cache = {}
        return _legal_dictionary_cache

    cleaned = {
        str(k).strip(): str(v).strip()
        for k, v in spellings.items()
        if str(k).strip() and str(v).strip()
    }
    _legal_dictionary_cache = cleaned
    if cleaned:
        logger.info("[LegalDict] Loaded %d baseline entries", len(cleaned))
    return cleaned

US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}

PRONOUNS = {
    "i",
    "me",
    "my",
    "mine",
    "myself",
    "we",
    "us",
    "our",
    "ours",
    "ourselves",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "it",
    "its",
    "itself",
}

ROLE_CANON = {
    "claimant": "Claimant",
    "respondent": "Respondent",
    "deponent": "Deponent",
    "witness": "Witness",
    "authorized representative": "Authorized Representative",
    "attorney of record": "Attorney of Record",
    "attorneys for claimant": "Attorneys for Claimant",
    "attorneys for respondent": "Attorneys for Respondent",
    "ordering attorney": "Ordering Attorney",
    "copy attorney": "Copy Attorney",
}

LEGAL_PHRASE_SEEDS = [
    "Notice of Intent to Take",
    "Zoom Video Deposition",
    "Oral Deposition",
    "Certificate of Service",
    "Respectfully submitted",
]

ORG_SUFFIXES = (
    "Inc",
    "Inc.",
    "LLP",
    "L.L.P.",
    "LLC",
    "L.L.C.",
    "Association",
    "Solutions",
    "Guides",
    "Company",
    "Co.",
    "Corp.",
    "Corporation",
)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\u00a0", " "))


def _squeeze_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_diacritics_for_matching(text: str) -> str:
    d = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in d if not unicodedata.combining(ch))


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        value = _squeeze_ws(item)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _extract_dates_times(text: str) -> tuple[set[str], set[str]]:
    dates: set[str] = set()
    times: set[str] = set()

    for mm, dd, yyyy in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        try:
            dates.add(date(int(yyyy), int(mm), int(dd)).isoformat())
        except ValueError:
            pass

    for mon, dd, yyyy in re.findall(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    ):
        try:
            mm = datetime.strptime(mon[:3].title(), "%b").month
            dates.add(date(int(yyyy), mm, int(dd)).isoformat())
        except ValueError:
            pass

    for hh, mm, ampm in re.findall(
        r"\b(\d{1,2}):(\d{2})\s*(A\.?M\.?|P\.?M\.?)\b", text, flags=re.IGNORECASE
    ):
        h = int(hh)
        m = int(mm)
        ap = ampm.replace(".", "").upper()
        if ap == "PM" and h != 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            times.add(f"{h:02d}:{m:02d}")

    return dates, times


def _extract_pronouns(text: str) -> set[str]:
    toks = re.findall(r"[A-Za-z']+", text.lower())
    out = {t for t in toks if t in PRONOUNS}
    if "his/her" in text.lower():
        out.add("his/her")
    return out


def _extract_numeric_expressions(text: str) -> set[str]:
    out: set[str] = set()
    out.update(re.findall(r"\b\d{2,}-\d{2,}-\d{2,}-\d{2,}\b", text))
    out.update(re.findall(r"\bCase\s+No\.?\s*[\w\-]+\b", text, flags=re.IGNORECASE))
    out.update(re.findall(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", text))
    out.update(re.findall(r"\b[A-Za-z]+\s*\(\d+\)\b", text))
    out.update(re.findall(r"\b\d+\.\d+(?:\([^)]+\))*\b", text))
    return {_squeeze_ws(x) for x in out}


def _extract_locations(text: str) -> set[str]:
    out: set[str] = set()
    for city, st in re.findall(r"\b([A-Z][A-Za-z.\-'\s]{2,40}),\s*([A-Z]{2})\b", text):
        if st in US_STATES:
            out.add(f"{_squeeze_ws(city)}, {st}")
    return out


def _extract_rule_citations(text: str) -> set[str]:
    return {
        _squeeze_ws(match)
        for match in re.findall(
            r"\bTexas Rule of Civil Procedure\s+\d+\.\d+(?:\([^)]+\))*\b",
            text,
            flags=re.IGNORECASE,
        )
    }


def _canonicalize_person(name: str) -> str:
    name = _squeeze_ws(name)
    parts = name.split()
    out = []
    for part in parts:
        if re.fullmatch(r"[A-Z]\.", part):
            out.append(part)
            continue
        if re.fullmatch(r"(II|III|IV|V)", part):
            out.append(part)
            continue
        if part.lower() in {"jr", "jr.", "sr", "sr."}:
            out.append("Jr." if part.lower().startswith("jr") else "Sr.")
            continue
        if part.startswith('"') and part.endswith('"') and len(part) > 2:
            out.append(part)
            continue
        sub = re.split(r"([-'])", part)
        rebuilt = []
        for s in sub:
            if s in {"-", "'"}:
                rebuilt.append(s)
            else:
                rebuilt.append(s[:1].upper() + s[1:].lower() if s else s)
        out.append("".join(rebuilt))
    return " ".join(out)


def _canonicalize_org(org: str) -> str:
    org = _squeeze_ws(org)
    words = org.split()
    out = []
    for word in words:
        if word == "&":
            out.append("&")
            continue
        base = word.rstrip(".,")
        punct = word[len(base) :]
        up = base.upper()
        if up in {"LLP", "LLC", "INC", "CO", "CORP", "CSR", "AAA"}:
            out.append(up + punct)
        else:
            out.append(base[:1].upper() + base[1:].lower() + punct)
    return " ".join(out)


def _extract_people_and_orgs(text: str) -> tuple[list[str], list[str]]:
    cap = r"(?:[A-Z][a-z\u00C0-\u017F]+|[A-Z\u00C0-\u017F]{2,})(?:[-'][A-Za-z\u00C0-\u017F]+)?"
    init = r"(?:[A-Z]\.)"
    suffix = r"(?:Jr\.?|Sr\.?|II|III|IV)"
    nick = r"\"[A-Za-z\u00C0-\u017F]+\""

    person_pat = re.compile(
        rf"\b{cap}(?:\s+{init})?(?:\s+{nick})?(?:\s+{cap}){{1,3}}(?:\s+{suffix})?\b"
    )
    candidates = []
    stop_tokens = {
        "Texas",
        "Rule",
        "Civil",
        "Procedure",
        "Zoom",
        "Deposition",
        "Certificate",
        "Service",
        "Case",
        "No",
        "First",
        "Amended",
        "Notice",
        "Of",
    }
    people = []

    suff = "|".join(re.escape(s) for s in ORG_SUFFIXES)
    org_pat = re.compile(
        rf"\b(?:[A-Z][A-Za-z\u00C0-\u017F&.\-']+|[A-Z]{{2,}})\s+"
        rf"(?:(?:[A-Z][A-Za-z\u00C0-\u017F&.\-']+|[A-Z]{{2,}})\s+)*"
        rf"(?:{suff})\b"
    )
    orgs = []

    for raw_line in text.splitlines():
        line = _squeeze_ws(raw_line)
        if not line:
            continue
        if any(seed.lower() in line.lower() for seed in LEGAL_PHRASE_SEEDS):
            orgs.extend(_canonicalize_org(m.group(0)) for m in org_pat.finditer(line))
            continue
        candidates.extend(m.group(0) for m in person_pat.finditer(line))
        orgs.extend(_canonicalize_org(m.group(0)) for m in org_pat.finditer(line))

    for candidate in candidates:
        toks = candidate.split()
        if len(toks) < 2:
            continue
        if any(t.strip(".,:;").title() in stop_tokens for t in toks):
            continue
        if any(sfx in candidate for sfx in ORG_SUFFIXES):
            continue
        people.append(_canonicalize_person(candidate))

    return _dedupe_preserve(people), _dedupe_preserve(orgs)


def _extract_roles(text: str) -> list[str]:
    found = []
    for key, canon in ROLE_CANON.items():
        if re.search(rf"\b{re.escape(key)}\b", text, flags=re.IGNORECASE):
            found.append(canon)
    return _dedupe_preserve(found)


def _extract_legal_phrases(text: str) -> list[str]:
    found = []
    for phrase in LEGAL_PHRASE_SEEDS:
        if re.search(re.escape(phrase), text, flags=re.IGNORECASE):
            found.append(phrase)
    found.extend(sorted(_extract_rule_citations(text)))
    found.extend(re.findall(r"\bCase\s+No\.?\s*[\w\-]+\b", text, flags=re.IGNORECASE))
    return _dedupe_preserve(found)


def _suggest_speaker_map(
    text: str, people: list[str], orgs: list[str], roles: list[str]
) -> dict[str, Any]:
    sm: dict[str, Any] = {}

    if "Deponent" in roles and people:
        sm.setdefault("deponent", people[0])
        sm.setdefault("witness", people[0])
    if "Claimant" in roles and people:
        sm.setdefault("claimant", people[0])
    if "Respondent" in roles and orgs:
        sm.setdefault("respondent", orgs[0])

    speaker_lines = re.findall(
        r"(?m)^(MR\.|MS\.|MRS\.|DR\.)\s+([A-Z][A-Z'\-]+)\s*:\s*$", text
    )
    for honor, last in speaker_lines:
        label = f"{honor} {last}:"
        sm.setdefault(label, _canonicalize_person(f"{honor.title()} {last.title()}"))

    if re.search(r"(?m)^Q\.\s", text):
        sm.setdefault("Q.", "Questioner (Attorney)")
    if re.search(r"(?m)^A\.\s", text):
        sm.setdefault("A.", "Witness/Deponent")
    return sm


def build_case_vocab_from_text(raw_text: str) -> dict[str, Any]:
    text = _nfc(raw_text or "")
    text_nl = text
    text_sp = _squeeze_ws(text)

    people, orgs = _extract_people_and_orgs(text_nl)
    roles = _extract_roles(text_nl)
    phrases = _extract_legal_phrases(text_nl)
    pronouns = sorted(_extract_pronouns(text_sp))
    dates, times = _extract_dates_times(text_sp)
    nums = sorted(_extract_numeric_expressions(text_sp))
    locs = sorted(_extract_locations(text_nl))

    deepgram_keyterms = _dedupe_preserve(people + orgs + phrases)

    confirmed_spellings: dict[str, str] = {}
    for item in people + orgs:
        alias = _strip_diacritics_for_matching(item)
        if alias != item:
            confirmed_spellings[alias] = item

    return {
        "deepgram_keyterms": deepgram_keyterms,
        "confirmed_spellings": confirmed_spellings,
        "speaker_map_suggestion": _suggest_speaker_map(text_nl, people, orgs, roles),
        "counts": {
            "People": len(people),
            "Orgs": len(orgs),
            "Legal Roles": len(roles),
            "Legal Phrases": len(phrases),
            "Pronouns": len(pronouns),
            "Dates": len(dates),
            "Times": len(times),
            "Locations": len(locs),
            "Numeric Expressions": len(nums),
        },
        "examples": {
            "People": people[:8],
            "Orgs": orgs[:8],
            "Legal Roles": roles[:8],
            "Legal Phrases": phrases[:8],
            "Pronouns": pronouns[:8],
            "Dates": sorted(dates),
            "Times": sorted(times),
            "Locations": locs[:5],
            "Numeric Expressions": nums[:8],
        },
    }


def _string_set(xs: list[str]) -> set[str]:
    return {x.strip().lower() for x in xs if x and x.strip()}


def recall(extracted: list[str], gold: list[str]) -> float:
    ex = _string_set(extracted)
    gd = _string_set(gold)
    if not gd:
        return 1.0
    return sum(1 for g in gd if g in ex) / len(gd)


def precision(extracted: list[str], gold: list[str]) -> float:
    ex = _string_set(extracted)
    gd = _string_set(gold)
    if not ex:
        return 1.0 if not gd else 0.0
    return sum(1 for e in ex if e in gd) / len(ex)


def f1(precision_value: float, recall_value: float) -> float:
    return (
        0.0
        if (precision_value + recall_value) == 0
        else 2 * precision_value * recall_value / (precision_value + recall_value)
    )
