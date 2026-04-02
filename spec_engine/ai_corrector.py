"""
spec_engine/ai_corrector.py

AI-assisted transcript correction pass using Claude API.

This is an OPTIONAL second pass that runs AFTER the deterministic
corrections in corrections.py. It handles cases that require reading
context — things Python regex cannot do safely.

Rules handled here (per Morson's English Guide and Depo-Pro spec):
  Rule 6   — Proper noun correction (from provided list)
  Rule 7   — Homophone correction (100% context certainty only)
  Rule 9   — [VERIFY: ...] flags for uncertain corrections
  Rule 14  — Ellipsis preservation (. . . / ... / ....)
  Rule 15  — Percent / height context-dependent cases
  Rule 21  — [SCOPIST: FLAG N:] for unverifiable garbles
  Rule 23  — Verbatim affirmation/negation (Yeah/Nope kept)
  Rule 24  — Post-record spelling retroactive correction

VERBATIM MANDATE (absolute, no exceptions):
  uh, um, ah, uh-huh, uh-uh, yeah, yep, yup, nope, nah, gonna, wanna
  — these are NEVER normalized or removed. They are part of the legal record.

Called from core/correction_runner.py when apply_ai=True.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app_logging import get_logger
from config import ANTHROPIC_API_KEY as _CONFIG_API_KEY

logger = get_logger(__name__)

VERBATIM_TOKEN_RE = re.compile(
    r'\b(?:uh-huh|uh-uh|uh|um|ah|yeah|yep|yup|nope|nah|gonna|wanna|gotta)\b',
    re.IGNORECASE,
)
SCOPIST_FLAG_RE = re.compile(r'\[SCOPIST: FLAG \d+:')


def _protect_verbatim(text: str) -> tuple[str, dict[str, str]]:
    """Replace verbatim-protected tokens with placeholders before AI."""
    protected: dict[str, str] = {}
    counter = [0]

    def _replace(match: re.Match) -> str:
        key = f"__VERBATIM_{counter[0]}__"
        protected[key] = match.group(0)
        counter[0] += 1
        return key

    return VERBATIM_TOKEN_RE.sub(_replace, text), protected


def _restore_verbatim(text: str, protected: dict[str, str]) -> str:
    for key, value in protected.items():
        text = text.replace(key, value)
    return text


def _all_protected_tokens_preserved(text: str, protected: dict[str, str]) -> bool:
    return all(key in text for key in protected)


def _line_signature(line: str) -> str:
    stripped = line.lstrip('\t ')
    if not stripped:
        return 'BLANK'
    if stripped.startswith('Q.'):
        return 'Q'
    if stripped.startswith('A.'):
        return 'A'
    if re.match(r"^[A-Z][A-Z .'\-]+:\s*", stripped):
        return 'SP'
    return 'TEXT'


def _preserves_structure(original: str, candidate: str) -> bool:
    original_lines = original.splitlines()
    candidate_lines = candidate.splitlines()
    if len(original_lines) != len(candidate_lines):
        return False
    return [
        _line_signature(line) for line in original_lines
    ] == [
        _line_signature(line) for line in candidate_lines
    ]


# ── System prompt ─────────────────────────────────────────────────────────────

TRANSCRIPT_CORRECTION_SYSTEM_PROMPT = """
You are a certified legal transcript editor specializing in Texas deposition
transcripts. You apply Morson's English Guide for Court Reporters and the
Texas Uniform Format Manual (UFM) to correct AI-transcription artifacts while
preserving the verbatim legal record.

ABSOLUTE VERBATIM RULE — violations invalidate the transcript:
These words and sounds are NEVER changed, removed, or normalized:
  uh, um, ah          — hesitation markers (Morson's Rule 4)
  uh-huh, uh-uh       — non-lexical affirmation/negation (Morson's Rule 4)
  yeah, yep, yup      — informal affirmation (never change to "Yes")
  nope, nah           — informal negation (never change to "No")
  gonna, wanna, gotta — informal speech (witness register is evidence)
  stutters: b-b-bank  — stutter within a word, hyphen, no space
  false starts: word -- — preserve exactly as spoken

## STRUCTURE PROTECTION RULE (ABSOLUTE)
You MUST NOT:
  - Change Q./A. labels
  - Move text between speakers
  - Insert or remove speaker lines
  - Extract objections into new lines
  - Modify transcript structure in any way

Structure is handled by the deterministic pipeline before AI processing.
You may ONLY:
  - Correct individual words or short phrases already present
  - Add [VERIFY: ...] when uncertainty remains
  - Add [SCOPIST: FLAG N: ...] when certainty is impossible

## RULE 6 — PROPER NOUN CORRECTION
Correct only to names in the provided proper_nouns list.
If a name is NOT in the list → [SCOPIST: FLAG N: Verify spelling from audio]
Never invent or guess a spelling not confirmed by the source documents.

## RULE 7 — HOMOPHONE CORRECTION
Correct ONLY when you are 100% certain from context.
Examples where context makes it clear:
  "know" vs "no" — "I don't know" vs "No, I didn't"
  "their" vs "there" — "their truck" vs "over there"
  "to" vs "too" vs "two"
When uncertain → [VERIFY: possible homophone: word1/word2]

## RULE 9 — VERIFY FLAGS
Use [VERIFY: brief description] for uncertain corrections.
Use [VERIFY: proper noun — not in source list] for unknown names.
Do NOT use VERIFY for common words you are confident about.

## RULE 14 — ELLIPSIS PRESERVATION
Morson's Rules 270–273:
  . . .   — three spaced periods (trailing off / internal omission)
  . . . . — four spaced periods (omission at end of sentence)
  ...     — three joined periods (also acceptable per Morson's)

NEVER convert ". . ." to "..." or vice versa — preserve as found.
NEVER replace an ellipsis with a dash unless it clearly was a dash.

## RULE 15 — PERCENT / HEIGHT CONTEXT
Heights: "5.1" in medical context likely means 5'1" → correct to 5'1"
         Flag: [VERIFY: height — verify from audio if ambiguous]

Dollar amounts: "$4.50 per week" for a surgery claim → likely $450
                Flag with: [VERIFY: dollar amount — verify from audio]

## RULE 21 — SCOPIST FLAGS [SCOPIST: FLAG N: description]
Insert a scopist flag when you detect an error you CANNOT correct
with certainty:

Format:  [SCOPIST: FLAG N: one-line description]
Number:  Sequential, starting at FLAG 1 for this transcript.

Flag for:
  - Phonetically plausible but contextually wrong words
    "pills" in billing context → likely "bills"
    "bag" in injury context → likely "back"
  - Proper names not in the provided proper_nouns list
  - Attorney-stated facts not confirmed by the witness
    Attorney: "I believe that was a 2012 Jeep" → flag the year
  - Names mentioned only in attorney questions (not by witness)

DO NOT:
  - Flag common words that are clearly correct
  - Replace the word — insert flag NEXT TO the original text
  - Use any other flag format

## RULE 23 — VERBATIM AFFIRMATION / NEGATION PRESERVATION
These must be kept EXACTLY as spoken. Never normalize:
  Yeah  → keep as "Yeah."   (NEVER change to "Yes.")
  Yep   → keep as "Yep."    (NEVER change to "Yes.")
  Yup   → keep as "Yup."    (NEVER change to "Yes.")
  Nope  → keep as "Nope."   (NEVER change to "No.")
  Nah   → keep as "Nah."    (NEVER change to "No.")

These are part of the verbatim legal record.
Normalizing them constitutes alteration of testimony.

## RULE 24 — POST-RECORD SPELLING RETROACTIVE CORRECTION

When CONFIRMED POST-RECORD SPELLINGS are provided below,
the spellings are AUTHORITATIVE. They were established on
the record by the witness or attorney spelling out a name
letter by letter.

For each confirmed spelling:
  - The correct form is given (e.g., Balderas)
  - All prior instances in this chunk where the name
    appears in any phonetic or misspelled form must be
    corrected to the confirmed spelling
  - Do NOT alter the hyphenated letter sequence itself
    (e.g., B-A-L-D-E-R-A-S must remain as written —
    it is part of the verbatim record)
  - Do NOT correct instances that appear AFTER the
    spelling was given — those are already correct

If no CONFIRMED POST-RECORD SPELLINGS section appears
in the prompt, this rule does not apply.

## OUTPUT REQUIREMENTS
Return ONLY the corrected transcript text.
Do NOT add commentary, explanations, headers, or summaries.
Do NOT add markdown formatting (no **, no ##, no ---).
Preserve all existing line breaks and paragraph structure.
Preserve all tab characters that begin Q., A., and SP lines.
""".strip()


# ── AI correction runner ──────────────────────────────────────────────────────

def _build_user_prompt(
    transcript_text: str,
    proper_nouns: list[str],
    speaker_map: dict,
    confirmed_spellings: dict,
    post_record_spellings: list = None,
) -> str:
    """Build the user-turn prompt with case-specific context."""
    parts = []

    if proper_nouns:
        parts.append(
            "PROPER NOUNS (verified spellings — use these exactly):\n"
            + "\n".join(f"  {n}" for n in proper_nouns[:30])
        )

    if speaker_map:
        parts.append(
            "SPEAKER MAP:\n"
            + "\n".join(f"  Speaker {k} → {v}" for k, v in speaker_map.items())
        )

    if confirmed_spellings:
        parts.append(
            "CONFIRMED SPELLINGS (use exactly):\n"
            + "\n".join(f"  {k} → {v}" for k, v in list(confirmed_spellings.items())[:40])
        )

    if post_record_spellings:
        confirmed_prs = [
            prs for prs in post_record_spellings
            if getattr(prs, 'correct_spelling', '')
        ]
        if confirmed_prs:
            parts.append(
                "CONFIRMED POST-RECORD SPELLINGS"
                " (authoritative — correct all prior instances):\n"
                + "\n".join(
                    f"  {getattr(prs, 'letters_as_given', '')} → "
                    f"{getattr(prs, 'correct_spelling', '')}"
                    for prs in confirmed_prs
                )
            )

    context_block = "\n\n".join(parts)
    if context_block:
        context_block += "\n\n"

    return (
        f"{context_block}"
        f"Please apply all rules to the following transcript:\n\n"
        f"{transcript_text}"
    )


def run_ai_correction(
    transcript_text: str,
    job_config: Any,
    progress_callback=None,
) -> str:
    """
    Run an AI correction pass on a transcript text block.

    Args:
        transcript_text:   The corrected transcript text (after Python rules).
        job_config:        JobConfig or dict — used for proper nouns, speaker
                           map, and confirmed spellings.
        progress_callback: Optional callable for status messages.

    Returns:
        Corrected transcript text string.

    Returns original transcript text unchanged when AI is unavailable.
    """
    api_key = (_CONFIG_API_KEY or os.environ.get('ANTHROPIC_API_KEY', '')).strip()
    if not api_key:
        logger.info('[AICorrector] AI disabled — no API key found')
        return transcript_text

    def _log(msg: str):
        logger.info('[AICorrector] %s', msg)
        if progress_callback:
            progress_callback(msg)

    import anthropic

    if hasattr(job_config, 'all_proper_nouns'):
        proper_nouns = list(getattr(job_config, 'all_proper_nouns', []) or [])
    elif isinstance(job_config, dict):
        proper_nouns = list(job_config.get('all_proper_nouns', []) or [])
    else:
        proper_nouns = []

    speaker_map: dict = {}
    if hasattr(job_config, 'speaker_map'):
        speaker_map = dict(getattr(job_config, 'speaker_map', {}) or {})
    elif isinstance(job_config, dict):
        speaker_map = dict(job_config.get('speaker_map', {}) or {})

    confirmed_spellings: dict = {}
    if hasattr(job_config, 'confirmed_spellings'):
        confirmed_spellings = dict(getattr(job_config, 'confirmed_spellings', {}) or {})
    elif isinstance(job_config, dict):
        confirmed_spellings = dict(job_config.get('confirmed_spellings', {}) or {})

    post_record_spellings: list = []
    if hasattr(job_config, 'post_record_spellings'):
        post_record_spellings = list(
            getattr(job_config, 'post_record_spellings', []) or []
        )
    elif isinstance(job_config, dict):
        post_record_spellings = list(
            job_config.get('post_record_spellings', []) or []
        )

    MAX_CHARS = 8000
    chunks = _split_into_chunks(transcript_text, MAX_CHARS)
    _log(f'Split transcript into {len(chunks)} chunk(s) for AI correction')

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    model_name = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-6').strip() or 'claude-sonnet-4-6'

    for i, chunk in enumerate(chunks):
        _log(f'AI correcting chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)…')

        chunk_prompt, protected = _protect_verbatim(chunk)

        user_prompt = _build_user_prompt(
            chunk_prompt,
            proper_nouns,
            speaker_map,
            confirmed_spellings,
            post_record_spellings,
        )

        message = client.messages.create(
            model=model_name,
            max_tokens=5500,
            system=TRANSCRIPT_CORRECTION_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        corrected_protected_chunk = message.content[0].text.strip()

        if not _all_protected_tokens_preserved(corrected_protected_chunk, protected):
            _log('AI output removed verbatim-protected tokens — reverting to original chunk')
            results.append(chunk)
            continue

        corrected_chunk = _restore_verbatim(corrected_protected_chunk, protected)

        if len(corrected_chunk) < len(chunk) * 0.9:
            _log('AI output too destructive — reverting to original chunk')
            results.append(chunk)
            continue

        if not _preserves_structure(chunk, corrected_chunk):
            _log('AI output changed transcript structure — reverting to original chunk')
            results.append(chunk)
            continue

        results.append(corrected_chunk)

    assembled = '\n\n'.join(results)
    assembled = _renumber_scopist_flags(assembled)

    total_flags = len(SCOPIST_FLAG_RE.findall(assembled))
    _log(f'AI correction complete — {total_flags} scopist flags generated')
    return assembled


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """
    Split transcript text into chunks at paragraph boundaries.
    Preserves complete paragraphs — never splits mid-paragraph.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split('\n\n')
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2
        if current_len + para_len > max_chars and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append('\n\n'.join(current))
    return chunks


def _renumber_scopist_flags(text: str) -> str:
    """Renumber all [SCOPIST: FLAG N:] markers sequentially from 1."""
    counter = [0]

    def _replace(m: re.Match) -> str:
        counter[0] += 1
        return f'[SCOPIST: FLAG {counter[0]}:'

    return re.sub(r'\[SCOPIST: FLAG \d+:', _replace, text)
