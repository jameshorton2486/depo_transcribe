"""
classifier.py

Classifies each Block into one or more (LineType, text) pairs for emission.
Spec Section 4: Examination Structure

MORSON'S COMPLIANCE (Morson's English Guide for Court Reporters):
  - THE REPORTER: label used throughout (not THE COURT REPORTER:)
    Reason: formatter.py normalizes this in the text path, but spec_engine
    writes directly to DOCX and must use the correct label from the start.
  - Objections preserved verbatim as spoken — no auto-rewrite to "Objection to form."
    Reason: Morson's requires objections as separate sentence fragments, exactly spoken.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .models import (
    Block, BlockType, JobConfig, LineType, ScopistFlag, PostRecordSpelling,
    SpeakerMapUnverifiedError,
)
from .pages.post_record import derive_correct_spelling
from .speaker_resolver import ROLE_ATTORNEY, ROLE_EXAMINING_ATTORNEY, ROLE_INTERPRETER, ROLE_OPPOSING_COUNSEL, ROLE_REPORTER, ROLE_VIDEOGRAPHER, ROLE_WITNESS


__all__ = [
    "ClassifierState",
    "classify_block",
    "classify_blocks",
    "split_correct_mid",
    "fix_trailing_okay_in_answer",
    "flag_name_unverified",
    "flag_witness_conflict",
    "flag_date_uncertain",
    "flag_exhibit_unclear",
    "flag_caption_discrepancy",
    "flag_post_record_spelling",
]


# ── Module logger ─────────────────────────────────────────────────────────────
logger = logging.getLogger("spec_engine.classifier")


# ── Tunable thresholds (named to match assertions in test_ui_invariants.py) ──
# Word-count ceiling above which a short utterance is no longer treated as
# pre-record chatter (greetings, mic checks). Anything longer is assumed to be
# substantive and is preserved.
MAX_PRE_RECORD_WORD_COUNT = 12
# Word-count ceiling for a generic short utterance to be treated as a witness
# answer when it appears after a Q line.
MAX_GENERIC_ANSWER_WORDS = 12
# Word-count ceiling specifically for blocks already labeled as attorney that
# we are willing to re-route as an answer (diarization-failure rescue).
MAX_ATTORNEY_LABEL_ANSWER_WORDS = 6
# Length of the text sample included in a SCOPIST flag when an unmapped
# speaker ID is encountered.
SPEAKER_FLAG_SAMPLE_LEN = 60


# ── Objection detection (Morson's: preserve as spoken) ────────────────────────
# We detect objections to classify them as SP lines, but do NOT rewrite
# the spoken text. Only ensure terminal punctuation is present.
OBJECTION_START_RE = re.compile(r'^[Oo]bject(?:ion)?', re.IGNORECASE)

# ── Record status patterns (Spec Section 4.4) ─────────────────────────────────
OFF_RECORD_RE  = re.compile(r'off\s+the\s+record',       re.IGNORECASE)
ON_RECORD_RE   = re.compile(r'back\s+on\s+the\s+record', re.IGNORECASE)
# ── First on-record markers — start of legal deposition record ────────────────
# These patterns identify the moment the videographer or reporter opens
# the formal record. Everything BEFORE the first match is pre-record chatter
# and must be excluded from the certified transcript.
FIRST_ON_RECORD_PATTERNS = [
    re.compile(r'\bwe\s+are\s+on\s+the\s+record\b',                    re.IGNORECASE),
    re.compile(r'\brecording\s+in\s+progress\b',                        re.IGNORECASE),
    re.compile(r'\bthis\s+is\s+the\s+beginning\s+of\s+the\s+deposition\b', re.IGNORECASE),
    re.compile(r"\btoday'?s\s+date\s+is\s+\d{1,2}/\d{1,2}/\d{4}\b",  re.IGNORECASE),
    re.compile(r'\bthe\s+time\s+is\s+\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?|AM|PM)\b', re.IGNORECASE),
]
PRE_RECORD_KEYWORDS = [
    'good morning', 'good afternoon', 'good evening',
    'can you hear me', 'testing one two', 'check one two',
    'volume check', 'lighting', 'hold on', 'just a second',
    'everyone ready',
]
# Pre-compiled keyword regexes — built once at import time so that
# _is_pre_record_chatter() does not re-compile per keyword per block.
_PRE_RECORD_KEYWORD_RES = [
    re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE)
    for keyword in PRE_RECORD_KEYWORDS
]

def _is_pre_record_chatter(text: str) -> bool:
    sanitized = (text or "").strip()
    if not sanitized:
        return True
    upper = sanitized.upper()
    for prefix in ('Q.', 'A.', 'THE REPORTER', 'MR.', 'MS.', 'MRS.', 'DR.', 'SPEAKER'):
        if upper.startswith(prefix):
            return False
    if len(sanitized.split()) > MAX_PRE_RECORD_WORD_COUNT:
        return False
    lowered = sanitized.lower()
    for pattern in _PRE_RECORD_KEYWORD_RES:
        if pattern.search(lowered):
            return True
    return False
CONCLUDED_RE   = re.compile(r'deposition\s+(?:is\s+)?concluded', re.IGNORECASE)
TIME_RE        = re.compile(r'(\d{1,2}:\d{2})\s*(a\.?m\.?|p\.?m\.?|AM|PM)', re.IGNORECASE)

# ── Oath patterns (Spec Section 4.5) ─────────────────────────────────────────
OATH_RE = re.compile(
    r'raise\s+your\s+right\s+hand'
    r'|raise\s+your\s+(?:left\s+)?hand'
    r'|solemnly\s+swear'
    r'|solemnly\s+affirm'
    r'|do\s+you\s+(?:swear|affirm)\s+(?:to\s+)?tell\s+the\s+truth',
    re.IGNORECASE,
)

# ── Embedded answer starters (Spec Section 4.2) ───────────────────────────────
EMBEDDED_ANSWER_STARTERS = [
    # Affirm / deny
    'yes', 'no', 'correct', 'right', 'yeah', 'yep', 'yup', 'nope', 'nah',
    'mm-hmm', 'uh-huh', 'no, sir', 'yes, sir', "no, ma'am", "yes, ma'am",
    # First-person responses
    'i do', 'i do not', "i don't", 'i did', 'i did not',
    'i have', 'i have not', 'i would', 'i could', 'i could not',
    'i was not', 'i am not', 'i was', 'i will', 'i will not',
    'i believe', 'i think', 'i recall', 'i remember',
    "i don't know", "i don't recall", "i don't remember",
    # Group / third-person
    'we have', 'we did', 'we were', 'they would have',
    'there was not', 'there is not', 'there were not',
    # Professional context
    "that's correct", 'that is correct', 'not particularly', 'not necessarily',
    'not that i recall', 'sure', 'never', 'absolutely', 'definitely',
    # Medical / deposition context
    'fentanyl', 'in the ed', 'surgical issues',
]

ANSWER_TOKEN_RE = re.compile(
    r'(\?)\s{1,2}'
    r'(No\.|Yes\.|Correct\.|Right\.|Yeah\.|Yep\.|Yup\.|Nope\.|Nah\.'
    r'|Mm-hmm\.|Uh-huh\.|No,\s+sir\.|Yes,\s+sir\.|No,\s+ma\'am\.|Yes,\s+ma\'am\.'
    r'|I have\.|I have not\.|I do\.|I do not\.|I did\.|I did not\.'
    r'|I would\.|I could\.|I could not\.|I was not\.|I am not\.'
    r'|I recall\.|I remember\.|Sure\.|Never\.|That\'s correct\.|That is correct\.'
    r'|Not particularly\.|Not necessarily\.|Not that I recall\.'
    r'|We have\.|We did\.|We were\.|There was not\.|There is not\.'
    r'|They would have\.)',
    re.IGNORECASE
)

CORRECT_MID_RE = re.compile(
    r'(\.\s{1,2})(Correct\.)(\s{1,2}[A-Z])',
    re.IGNORECASE
)

TRAILING_OKAY_RE = re.compile(r'\s{1,2}Okay\.$')

# Sentence-boundary detector used inside _detect_embedded_answer. Pre-compiled
# so the regex isn't rebuilt on every embedded-answer split attempt.
_EMBEDDED_ANSWER_END_RE = re.compile(r'(?<=[.!?])\s+[A-Z]')

QUESTION_WORDS = ("who", "what", "when", "where", "why", "how", "did", "do", "does", "is", "are", "can", "could", "would", "will")
IMPERATIVE_QUESTION_STARTERS = ("state", "tell", "describe", "explain", "identify", "name")
QUESTION_LEAD_PHRASES = (
    "please state",
    "would you please",
    "could you please",
    "would you",
    "could you",
    "will you",
    "can you",
    "have you",
    "had you",
    "are you",
    "were you",
    "was there",
    "were there",
    "do you solemnly swear",
    "do you affirm",
)
REPORTER_ADMIN_MARKERS = (
    "for the record",
    "on the record",
    "off the record",
    "back on the record",
    "deposition",
    "counsel",
    "raise your right hand",
    "solemnly swear",
)
ATTORNEY_LABEL_MARKERS = ("MR.", "MS.", "MRS.", "DR.", "COUNSEL", "ATTORNEY")

# ── Post-record spelling pattern (Spec Section 8) ─────────────────────────────
SPELLING_RE = re.compile(
    r'(\w[\w\s]+?)\s+(?:is\s+)?(?:spelled|spelling)\s+([A-Z](?:-[A-Z]){2,})',
    re.IGNORECASE,
)

# ── Exhibit marking (Spec Section 3.3 Type 4) ─────────────────────────────────
EXHIBIT_RE = re.compile(
    r"(?:"
    r"marked"
    r"|handing(?:\s+you)?"
    r"|what'?s?\s+been\s+marked"
    r"|i\s+am\s+handing(?:\s+you)?"
    r")\s+(?:as\s+)?[Ee]xhibit\s+(?:No\.?\s*)?(\d+)",
    re.IGNORECASE,
)


# ── Flag factory functions (Spec Section 6.3) ─────────────────────────────────

def flag_name_unverified(n: int, deepgram_output: str, source: str) -> str:
    return f'[SCOPIST: FLAG {n}: "{deepgram_output}" — verify spelling from {source}]'


def flag_witness_conflict(n: int, witness_a: str, fact_a: str,
                          witness_b: str, fact_b: str) -> str:
    return (f'[SCOPIST: FLAG {n}: CONFLICT — {witness_a} states {fact_a}. '
            f'{witness_b} states {fact_b}. Verify from dashcam/recording.]')


def flag_date_uncertain(n: int, raw_output: str, assumed_date: str) -> str:
    return (f'[SCOPIST: FLAG {n}: Date "{raw_output}" — verify from audio/report. '
            f'Used {assumed_date}.]')


def flag_exhibit_unclear(n: int, exhibit_num: str) -> str:
    return (f'[SCOPIST: FLAG {n}: Exhibit {exhibit_num} description — '
            f'verify from reporter exhibit log.]')


def flag_caption_discrepancy(n: int, field: str, source_a: str, val_a: str,
                              source_b: str, val_b: str) -> str:
    return (f'[SCOPIST: FLAG {n}: {field} — {source_a} shows "{val_a}". '
            f'{source_b} shows "{val_b}". Used {val_a} per {source_a}.]')


def flag_post_record_spelling(n: int, name: str, letters: str) -> str:
    return (f'[SCOPIST: FLAG {n}: "{name}" — spelled on record as {letters}. '
            f'Confirm matches all prior uses.]')


# ── State tracker ─────────────────────────────────────────────────────────────

@dataclass
class ClassifierState:
    in_pre_record: bool = True
    current_examiner_id: Optional[int] = None
    in_post_record: bool = False
    examination_type: str = "EXAMINATION"
    flag_counter: int = 0
    flags: List[ScopistFlag] = field(default_factory=list)
    post_record_spellings: List[PostRecordSpelling] = field(default_factory=list)
    qa_tracker_last_was_q: bool = False

    def next_flag(self) -> int:
        self.flag_counter += 1
        return self.flag_counter

    def add_flag(self, description: str, block_index: int, category: str,
                 inline_text: str) -> ScopistFlag:
        n = self.next_flag()
        flag = ScopistFlag(
            number=n, description=description, block_index=block_index,
            category=category, inline_text=inline_text,
        )
        self.flags.append(flag)
        return flag


# ── JobConfig accessor helper ─────────────────────────────────────────────────
# JobConfig may arrive as either a dataclass-style object or a plain dict.
# Extract the dual-access pattern so each call site is a single line and the
# behavior stays identical to the original inline checks.

def _get_config_value(job_config, key: str, default=None):
    """Read a value from JobConfig (object) or dict, returning default if missing."""
    if job_config is None:
        return default
    if hasattr(job_config, key):
        return getattr(job_config, key, default)
    if isinstance(job_config, dict):
        return job_config.get(key, default)
    return default


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_time(text: str) -> Optional[str]:
    m = TIME_RE.search(text)
    if m:
        period = m.group(2).lower().strip()
        if '.' not in period:
            period = period[0] + '.' + period[1] + '.'
        return f"{m.group(1)} {period}"
    return None


def _detect_embedded_answer(
    text: str, job_config: JobConfig
) -> Optional[Tuple[str, str, Optional[str]]]:
    """
    Spec Section 4.2: Detect attorney block containing an embedded witness answer.
    Returns (question_text, answer_text, continuation_text) or None.
    """
    if not job_config.split_embedded_answers:
        return None

    match = ANSWER_TOKEN_RE.search(text)
    if match:
        question_part = text[:match.start(2)].strip()
        remainder = text[match.start(2):].strip()
        if not question_part or not remainder:
            return None

        end_match = _EMBEDDED_ANSWER_END_RE.search(remainder)
        if end_match:
            answer_part = remainder[:end_match.start()].strip()
            continuation = remainder[end_match.start():].strip()
            return question_part, answer_part, continuation or None
        return question_part, remainder, None

    q_pos = text.rfind('?')
    if q_pos == -1:
        return None
    question_part = text[:q_pos + 1].strip()
    remainder = text[q_pos + 1:].strip()
    if not remainder or remainder.rstrip().endswith('?'):
        return None
    r_lower = remainder.lower()
    for starter in EMBEDDED_ANSWER_STARTERS:
        if r_lower.startswith(starter):
            return question_part, remainder, None
    return None


def _sentence_time(time_str: Optional[str], fallback: str = "[time]") -> str:
    """Normalize a time string for sentence-final insertion."""
    return (time_str or fallback).rstrip(".")


def _looks_like_question_text(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    imperative_match = any(lowered.startswith(word + " ") for word in IMPERATIVE_QUESTION_STARTERS)
    if lowered.startswith("tell ") and not lowered.startswith(("tell me ", "tell us ", "tell the ")):
        imperative_match = False
    return (
        normalized.endswith("?")
        or any(lowered.startswith(word + " ") for word in QUESTION_WORDS)
        or imperative_match
        or any(lowered.startswith(phrase + " ") for phrase in QUESTION_LEAD_PHRASES)
    )


def _looks_like_answer_after_question(text: str, speaker_label_upper: str = "") -> bool:
    """
    Heuristic guard for diarization failures where the witness answer is
    misattributed immediately after a Q line.
    """
    normalized = (text or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered.endswith("?"):
        return False
    if any(marker in lowered for marker in REPORTER_ADMIN_MARKERS):
        return False
    if OBJECTION_START_RE.match(normalized):
        return False

    for starter in EMBEDDED_ANSWER_STARTERS:
        if lowered.startswith(starter):
            return True

    generic_answer_starts = (
        "it's ",
        "it is ",
        "i'm ",
        "i am ",
        "my ",
        "uh,",
        "um,",
        "sorry,",
        "sorry ",
        "currently ",
        "born ",
    )
    if lowered.startswith(generic_answer_starts):
        return True

    is_attorney_label = any(marker in (speaker_label_upper or "") for marker in ATTORNEY_LABEL_MARKERS)
    if is_attorney_label:
        return len(normalized.split()) <= MAX_ATTORNEY_LABEL_ANSWER_WORDS and any(
            lowered.startswith(starter) for starter in EMBEDDED_ANSWER_STARTERS
        )

    return len(normalized.split()) <= MAX_GENERIC_ANSWER_WORDS


def split_correct_mid(text: str) -> Optional[Tuple[str, str, str]]:
    """
    Detect 'Statement. Correct. New question' in Q paragraph text.
    Only fires when Correct. follows a period, never a question mark.
    """
    match = CORRECT_MID_RE.search(text)
    if not match:
        return None
    before = text[:match.start(2)].rstrip()
    continuation = text[match.end(2):].strip()
    return (before, 'Correct.', continuation)


def fix_trailing_okay_in_answer(blocks: list[Tuple[LineType, str]]) -> list[Tuple[LineType, str]]:
    """
    Strip trailing 'Okay.' from an answer and prepend it to the next Q.
    """
    result = list(blocks)
    i = 0
    while i < len(result):
        lt, text = result[i]
        if lt == LineType.A and TRAILING_OKAY_RE.search(text):
            clean = TRAILING_OKAY_RE.sub('', text).strip()
            result[i] = (LineType.A, clean)
            for j in range(i + 1, len(result)):
                next_lt, next_text = result[j]
                if next_lt == LineType.Q:
                    if not next_text.startswith('Okay.'):
                        result[j] = (LineType.Q, 'Okay. ' + next_text)
                    break
        i += 1
    return result


def _get_label(job_config, speaker_id: int) -> str:
    speaker_map = _get_config_value(job_config, "speaker_map", {}) or {}
    return speaker_map.get(speaker_id, f"SPEAKER {speaker_id}")


def classify_blocks(blocks: list[Block], job_config: JobConfig | dict | None = None) -> list[Block]:
    """
    Lightweight block classifier for the block-based pipeline.
    Priority:
      1. Speaker role
      2. Known structural patterns
      3. Punctuation and simple heuristics
      4. Previous-block context
    """
    examining_attorney_id = _get_config_value(job_config, "examining_attorney_id")

    if job_config is not None:
        _verified = _get_config_value(job_config, "speaker_map_verified", False)
        if not _verified:
            logger.warning(
                "classify_blocks() called with unverified speaker map. "
                "Speaker roles will use heuristics only. "
                "Call SpeakerVerifyDialog before final processing to ensure accurate output."
            )

    previous_type = BlockType.UNKNOWN
    for block in blocks:
        text = (block.text or "").strip()
        lower = text.lower()
        role = (block.speaker_name or "").upper().strip()
        resolved_role = (block.speaker_role or "").upper().strip()

        if not text:
            block.block_type = BlockType.UNKNOWN
            continue
        if text.startswith("(") and text.endswith(")"):
            block.block_type = BlockType.PARENTHETICAL
        elif OBJECTION_START_RE.match(text):
            block.block_type = BlockType.SPEAKER
        elif resolved_role == ROLE_WITNESS or "WITNESS" in role:
            if _looks_like_question_text(text):
                block.block_type = BlockType.QUESTION
            else:
                block.block_type = BlockType.ANSWER
        elif (
            resolved_role in (ROLE_REPORTER, ROLE_VIDEOGRAPHER, ROLE_INTERPRETER)
            or any(marker in role for marker in ("REPORTER", "VIDEOGRAPHER", "INTERPRETER"))
        ):
            if "VIDEOGRAPHER" in role or resolved_role == ROLE_VIDEOGRAPHER:
                block.block_type = BlockType.PARENTHETICAL
            else:
                block.block_type = BlockType.SPEAKER
        elif resolved_role in (ROLE_ATTORNEY, ROLE_EXAMINING_ATTORNEY, ROLE_OPPOSING_COUNSEL) or any(marker in role for marker in ("ATTORNEY", "COUNSEL", "MR.", "MS.", "MRS.", "DR.")):
            _is_examiner = resolved_role in (ROLE_EXAMINING_ATTORNEY, ROLE_ATTORNEY)
            _imperative_fires = (
                _is_examiner
                and any(lower.startswith(word + " ") for word in IMPERATIVE_QUESTION_STARTERS)
            )
            _attorney_label_answer = (
                previous_type == BlockType.QUESTION
                and block.speaker_id != examining_attorney_id
                and _looks_like_answer_after_question(text, role)
            )
            if _attorney_label_answer:
                block.block_type = BlockType.ANSWER
            elif _looks_like_question_text(text) or _imperative_fires:
                block.block_type = BlockType.QUESTION
            else:
                block.block_type = BlockType.COLLOQUY
        elif _looks_like_question_text(text):
            block.block_type = BlockType.QUESTION
        elif any(lower.startswith(token) for token in EMBEDDED_ANSWER_STARTERS):
            block.block_type = BlockType.ANSWER
        elif (
            previous_type == BlockType.QUESTION
            and resolved_role not in (
                ROLE_ATTORNEY,
                ROLE_EXAMINING_ATTORNEY,
                ROLE_OPPOSING_COUNSEL,
                ROLE_REPORTER,
                ROLE_VIDEOGRAPHER,
                ROLE_INTERPRETER,
            )
            and not any(
                marker in role for marker in (
                    "ATTORNEY", "COUNSEL", "MR.", "MS.", "MRS.", "DR.",
                    "REPORTER", "VIDEOGRAPHER", "INTERPRETER",
                )
            )
        ):
            block.block_type = BlockType.ANSWER
        else:
            if "VIDEOGRAPHER" in role:
                block.block_type = BlockType.PARENTHETICAL
            else:
                block.block_type = BlockType.UNKNOWN

        previous_type = block.block_type
    return blocks


# ── Main classification function ──────────────────────────────────────────────

def classify_block(
    block: Block,
    job_config: JobConfig,
    state: ClassifierState,
    block_index: int,
) -> List[Tuple[LineType, str]]:
    """
    Classify one block into one or more (LineType, text) pairs.
    Spec Section 4: Examination Structure.
    Morson's: THE REPORTER: label, objections preserved as spoken.
    """
    if not job_config.speaker_map_verified:
        raise SpeakerMapUnverifiedError(
            "Speaker map has not been verified. "
            "Use the Speaker Verification dialog before processing."
        )

    results: List[Tuple[LineType, str]] = []
    text = block.text
    sid  = block.speaker_id
    speaker_label = _get_label(job_config, sid)
    speaker_label_upper = speaker_label.upper()

    # ── Pre-record filter — discard everything before the legal record opens ──
    # All content before the videographer's "we are on the record" statement
    # is off-record Zoom/Teams setup chatter and must be excluded.
    if state.in_pre_record:
        for pattern in FIRST_ON_RECORD_PATTERNS:
            if pattern.search(text):
                state.in_pre_record = False
                # Allow this block to continue processing normally —
                # the videographer's opening statement IS part of the record
                break
        else:
            if _is_pre_record_chatter(text):
                # This block is pre-record setup chatter (Zoom/Teams setup,
                # "can you hear me", lighting adjustments, greetings before the
                # reporter's opening statement). Discard it entirely from the
                # legal record.
                return []

    # Guard: a verified speaker map must still explicitly cover the speaker ID.
    # Never silently fall through to generic speaker labeling for an unmapped ID.
    if sid not in job_config.speaker_map:
        n = state.next_flag()
        sample = text[:SPEAKER_FLAG_SAMPLE_LEN].replace('\n', ' ')
        flag_text = (
            f'[SCOPIST: FLAG {n}: Speaker {sid} role not in speaker_map. '
            f'Sample: "{sample}"]'
        )
        state.flags.append(ScopistFlag(
            number=n,
            description=f'Speaker {sid} not in speaker map.',
            block_index=block_index,
            category='speaker',
            inline_text=flag_text,
        ))
        results.append((LineType.FLAG, flag_text))

    # ── Exhibit marking ───────────────────────────────────────────────────────
    exhibit_match = EXHIBIT_RE.search(text)
    if exhibit_match:
        exhibit_num = exhibit_match.group(1)
        results.append((LineType.PN,
            f"(Exhibit No. {exhibit_num} was marked for identification.)"))
        lowered = text.lower().strip().rstrip(".;:")
        if lowered in {
            f"i am handing you exhibit {exhibit_num}",
            f"i am handing you what has been marked as exhibit {exhibit_num}",
            f"what has been marked as exhibit {exhibit_num}",
            f"marked as exhibit {exhibit_num}",
        }:
            return results
        remaining = EXHIBIT_RE.sub('', text).strip().strip('.,;:')
        if not remaining:
            return results
        text = remaining

    # ── Oath / swearing-in (Spec Section 4.5) ─────────────────────────────────
    if OATH_RE.search(text):
        witness_name = job_config.witness_name or "Witness"
        time_str = _sentence_time(_extract_time(text) or job_config.depo_start_time)
        examiner_label = _get_label(job_config, job_config.examining_attorney_id)

        # MORSON'S COMPLIANCE: Use THE REPORTER: (not THE COURT REPORTER:)
        results.extend([
            (LineType.SP,
             f"THE REPORTER:  {witness_name}, would you please raise your right hand. "
             f"Do you solemnly swear to tell the truth, the whole truth, and nothing "
             f"but the truth, so help you God?"),
            (LineType.SP, "THE WITNESS:  I do."),
            (LineType.SP,
             "THE REPORTER:  Thank you. You can lower your hand. "
             "You may proceed with the examination."),
            (LineType.PN, "(The witness was sworn.)"),
            (LineType.PN, f"(Whereupon, the deposition commenced at {time_str}.)"),
            (LineType.HEADER, state.examination_type),
            (LineType.BY, f"BY {examiner_label}:"),
        ])
        state.current_examiner_id = job_config.examining_attorney_id
        return results

    # ── Videographer — recess / resumption (Spec Section 4.4) ────────────────
    vg_ids = [k for k, v in job_config.speaker_map.items()
               if 'VIDEOGRAPHER' in v.upper()]
    is_videographer = sid in vg_ids or sid == 0

    if is_videographer:
        if OFF_RECORD_RE.search(text):
            state.in_post_record = True
            time_str = _sentence_time(_extract_time(text))
            results.append((LineType.PN,
                f"(Whereupon, a recess was taken at {time_str}.)"))
            return results

        if ON_RECORD_RE.search(text):
            state.in_post_record = False
            time_str = _sentence_time(_extract_time(text))
            results.append((LineType.PN,
                f"(Whereupon, the proceedings resumed at {time_str}.)"))
            if state.current_examiner_id is not None:
                examiner_label = _get_label(job_config, state.current_examiner_id)
                results.append((LineType.BY, f"BY {examiner_label}:"))
            return results

        if CONCLUDED_RE.search(text):
            time_str = _sentence_time(_extract_time(text) or job_config.depo_end_time)
            results.append((LineType.PN,
                f"(Whereupon, the deposition concluded at {time_str}.)"))
            return results

    # ── Post-record blocks (Spec Section 8 + 9.5) ─────────────────────────────
    if state.in_post_record:
        spelling_match = SPELLING_RE.search(text)
        if spelling_match:
            name    = spelling_match.group(1).strip()
            letters = spelling_match.group(2).strip()
            prs = PostRecordSpelling(
                name=name,
                correct_spelling=derive_correct_spelling(letters),
                letters_as_given=letters,
                block_index=block_index,
                flag=f"Verify: spelled on record as {letters}",
            )
            state.post_record_spellings.append(prs)
            n = state.next_flag()
            flag_text = flag_post_record_spelling(n, name, letters)
            state.flags.append(ScopistFlag(
                number=n,
                description=f'Post-record spelling: "{name}" — {letters}',
                block_index=block_index, category='post_record',
                inline_text=flag_text,
            ))
        label = _get_label(job_config, sid)
        results.append((LineType.SP, f"{label}:  {text}"))
        return results

    # ── Objection detection (Morson's: preserve as spoken) ────────────────────
    # Objections from non-witness speakers are formatted as SP lines.
    # The spoken text is preserved EXACTLY — we do NOT rewrite "Objection." to
    # "Objection to form." per Morson's English Guide for Court Reporters.
    # Only add terminal period if completely missing.
    if sid != job_config.witness_id and OBJECTION_START_RE.match(text.strip()):
        label = _get_label(job_config, sid)
        obj_text = text.strip()
        # Ensure terminal punctuation — never add words not spoken
        if obj_text and obj_text[-1] not in '.!?':
            obj_text += '.'
        results.append((LineType.SP, f"{label}:  {obj_text}"))
        return results

    # ── Q/A classification (Spec Section 4.2) ─────────────────────────────────
    if sid == job_config.examining_attorney_id:
        state.current_examiner_id = sid
        correct_split = split_correct_mid(text)
        if correct_split:
            before, correct_text, continuation = correct_split
            results.append((LineType.Q, before))
            results.append((LineType.A, correct_text))
            if continuation:
                results.append((LineType.Q, continuation))
            state.qa_tracker_last_was_q = True
            return results

        split = _detect_embedded_answer(text, job_config)
        if split:
            q_text, a_text, continuation = split
            results.append((LineType.Q, q_text))
            results.append((LineType.A, a_text))
            if continuation:
                results.append((LineType.Q, continuation))
                state.qa_tracker_last_was_q = True
            else:
                state.qa_tracker_last_was_q = False
        else:
            results.append((LineType.Q, text))
            state.qa_tracker_last_was_q = True
        return results

    if sid == job_config.witness_id:
        if _looks_like_question_text(text):
            split = _detect_embedded_answer(text, job_config)
            if split:
                q_text, a_text, continuation = split
                results.append((LineType.Q, q_text))
                results.append((LineType.A, a_text))
                if continuation:
                    results.append((LineType.Q, continuation))
                    state.qa_tracker_last_was_q = True
                else:
                    state.qa_tracker_last_was_q = False
                return results
            # Witness text that *looks* like a question but has no
            # embedded answer split — emit as A. Witness rhetorical
            # questions, tag questions ("you know?", "right?"), and
            # quoted speech ending in "?" are testimony, not new
            # questions to be answered. Previously emitted as Q, which
            # broke Q/A flow and let the next attorney line be misread
            # as a witness answer.
            results.append((LineType.A, text))
            state.qa_tracker_last_was_q = False
            return results
        results.append((LineType.A, text))
        state.qa_tracker_last_was_q = False
        return results

    if (
        state.qa_tracker_last_was_q
        and sid != job_config.examining_attorney_id
        and _looks_like_answer_after_question(text, speaker_label_upper)
    ):
        results.append((LineType.A, text))
        state.qa_tracker_last_was_q = False
        return results

    # ── All other speakers → Speaker Label ────────────────────────────────────
    results.append((LineType.SP, f"{speaker_label}:  {text}"))
    state.qa_tracker_last_was_q = False
    return results
