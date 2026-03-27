"""
corrections.py

All text correction rules from DepoPro Spec Section 2.
Applied in exact priority order from Spec Section 9.4.

PRIORITY ORDER (MUST NOT CHANGE):
  1. Multi-word name phrases
  2. Case-specific proper noun corrections (from confirmed_spellings)
  3. Universal proper noun corrections (Doctor. → Dr., subpoena variants, etc.)
  4a. Number-to-word in count context (1-10)
  4b. Date mashup flagging
  4c. Numbers at sentence start spelled out (Morson's English Guide)
  5. Deepgram artifact removal (doubled words — 4+ chars only)
  6. Normalize spaces
  7. Capitalize first character
  8. NEVER remove uh/um — verbatim rule is absolute

VERBATIM RULE: "uh" and "um" are NEVER removed. This is enforced by unit tests.
MORSON'S RULE: Numbers 1-10 at sentence start must be spelled out as words.
MORSON'S RULE 270: Ellipsis in any form (. . .) is never touched.
"""

import re
import logging
from typing import List, Optional, Tuple

from .models import Block, CorrectionRecord, JobConfig, ScopistFlag


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
    r'[Ee]xhibit\s+\d'      # Exhibit 3
    r'|\d{1,2}:\d{2}'       # time (2:30)
    r'|\$\s*\d'             # dollar amount
    r'|\d{3,}'              # address or long number (123 Main)
    r'|\d[/\-]\d'           # date fraction (4/17) or range
    r')',
)

# Sentence start: digit 1-10 as the FIRST token in the block
SENTENCE_START_NUM_RE = re.compile(
    r'^([1-9]|10)\b(?!\s*(?:a\.m|p\.m|\d|:))'
)


# ── Verbatim-protected words (Spec Section 2.1) ───────────────────────────────
VERBATIM_PROTECTED = {'okay', 'well'}

# Affirmation words preserved per Spec 9.6 unit test
# "correct correct" must remain — common witness affirmation pattern
AFFIRMATION_PROTECTED = {'correct', 'right', 'exactly', 'absolutely', 'definitely'}


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

    # Cross-examination hyphen (Spec Section 4.1)
    (r'\b([Cc])ross\s+[Ee]xamination\b', r'\1ross-Examination'),
    (r'\b([Cc])ross\s+-\s+[Ee]xamination\b', r'\1ross-Examination'),
]


# ── Deepgram artifact duplicate (Priority 5 — Spec 2.2) ──────────────────────
ARTIFACT_DUPLICATE_RE = re.compile(r'\b(\w{4,})\s+\1\b', re.IGNORECASE)


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


# ── Steps 6-7: Cleanup ────────────────────────────────────────────────────────

def normalize_spaces(text: str) -> str:
    return re.sub(r' {2,}', ' ', text).strip()


def capitalize_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


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
    Master correction function. Apply all corrections in Spec 9.4 order.

    CORRECTION ORDER (MUST NOT CHANGE):
      1. Multi-word name phrases
      2. Case-specific proper noun corrections
      3. Universal proper noun corrections
      4a. Number-to-word (mid-sentence count context)
      4b. Date mashup flagging
      4c. Numbers at sentence start spelled out (Morson's English Guide)
      5. Deepgram artifact removal (4+ char duplicates only)
      6. Normalize spaces
      7. Capitalize first character
      8. uh/um — NEVER touched
    """
    if flags is None:
        flags = []
    if flag_counter is None:
        flag_counter = [0]

    records: List[CorrectionRecord] = []

    text = apply_multiword_corrections(text, records, block_index)
    text = apply_case_corrections(text, job_config, records, block_index)
    text = apply_universal_corrections(text, records, block_index)
    text = normalize_time_and_dashes(text, records, block_index)
    text = apply_number_to_word(text, records, block_index)
    text = apply_date_normalization(text, records, flags, block_index, flag_counter)
    text = apply_san_name_flag(text, records, flags, block_index, flag_counter)
    text = apply_sentence_start_number(text, records, block_index)
    text = apply_artifact_removal(text, records, block_index)
    text = normalize_spaces(text)
    text = capitalize_first(text)
    text = normalize_sentence_spacing(text, records, block_index)
    # Step 8: uh/um — NEVER touched. No code here intentionally.

    return text, records, list(flags)


def apply_corrections(blocks: List[Block], job_config: JobConfig | dict) -> List[Block]:
    """
    Apply deterministic corrections to structured blocks in-place.
    """
    corrected_blocks: List[Block] = []
    flags: List[ScopistFlag] = []
    flag_counter = [0]
    change_count = 0

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
        "apply_corrections: %d/%d blocks modified",
        change_count,
        len(corrected_blocks),
    )
    return corrected_blocks
