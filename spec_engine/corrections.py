"""
corrections.py

All text correction rules from DepoPro Spec Section 2.
Applied in exact priority order from Spec Section 9.4.

PRIORITY ORDER (MUST NOT CHANGE):
  1.  Multi-word name phrases and objection garbles
  2.  Case-specific proper noun corrections (from confirmed_spellings)
  3.  Universal corrections (Doctor., K., Mm-hmm, Alright, % → percent, etc.)
  4a. Number-to-word in count context (1-10)
  4b. Date mashup flagging
  4c. Numbers at sentence start spelled out (Morson's English Guide)
  5.  Deepgram artifact removal (doubled words — 4+ chars only)
  6.  Spaced dashes (word--word → word -- word)           ← NEW
  7.  Uh-huh / Uh-uh hyphenation normalization            ← NEW
  8.  Even dollar amount cleanup ($450.00 → $450)         ← NEW
  9.  Conversational titles (miss → Ms., mister → Mr.)    ← NEW
  10. Normalize spaces  ← MUST precede two-space rule
  11. Capitalize first character
  12. Direct address comma (Yes, sir. / All right, Counsel.)
  13. Terminal punctuation enforcement
  14. Two-space rule after sentence-ending punctuation  ← RUNS LAST
  --  Yeah/Yep/Yup/Nope/Nah: NEVER normalized — added to VERBATIM_PROTECTED
  --  uh/um: NEVER touched — verbatim rule is absolute

VERBATIM RULE: "uh" and "um" are NEVER removed. This is enforced by unit tests.
MORSON'S RULE: Numbers 1-10 at sentence start must be spelled out as words.
MORSON'S RULE 270: Ellipsis in any form (. . .) is never touched.
"""

import re
import logging
from typing import List, Optional, Tuple

from .models import Block, CorrectionRecord, JobConfig, ScopistFlag

logger = logging.getLogger(__name__)


TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*(AM|PM)\b\.?", re.IGNORECASE)


# ── Number-to-word maps ───────────────────────────────────────────────────────

# Mid-sentence count context (lowercase)
NUMBER_WORD_MAP = {
    '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five',
    '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten',
}

# Sentence-start context (capitalized per Morson's)
SENTENCE_START_NUMBER_WORDS = {
    '1': 'One', '2': 'Two', '3': 'Three', '4': 'Four', '5': 'Five',
    '6': 'Six', '7': 'Seven', '8': 'Eight', '9': 'Nine', '10': 'Ten',
}

# Exclusion contexts — do NOT convert numbers in these patterns
NUMBER_EXCLUSION_RE = re.compile(
    r'(?:'
    r'[Ee]xhibit\s+(?:No\.\s+)?\d'      # Exhibit 3 / Exhibit No. 15
    r'|No\.\s+\d'                         # Exhibit No. / CSR No. / Cause No. —
                                         # "No." before a digit is always a legal
                                         # reference, never a count. Guards the digit
                                         # even when "Exhibit" is outside the 8-char
                                         # apply_number_to_word() window.
    r'|\d{1,2}:\d{2}'       # time (2:30)
    r'|\$\s*\d'             # dollar amount
    r'|I-\d'                # interstate highways (I-10)
    r'|\d{3,}'              # address or long number (123 Main)
    r'|\d[/\-]\d'           # date fraction (4/17) or range
    r')',
)

# Sentence start: digit 1-10 as the FIRST token in the block
SENTENCE_START_NUM_RE = re.compile(
    r'^([1-9]|10)\b(?!\s*(?:a\.m|p\.m|\d|:))'
)


# ── Verbatim-protected words (Spec Section 2.1) ───────────────────────────────
VERBATIM_PROTECTED = {
    # Acknowledgement words — Morson's Rule 4
    'okay', 'well',
}

# Affirmation words preserved per Spec 9.6 unit test
# "correct correct" must remain — common witness affirmation pattern
AFFIRMATION_PROTECTED = {
    'correct', 'right', 'exactly', 'absolutely', 'definitely',
    'yeah', 'yep', 'yup', 'nope', 'nah',
}


# ── Multi-word phrase corrections (Priority 1 — Spec 9.4 Step 1) ─────────────
MULTIWORD_CORRECTIONS: List[Tuple[str, str]] = [
    # Legal term — all Deepgram variants of "subpoena duces tecum"
    (r'\bsub[cp]oena\s+deuces?\s+ti[ck]um\b',  'subpoena duces tecum'),
    (r'\bde\s+sus\s+ti[ck]um\b',               'subpoena duces tecum'),
    (r'\bdeuceus\s+ti[ck]um\b',                'subpoena duces tecum'),
    (r'\bdue\s+to\s+ste[ck]um\b',              'subpoena duces tecum'),
    (r'\bdeusis\s+[Tt]ecum\b',                 'subpoena duces tecum'),
    (r'\bduces\s+take\s+them\b',               'subpoena duces tecum'),
    (r'\bdeuces\s+ti[ck]um\b',                 'subpoena duces tecum'),
    (r'\bdeuces\s+tek[uo]m\b',                 'subpoena duces tecum'),
    (r'\bde\s+sus\s+tec?um\b',                 'subpoena duces tecum'),

    # Law firm — multi-word must precede single-word name corrections
    (r'\bAllen[\s,]+Stein[\s,]+[ií]n[\s,]+Durbin\b',   'Allen, Stein & Durbin, P.C.'),
    (r'\bAllen[\s,]+Stein[\s,]+and[\s,]+Durbin\b',     'Allen, Stein & Durbin, P.C.'),
    (r'\bAllen[\s,]+Stein[\s,]+&[\s,]+Durbin\b',       'Allen, Stein & Durbin, P.C.'),
    (r'\bTexan\s+Medical\s+Legal\b',                    'Texas Medical Legal Consultants'),
    (r'\bBrook\s+Army\s+Medical\s+Center\b',            'Brooke Army Medical Center'),
    (r'\bClean\s*[Ss]capes?\b',                         'Clean Scapes Enterprises, Inc.'),
    (r'\bWill\s*[Tt]ower\b',                            'William Tower'),
    (r'\bPLC\s+account\b',                              'PLLC account'),
    (r'\bfiftyfifty\b',                                  'fifty-fifty'),

    # ASR garble → verbatim objection form
    # ── Objection garble — single word variants → "Objection." ──────────────
    # These are universal: apply to every deposition regardless of case.
    # Source: DeproPro Reference Rev 2, Table 5 (Q/A Classification)
    (r'\bInjection\b(?!\s+form)[.]?',   'Objection.'),
    (r'\bInfection\b[.]?',              'Objection.'),
    (r'\bDetection\b[.]?',              'Objection.'),
    (r'\bProtection\b(?!\s+order)[.]?', 'Objection.'),
    (r'\bPerfection\b[.]?',             'Objection.'),
    (r'\bEviction\b[.]?',               'Objection.'),
    (r'\bDefinition\b[.]?',             'Objection.'),

    # ── Objection + Form two-word variants → "Objection. Form." ─────────────
    (r'\bInjection\s+[Ff]orm\b[.]?',   'Objection. Form.'),
    (r'\bDirection\s+[Ff]orm\b[.]?',   'Objection. Form.'),

    # ── Form and leading variants → "Form and leading." ──────────────────────
    (r'\bFormer\s+[Ll]eaving\b[.]?',    'Form and leading.'),
    (r'\bForm\s+and\s+[Ll]eaving\b[.]?','Form and leading.'),
    (r'\bForm\s+and\s+[Ll]egal\b[.]?',  'Form and leading.'),

    # ── Leading variants → "Leading." ────────────────────────────────────────
    (r'\bBleeding\b[.]?',               'Leading.'),
    (r'\bLeaving\b[.]?',                'Leading.'),
    (r'\bWarming\b[.]?',                'Leading.'),
    (r'\bWarm\s+[Ll]eading\b[.]?',      'Leading.'),

    # ── Pass the witness variants → "Pass the witness." ──────────────────────
    # WARNING: "pass away" is intentionally excluded — it means to die.
    (r'\bPast\s+[Ww]itness\b[.]?',      'Pass the witness.'),
    (r'\bPastor\s+[Ww]itness\b[.]?',    'Pass the witness.'),
    # ── Additional objection garbles (confirmed across multiple depositions) ──
    (r'\bDissection\b[.]?',              'Objection.'),
    (r'\bPerception\b[.]?',              'Objection.'),
    (r'\bAddiction\b[.]?',               'Objection.'),
    (r'\bDeflection\b[.]?',              'Objection.'),
    # Combined forms of the new variants
    (r'\bDissection\s+[Ff]orm\b[.]?',    'Objection. Form.'),
    (r'\bPerception\s+[Ff]orm\b[.]?',    'Objection. Form.'),
    (r'\bAddiction\s+[Ff]orm\b[.]?',     'Objection. Form.'),
    (r'\bDeflection\s+[Ff]orm\b[.]?',    'Objection. Form.'),
    # "Counsel, state the basis" — garbled version of attorney's request
    (r'\bcan\s+cancel\s+state\s+the\s+basis\b',  'Counsel, state the basis'),
    (r'\bcancel\s+state\s+the\s+basis\b',         'Counsel, state the basis'),
    (r'\bcounsel\s+say\s+the\s+basis\b',          'Counsel, state the basis'),
    # ── Universal trucking / CDL vocabulary garbles ───────────────────────────
    # These appear across all trucking depositions regardless of case.
    # "belly dump" — type of dump truck. Deepgram hears "Betty" or "belly"
    (r'\b[Bb]etty\s+[Dd]ump\b',     'belly dump'),
    # "super dump" — type of dump truck. Deepgram hears "dumb"
    (r'\bsuper\s+dumb\b',            'super dump'),
    # "pre-trip inspection" — mandatory CDL inspection. Deepgram hears "free"
    (r'\bfree\s+trip\b',             'pre-trip'),
    (r'\bfree-trip\b',               'pre-trip'),
    (r'\bfree\s+trip\s+inspection\b','pre-trip inspection'),
    # "scale house" — DOT weigh station. Deepgram hears "scaler"
    (r'\bscaler\s+house\b',          'scale house'),
    (r'\bscaler\s+houses?\b',        'scale house'),
    # "CDL handbook" / "CDL manual" — Deepgram hears "CDO" or "CEO"
    (r'\bCDO\s+handbook\b',          'CDL handbook'),
    (r'\bCDO\s+manual\b',            'CDL manual'),
    (r'\bCEO\s+handbook\b',          'CDL handbook'),
    (r'\bCEO\s+manual\b',            'CDL manual'),
    (r'\bCVL\s+handbook\b',          'CDL handbook'),
    (r'\bCVL\s+manual\b',            'CDL manual'),
    # "tractor trailer" spacing variant
    (r'\btrailer\s+trailer\b',       'tractor trailer'),
    (r'\btrucker\s+trailer\b',       'tractor trailer'),
    # "bill of lading" — Deepgram garbles
    (r'\bbill\s+of\s+[Ll]ayding\b',  'bill of lading'),
    (r'\bbill\s+of\s+[Ll]aden\b',    'bill of lading'),
    # "hours of service" — HOS regulations
    (r'\bours\s+of\s+service\b',     'hours of service'),
    # "out of service" — DOT violation type
    (r'\bout\s+of\s+server\b',       'out of service'),
    # Exhibit number formatting — Morson's Rule 217
    # exhibit 15 / exhibit no 15 / exhibit number 15 → Exhibit No. 15
    (r'\b[Ee]xhibit\s+[Nn]umber\s+(\d+)\b',  r'Exhibit No. \1'),
    (r'\b[Ee]xhibit\s+[Nn]o\.?\s+(\d+)\b',   r'Exhibit No. \1'),
    (r'\b[Ee]xhibit\s+(\d+)\b',               r'Exhibit No. \1'),
    # 408th Judicial District — Deepgram digit-by-digit garbles
    # Appears in reporter preamble on every Bexar County deposition.
    (r'\b4\s+0\s+8(?:th)?\s+[Jj]udicial\s+[Dd]istrict\b',
     '408th Judicial District'),
    (r'\bfour\s+o\s+eight\s+[Jj]udicial\s+[Dd]istrict\b',
     '408th Judicial District'),
    (r'\bfour\s+zero\s+eight\s+[Jj]udicial\s+[Dd]istrict\b',
     '408th Judicial District'),
    (r'\b408\s+[Jj]udicial\s+[Dd]istrict\b',
     '408th Judicial District'),
    # "Cause Number" preamble garbles — Deepgram mishears "cop number"
    (r'\bcop\s+number\b',            'Cause Number'),
    (r'\bcaught\s+number\b',         'Cause Number'),
    (r'\bcause\s+numbers?\b',        'Cause Number'),
    # "non-CDL" split forms
    (r'\bnon\s+CDL\b',               'non-CDL'),
    (r'\bnon-CDO\b',                 'non-CDL'),
]


# ── Universal single corrections (Priority 3 — Spec 9.4 Step 3) ──────────────
UNIVERSAL_CORRECTIONS: List[Tuple[str, str]] = [
    # Reporter label normalization must run before generic word-split cleanup
    (r'\bTHE\s+COURT\s+REPORTER\s*:', 'THE REPORTER:'),

    # Texas highway number formatting
    (r'\bI\s+10\b', 'I-10'),
    (r'\bI\s+20\b', 'I-20'),
    (r'\bI\s+35\b', 'I-35'),
    (r'\bI\s+37\b', 'I-37'),
    (r'\bI\s+45\b', 'I-45'),
    (r'\bI\s+410\b', 'I-410'),

    # Loop / FM road formatting
    (r'\bLoop\s+1604\b', 'Loop 1604'),
    (r'\bFM\s+(\d+)\b', r'FM \1'),

    # Doctor. artifact — Deepgram adds period after "Doctor" before a name
    (r'\bDoctor\.\s+', 'Dr. '),

    # Standalone K/k → Okay.  (word boundary + space-or-end lookahead)
    (r'(?<![a-zA-Z])[Kk]\.(?=\s|$)',  'Okay.'),

    # Mid-sentence Okay / All right before the next capitalized sentence
    (r'\b(Okay|All right),\s+(?=[A-Z])', r'\1.  '),

    # Mhmm variants → Mm-hmm (idempotent — matches only un-normalized forms)
    (r'\b[Mm]hmm\b',  'Mm-hmm'),
    (r'\b[Mm]mhm\b',  'Mm-hmm'),

    # Brooke Army Medical Center
    (r'\bBrook\s+Army\b', 'Brooke Army'),

    # Deepgram word splits
    (r'\bvideo\s+grapher\b',     'videographer'),
    (r'\bcourt\s+report\s*er\b', 'court reporter'),

    # Standalone subpoena garbles
    (r'\bsubpeona\b', 'subpoena'),
    (r'\bsubpena\b', 'subpoena'),
    (r'\bsubpoina\b', 'subpoena'),
    (r'\bsubpeana\b', 'subpoena'),
    (r'\bsub-poena\b', 'subpoena'),
    (r'\bsupboena\b', 'subpoena'),
    (r'\bsub poena\b', 'subpoena'),
    # ── Reporter name normalization — Miah Bardot, CSR No. 12129 ─────────────
    # Deepgram mishears "Miah Bardot" in the reporter's opening statement.
    # These garbles appear at the start of every deposition she reports.
    # NOTE: Only correct the NAME — the CSR number is corrected separately
    #       by the cause-number normalization in apply_date_normalization().
    (r'\bMia\s+[Bb]ardell?\b',        'Miah Bardot'),
    (r'\bMia\s+[Bb]ordeau\b',         'Miah Bardot'),
    (r'\bMia\s+[Bb]ardeau\b',         'Miah Bardot'),
    (r'\bNeobardeau\b',               'Miah Bardot'),
    (r'\bMiyamardeau\b',              'Miah Bardot'),
    (r'\bLea\s+[Bb]ardot?\b',         'Miah Bardot'),
    (r'\bLea\s+[Bb]ardeau\b',         'Miah Bardot'),
    (r'\b[Mm]ia\s+[Bb]ardot\b',       'Miah Bardot'),
    # CSR number garbles in the reporter's opening statement
    (r'\bLicense\s+Number\s+12129\b',  'CSR No. 12129'),
    (r'\bnumber\s+12129\b',            'No. 12129'),
    (r'\b12129\.\s*9\b',               '12129'),

    # Deepgram zip code / number artifacts
    (r'\b[Rr]oad morning\b', 'Good morning'),
    (r'\bvampires are\b', 'OR fires are'),
    (r'\bright tibral bypass\b', 'right temporal bypass'),
    # ASR garble → verbatim objection form (Morson's: two sentences, as spoken)
    (r'\bExit form\b[.]?', 'Objection. Form.'),
    (r'\bAction form\b[.]?', 'Objection. Form.'),
    (r'\bAction point\b[.]?', 'Objection. Form.'),
    (r'\bObjection form\b[.]?', 'Objection. Form.'),
    (r'(?<!\. )\.{4}(?!\.)(?!\s*\.)', '. . . .'),
    (r'(?<!\. )\.{3}(?!\.)(?!\s*\.)', '. . .'),
    (r'\. \.\.', '. . .'),
    (r'\.\. \.', '. . .'),
    (r'\band\s*/\s*or\b', 'and/or'),
    (r'\beither\s*/\s*or\b', 'either/or'),

    # Oath / opening garbles
    (r'\bso\s+I\s+help\s+you\s+guide\b', 'so help you God'),
    (r'\bso\s+help\s+you\s+guide\b', 'so help you God'),
    (r'\bI\s+help\s+you\s+God\b', 'so help you God'),
    (r'\bnotice\s+seen\s+attorney\b', 'noticing attorney'),
    (r'\bremotes?\s+to\s+(?:any|ring)\s+witness\b', 'remote swearing of the witness'),
    (r'\bremote\s+swear\b', 'remote swearing'),

    # Reporter caption / certification garbles
    (
        r'\bon\s+me\s+of\s+our\s+court\s+for\s+our\s+license\s+in\s+Texas\s+number\s+(\d+)\b',
        r'CSR No. \1',
    ),

    # Cause number formatting (Texas)
    (r'\b(\d{4})\s+CI\s+(\d+)\b', r'\1-CI-\2'),
    # Cause number: "Cause number 24,2754" → "Cause number 24-2754"
    # Context-scoped to legal cause-number phrases only.
    (
        r'(\b(?:Cause\s+No\.?|Cause\s+Number|cause\s+number)\s+)(\d{2}),(\d{3,5})\b',
        r'\1\2-\3',
    ),
    # 4-digit year variant: "2025,12281" → "2025-CI-12281" (won't catch all)
    # This just ensures the simpler 2-digit year format is covered

    # Cross-examination hyphen (Spec Section 4.1)
    (r'\b([Cc])ross\s+[Ee]xamination\b', r'\1ross-Examination'),
    (r'\b([Cc])ross\s+-\s+[Ee]xamination\b', r'\1ross-Examination'),

    # ── "Alright" → "All right" (UFM + Morson's English Guide) ──────────────
    # UFM and Morson's both require two words. Deepgram outputs "alright".
    (r'\balright\b', 'all right'),

    # ── Date ordinal suffixes removed in testimony context ────────────────────
    # UFM: "April 17" not "April 17th" in Q/A body text.
    (r'\b((?:January|February|March|April|May|June|July|August'
     r'|September|October|November|December)\s+\d{1,2})(st|nd|rd|th)\b',
     r'\1'),

    # ── "%" → "percent" in testimony context ─────────────────────────────────
    # UFM: spell out "percent" in Q/A body text.
    # Negative lookbehind prevents firing inside Bates numbers like "EXH-100%"
    # (those will not appear in testimony text, but guard anyway).
    (r'(?<![A-Z\-])(\d+\.?\d*)\s*%', r'\1 percent'),
]


# ── Deepgram artifact duplicate (Priority 5 — Spec 2.2) ──────────────────────
ARTIFACT_DUPLICATE_RE = re.compile(r'\b(\w{4,})\s+\1\b', re.IGNORECASE)
# Morson's Rule 157: spaced single letters → hyphenated
# Matches 3+ consecutive single letters separated by spaces.
# Requires word boundary at start and end.
# Multi-letter words break the sequence — only single chars match.
# Letters followed by periods are not matched (protects Q. A. initials).
SPELLED_LETTERS_RE = re.compile(
    r'\b([A-Za-z](?:\s+[A-Za-z]){2,})\b'
)


# ── Case-preservation helper ──────────────────────────────────────────────────

def _preserve_case(original_word: str, replacement: str) -> str:
    """Return replacement in ALL CAPS if original was ALL CAPS."""
    if original_word.isupper():
        return replacement.upper()
    return replacement


# ── Step 1: Multi-word corrections ───────────────────────────────────────────

def apply_multiword_corrections(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    for pattern, replacement in MULTIWORD_CORRECTIONS:
        new_text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        if new_text != text:
            records.append(CorrectionRecord(
                original=text, corrected=new_text,
                pattern=pattern, block_index=block_index,
            ))
            text = new_text
    return text


# ── Step 2: Case-specific corrections ────────────────────────────────────────

def apply_case_corrections(
    text: str,
    job_config: JobConfig,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    if isinstance(job_config, dict):
        confirmed_spellings = job_config.get("confirmed_spellings", {}) or {}
    else:
        confirmed_spellings = getattr(job_config, "confirmed_spellings", {}) or {}
    if not isinstance(confirmed_spellings, dict):
        confirmed_spellings = {}

    for wrong, correct in confirmed_spellings.items():
        pattern = r'\b' + re.escape(wrong) + r'\b'

        def _replace_with_case(m: re.Match, _correct: str = correct) -> str:
            return _preserve_case(m.group(0), _correct)

        new_text = re.sub(pattern, _replace_with_case, text, flags=re.IGNORECASE)
        if new_text != text:
            records.append(CorrectionRecord(
                original=wrong, corrected=correct,
                pattern=f"confirmed_spelling:{wrong}",
                block_index=block_index,
            ))
            text = new_text
    return text


# ── Step 3: Universal corrections ────────────────────────────────────────────

def apply_universal_corrections(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    new_text = ARTIFACT_ZIP_78216_RE.sub('', text)
    if new_text != text:
        records.append(CorrectionRecord(
            original=text,
            corrected=new_text,
            pattern='artifact_zip_78216_scoped',
            block_index=block_index,
        ))
        text = new_text

    for pattern, replacement in UNIVERSAL_CORRECTIONS:
        new_text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        if new_text != text:
            records.append(CorrectionRecord(
                original=text, corrected=new_text,
                pattern=pattern, block_index=block_index,
            ))
            text = new_text
    return text


# ── Step 4a: Number-to-word (mid-sentence count context) ─────────────────────

def apply_number_to_word(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Convert digits 1-10 to words in mid-sentence count context.
    Spec Section 2.3: skip dates, times, dollar amounts, exhibit numbers, addresses.
    """
    def _replace(m: re.Match) -> str:
        start, end = m.span()
        window_start = max(0, start - 8)
        window_end = min(len(text), end + 8)
        if NUMBER_EXCLUSION_RE.search(text[window_start:window_end]):
            return m.group(1)
        return NUMBER_WORD_MAP.get(m.group(1), m.group(1))

    new_text = COUNT_RE.sub(_replace, text)
    if new_text != text:
        records.append(CorrectionRecord(
            original=text, corrected=new_text,
            pattern='number_to_word_1_10', block_index=block_index,
        ))
    return new_text


# ── Step 4b: Date mashup flagging ────────────────────────────────────────────

_MONTH_WORDS = (
    'january|february|march|april|may|june|july|august|'
    'september|october|november|december'
)
DATE_MASHUP_RE = re.compile(
    r'\b(?:' + _MONTH_WORDS + r')\s+\w+\s+(?:twenty|thirty|two thousand)',
    re.IGNORECASE,
)

SAN_NAME_FLAG_RE = re.compile(
    r'^\s*San\s+(?!Antonio\b|Diego\b|Marcos\b|Jose\b|Juan\b|Angelo\b|Francisco\b'
    r'|Benito\b|Elizario\b|Saba\b|Isidro\b|Patricio\b|Ygnacio\b|Augustine\b)'
    r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b'
)
COUNT_RE = re.compile(r'\b([1-9]|10)\b(?=\s+[a-zA-Z])')
ARTIFACT_ZIP_78216_RE = re.compile(r'(?<!Texas\s)\b78216\b', re.IGNORECASE)


def apply_date_normalization(
    text: str,
    records: List[CorrectionRecord],
    flags: List[ScopistFlag],
    block_index: int,
    flag_counter: List[int],
) -> str:
    """Flag date mashups for scopist review. Always flags, never auto-corrects."""
    if DATE_MASHUP_RE.search(text):
        flag_counter[0] += 1
        n = flag_counter[0]
        flag_text = (
            f'[SCOPIST: FLAG {n}: Date "{text[:60]}" — '
            f'verify from audio/report. Used assumed date.]'
        )
        flags.append(ScopistFlag(
            number=n,
            description=f'Date unclear: "{text[:60]}" — verify.',
            block_index=block_index,
            category='date',
            inline_text=flag_text,
        ))
        records.append(CorrectionRecord(
            original=text, corrected=text,
            pattern='date_mashup_flag', block_index=block_index,
        ))
    return text


def apply_san_name_flag(
    text: str,
    records: List[CorrectionRecord],
    flags: List[ScopistFlag],
    block_index: int,
    flag_counter: List[int],
) -> str:
    """Flag likely 'San' misrecognitions at the start of a block for review."""
    if SAN_NAME_FLAG_RE.search(text):
        flag_counter[0] += 1
        n = flag_counter[0]
        flag_text = (
            f'[SCOPIST: FLAG {n}: "{text[:60]}" — verify whether initial '
            f'"San" is a misrecognized conjunction.]'
        )
        flags.append(ScopistFlag(
            number=n,
            description=f'Possible "San" artifact: "{text[:60]}"',
            block_index=block_index,
            category='artifact',
            inline_text=flag_text,
        ))
        records.append(CorrectionRecord(
            original=text, corrected=text,
            pattern='san_name_flag', block_index=block_index,
        ))
    return text


# ── Step 4c: Numbers at sentence start spelled out (Morson's English Guide) ──

def apply_sentence_start_number(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Step 4c: Spell out digits 1-10 when they appear at the VERY START of a block.
    Per Morson's English Guide for Court Reporters:
    Any number beginning a sentence must be spelled out as a word.

    Examples:
      "3 witnesses saw the crash" → "Three witnesses saw the crash"
      "10 years ago"             → "Ten years ago"

    Exceptions (do NOT convert):
      - Exhibit 3 (exclude context)
      - Times like 3:00 p.m.
      - Dollar amounts $3
    """
    match = SENTENCE_START_NUM_RE.search(text)
    if not match:
        return text
    start, end = match.span()
    window_start = max(0, start - 8)
    window_end = min(len(text), end + 8)
    if NUMBER_EXCLUSION_RE.search(text[window_start:window_end]):
        return text

    new_text = SENTENCE_START_NUM_RE.sub(
        lambda m: SENTENCE_START_NUMBER_WORDS.get(m.group(1), m.group(1)),
        text,
        count=1,
    )
    if new_text != text:
        records.append(CorrectionRecord(
            original=text, corrected=new_text,
            pattern='sentence_start_number_morson',
            block_index=block_index,
        ))
    return new_text


# ── Step 5: Deepgram artifact removal ────────────────────────────────────────

def apply_artifact_removal(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Spec 2.2: Remove Deepgram duplicate artifacts.
    ONLY 4+ character words are collapsed.
    Verbatim words and affirmation words are NEVER auto-removed.
    """
    def _replace_duplicate(match: re.Match) -> str:
        word = match.group(1)
        w_lower = word.lower()
        if w_lower in VERBATIM_PROTECTED:
            return match.group(0)
        if w_lower in AFFIRMATION_PROTECTED:
            return match.group(0)
        return word

    new_text = ARTIFACT_DUPLICATE_RE.sub(_replace_duplicate, text)
    if new_text != text:
        records.append(CorrectionRecord(
            original=text, corrected=new_text,
            pattern='artifact_duplicate_4plus', block_index=block_index,
        ))
    return new_text


def apply_spelled_letter_hyphenation(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Join space-separated single letters with hyphens.
    Morson's Rule 157: spelled letters use hyphens between them.

    VERBATIM RULE: Letters are never changed or collapsed.
    Only spaces between single letters become hyphens.

    Examples:
      B r e n n e n     → B-r-e-n-n-e-n
      B A L D E R A S   → B-A-L-D-E-R-A-S
      T O V A R         → T-O-V-A-R

    Guards:
      - Requires 3+ consecutive single letters
      - Letters followed by periods are excluded (Q. A. initials)
      - Multi-letter words break the sequence
    """
    original = text

    def _hyphenate(m: re.Match) -> str:
        return '-'.join(m.group(0).split())

    new_text = SPELLED_LETTERS_RE.sub(_hyphenate, text)

    if new_text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=new_text,
            pattern='spelled_letter_hyphenation_rule157',
            block_index=block_index,
        ))
    return new_text


# ── Steps 6-7: Cleanup ────────────────────────────────────────────────────────

def fix_spaced_dashes(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Ensure exactly one space before and after every double-hyphen dash.

    Morson's English Guide requires: word -- word
    (not word-- or --word or word--word)

    This runs AFTER normalize_time_and_dashes() which converts em/en dashes.
    This function handles any remaining closed -- that still lack spaces.

    Examples:
      he--stopped         → he -- stopped
      I went--I drove     → I went -- I drove
      he -- stopped       → unchanged (already correct)
      9:15 a.m.--9:30     → 9:15 a.m. -- 9:30
    """
    original = text
    text = re.sub(r'(?<! )--(?! )', ' -- ', text)
    text = re.sub(r' {2,}--', ' --', text)
    text = re.sub(r'-- {2,}', '-- ', text)
    if text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=text,
            pattern='fix_spaced_dashes',
            block_index=block_index,
        ))
    return text


def fix_uh_huh_hyphenation(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Normalize un-hyphenated affirmation/negation forms to hyphenated.

    Morson's Rule 4 requires: Uh-huh (affirmation), Uh-uh (negation)
    — strictly hyphenated.

    Deepgram frequently outputs these without the hyphen:
      uh huh  → Uh-huh
      uh uh   → Uh-uh
      mm hmm  → Mm-hmm  (also handled for completeness)

    VERBATIM RULE: These are preserved — the hyphenation fix is purely
    typographic, not a word change. The spoken sound is the same.

    Examples:
      uh huh. Yes.  → Uh-huh.  Yes.
      uh uh. No.    → Uh-uh.  No.
      Uh-huh.       → unchanged (already correct)
    """
    original = text
    text = re.sub(r'\buh\s+huh\b', 'Uh-huh', text, flags=re.IGNORECASE)
    text = re.sub(r'\buh\s+uh\b', 'Uh-uh', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmm\s+hmm\b', 'Mm-hmm', text, flags=re.IGNORECASE)
    if text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=text,
            pattern='fix_uh_huh_hyphenation',
            block_index=block_index,
        ))
    return text


def fix_even_dollar_amounts(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Remove trailing .00 from even dollar amounts.

    Morson's / Depo-Pro rule: $450.00 → $450
    Rationale: trailing zeros are visually noisy and risk being misread as
    additional digits in low-resolution printouts.

    Only fires on amounts ending in exactly .00 — not .50, .25, etc.

    Examples:
      $450.00   → $450
      $1,200.00 → $1,200
      $4.50     → $4.50     (unchanged — non-zero cents preserved)
      $350      → $350      (unchanged — already no decimals)
    """
    original = text
    text = re.sub(r'\$(\d[\d,]*?)\.00\b', r'$\1', text)
    if text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=text,
            pattern='fix_even_dollar_amounts',
            block_index=block_index,
        ))
    return text


def fix_conversational_titles(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Correct informal spoken title references to proper abbreviated form.

    Morson's Rule 208 / Depo-Pro Rule 20:
      miss [Name]    → Ms. [Name]
      missus [Name]  → Mrs. [Name]
      mister [Name]  → Mr. [Name]

    Applies only when the informal title immediately precedes a capitalized name
    or a known title word. Does NOT change already-correct forms (Ms., Mrs., Mr.)
    Does NOT change lowercase 'the miss' or 'a mister' (descriptive, not title).

    Examples:
      miss Ozuna         → Ms. Ozuna
      mister Garcia      → Mr. Garcia
      missus Rodriguez   → Mrs. Rodriguez
      Ms. Ozuna          → unchanged (already correct)
      the miss           → unchanged (not a title before a name)
    """
    original = text
    text = re.sub(r'\b(?i:miss)\s+(?=[A-Z])', 'Ms. ', text)
    text = re.sub(r'\b(?i:missus)\s+(?=[A-Z])', 'Mrs. ', text)
    text = re.sub(r'\b(?i:mister)\s+(?=[A-Z])', 'Mr. ', text)
    if text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=text,
            pattern='fix_conversational_titles',
            block_index=block_index,
        ))
    return text


def normalize_spaces(text: str) -> str:
    return re.sub(r' {2,}', ' ', text).strip()


def capitalize_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def enforce_terminal_punctuation(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Ensure every Q or A block ends with sentence-ending punctuation.

    Rules applied:
      1. "Okay," at end of block → "Okay." (transition comma → period)
      2. Bare "Okay" at end of block with no punctuation → "Okay."
      3. Any block ending without .?! → append period
         (Does NOT fire on blocks ending with "--" — interrupted speech)

    Verbatim rule: uh/um are never touched here or anywhere.
    """
    original = text
    stripped = text.rstrip()

    # Rule 1: "Okay," → "Okay." at end of block
    if stripped.endswith('Okay,'):
        text = stripped[:-len('Okay,')] + 'Okay.'
        stripped = text.rstrip()

    # Rule 2: Bare "Okay" with no punctuation at end
    if re.search(r'\bOkay\s*$', stripped):
        text = re.sub(r'\bOkay\s*$', 'Okay.', stripped)
        stripped = text.rstrip()

    # Rule 3: No terminal punctuation — append period
    # Exceptions:
    #   - interrupted speech ending with "--"
    #   - interrupted/stuttered starts like "I--I don't know"
    if (
        stripped
        and stripped[-1] not in '.?!'
        and not stripped.endswith('--')
        and not re.search(r'\b\w+--\w+', stripped)
    ):
        text = stripped + '.'

    if text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=text,
            pattern='terminal_punctuation',
            block_index=block_index,
        ))
    return text


def enforce_direct_address_comma(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Insert a comma after direct address openers when one is missing.

    Covered patterns (UFM §2.8 and Morson's English Guide):
      "Yes sir"      → "Yes, sir."
      "No sir"       → "No, sir."
      "Yes ma'am"    → "Yes, ma'am."
      "No ma'am"     → "No, ma'am."
      "Yes Counsel"  → "Yes, Counsel."
      "All right Counsel" → "All right, Counsel."

    Does NOT fire when a comma is already present.
    Does NOT fire on "All right" when followed by a lowercase word
    (that is a conjunction, not a direct address).
    """
    original = text

    # Yes/No + title — requires no existing comma
    text = re.sub(
        r'\b(Yes|No)\s+(sir|ma\'am|counsel|Counsel)\b(?!,)',
        r'\1, \2',
        text,
        flags=re.IGNORECASE,
    )

    # "All right" + capitalized title — no existing comma
    text = re.sub(
        r'\bAll right\s+([A-Z][a-z]+)\b',
        r'All right, \1',
        text,
    )

    if text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=text,
            pattern='direct_address_comma',
            block_index=block_index,
        ))
    return text


def normalize_sentence_spacing(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    """
    Enforce the two-space rule after sentence-ending punctuation inside a block.
    """
    if re.fullmatch(r"Objection\.\s+Form\.\.?", text, flags=re.IGNORECASE):
        return "Objection. Form."

    _ELLIPSIS_TOK = "\x00ELLIPSIS\x00"
    working = text.replace(". . .", _ELLIPSIS_TOK)

    _ABBR_RE = re.compile(
        r'\b(?:Dr|Mr|Mrs|Ms|Jr|Sr|St|Lt|Sgt|Cpl|Pvt|Prof|Rev|Gen|Col|Maj|Capt'
        r'|vs|etc|No|Vol|approx|est|dept|Inc|Corp|Ltd|LLC|PLLC'
        r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec'
        r'|a\.m|p\.m)\.',
        re.IGNORECASE,
    )
    abbr_tokens: list[tuple[str, str]] = []

    def _tok_abbr(m: re.Match) -> str:
        tok = f"\x01A{len(abbr_tokens)}\x01"
        abbr_tokens.append((tok, m.group(0)))
        return tok

    working = _ABBR_RE.sub(_tok_abbr, working)

    new_text = re.sub(
        r'(?<!\.)(([.!?])(?:["\')\]]*)?)[ \t]+(?=[A-Z(\["\'])',
        lambda m: f"{m.group(1)}  ",
        working,
    )
    new_text = re.sub(r'([.!?])[ \t]{3,}([A-Z])', r'\1  \2', new_text)
    for tok, original in abbr_tokens:
        new_text = new_text.replace(tok, original)
    new_text = new_text.replace(_ELLIPSIS_TOK, ". . .")
    if new_text != text:
        records.append(CorrectionRecord(
            original=text,
            corrected=new_text,
            pattern='sentence_spacing_two_spaces',
            block_index=block_index,
        ))
    return new_text


def normalize_time_and_dashes(
    text: str,
    records: List[CorrectionRecord],
    block_index: int,
) -> str:
    original = text
    text = re.sub(r"[—–]+", "--", text)
    text = re.sub(r"\s*---\s*", " -- ", text)

    def _fix_time(match: re.Match) -> str:
        time_text = match.group(1)
        hour, minute = time_text.split(":", 1)
        normalized_time = f"{int(hour)}:{minute}"
        period = match.group(2).lower()
        dotted = "a.m." if period == "am" else "p.m."
        return f"{normalized_time} {dotted}"

    text = TIME_RE.sub(_fix_time, text)
    if text != original:
        records.append(CorrectionRecord(
            original=original,
            corrected=text,
            pattern='time_dash_normalization',
            block_index=block_index,
        ))
    return text


# ── Master correction function ────────────────────────────────────────────────

def clean_block(
    text: str,
    job_config: JobConfig,
    block_index: int = 0,
    flags: Optional[List[ScopistFlag]] = None,
    flag_counter: Optional[List[int]] = None,  # mutable [int] box shared across calls
) -> Tuple[str, List[CorrectionRecord], List[ScopistFlag]]:
    """
    Master correction function. Apply all corrections in reference doc order.

    CORRECTION ORDER (MUST NOT CHANGE):
      1.  Multi-word phrase standardization
      2.  Case-specific proper noun corrections (confirmed_spellings)
      3.  Universal single-word corrections
      4a. Number-to-word (mid-sentence count context)
      4b. Date mashup flagging
      4c. Sentence-start number spelled out (Morson's English Guide)
      5.  Deepgram duplicate artifact removal (4+ char words only)
      5b. Spelled-letter hyphenation (Morson's Rule 157)
      6.  Spaced dashes (word--word → word -- word)
      7.  Uh-huh / Uh-uh hyphenation normalization
      8.  Even dollar amount cleanup ($450.00 → $450)
      9.  Conversational titles (miss → Ms., mister → Mr.)
      10. Space normalization (MUST run before two-space rule)
      11. Capitalize first character
      12. Direct address comma insertion
      13. Terminal punctuation enforcement
      14. Two-space rule after sentence-ending punctuation (RUNS LAST)
      -- uh/um: NEVER touched — verbatim rule is absolute
    """
    if flags is None:
        flags = []
    if flag_counter is None:
        flag_counter = [0]

    records: List[CorrectionRecord] = []

    _before = text  # snapshot for block-level summary log

    text = apply_multiword_corrections(text, records, block_index)
    text = apply_case_corrections(text, job_config, records, block_index)
    text = apply_universal_corrections(text, records, block_index)
    text = normalize_time_and_dashes(text, records, block_index)
    text = apply_number_to_word(text, records, block_index)
    text = apply_date_normalization(text, records, flags, block_index, flag_counter)
    text = apply_san_name_flag(text, records, flags, block_index, flag_counter)
    text = apply_sentence_start_number(text, records, block_index)
    text = apply_artifact_removal(text, records, block_index)
    text = apply_spelled_letter_hyphenation(text, records, block_index)
    text = fix_spaced_dashes(text, records, block_index)
    text = fix_uh_huh_hyphenation(text, records, block_index)
    text = fix_even_dollar_amounts(text, records, block_index)
    text = fix_conversational_titles(text, records, block_index)
    text = normalize_spaces(text)
    text = capitalize_first(text)
    text = enforce_direct_address_comma(text, records, block_index)
    text = enforce_terminal_punctuation(text, records, block_index)
    text = normalize_sentence_spacing(text, records, block_index)
    # Step 8: uh/um — NEVER touched. No code here intentionally.

    # ── Block-level debug log (off by default — enable with DEBUG level) ─────
    if records and logger.isEnabledFor(logging.DEBUG):
        rule_names = sorted({r.pattern.split(":")[0] for r in records})
        logger.debug(
            "[corrections] block %d: %d correction(s) fired  rules=%s\n"
            "  before: %r\n  after:  %r",
            block_index, len(records), rule_names, _before[:80], text[:80],
        )

    return text, records, list(flags)


def apply_corrections(blocks: List[Block], job_config: JobConfig | dict) -> List[Block]:
    """
    Apply deterministic corrections to structured blocks in-place.

    Also deduplicates consecutive verbatim duplicate blocks, which Deepgram
    occasionally produces from overlapping audio chunks or echo artifacts.
    """
    corrected_blocks: List[Block] = []
    flags: List[ScopistFlag] = []
    flag_counter = [0]
    change_count = 0
    prev_cleaned: str = ""
    prev_speaker: Optional[int] = None

    for index, block in enumerate(blocks):
        result = clean_block(
            block.text,
            job_config,  # type: ignore[arg-type]
            block_index=index,
            flags=flags,
            flag_counter=flag_counter,
        )
        cleaned_text = result[0]
        records = result[1]

        # ── Consecutive duplicate block detection ─────────────────────────────
        # Skip this block if its cleaned text is identical to the previous
        # block AND they share the same speaker. Only applies to blocks of
        # 15+ characters to avoid false positives on short responses like "Yes."
        if (
            len(cleaned_text.strip()) >= 15
            and cleaned_text.strip() == prev_cleaned.strip()
            and block.speaker_id == prev_speaker
        ):
            logging.getLogger(__name__).debug(
                "apply_corrections: skipping duplicate block %d: %r",
                index, cleaned_text[:60],
            )
            continue

        if cleaned_text.strip():
            prev_cleaned = cleaned_text.strip()
            prev_speaker = block.speaker_id

        if cleaned_text != block.text:
            change_count += 1
        corrected_blocks.append(
            Block(
                raw_text=block.raw_text,
                text=cleaned_text,
                speaker_id=block.speaker_id,
                speaker_name=block.speaker_name,
                speaker_role=block.speaker_role,
                block_type=block.block_type,
                words=list(block.words),
                flags=list(block.flags),
                meta={**block.meta, "corrections": records},
            )
        )

    logging.getLogger(__name__).info(
        "apply_corrections: %d/%d blocks modified  |  %d duplicates skipped",
        change_count,
        len(corrected_blocks),
        len(blocks) - len(corrected_blocks),
    )
    return corrected_blocks
