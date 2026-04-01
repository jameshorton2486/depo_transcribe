"""
spec_engine/ai_corrector.py

AI-assisted transcript correction pass using Claude API.

This is an OPTIONAL second pass that runs AFTER the deterministic
corrections in corrections.py. It handles cases that require reading
context — things Python regex cannot do safely.

Rules handled here (per Morson's English Guide and Depo-Pro spec):
  Rule 5   — Speaker Q/A structure consistency
  Rule 6   — Proper noun correction (from provided list)
  Rule 7   — Homophone correction (100% context certainty only)
  Rule 9   — [VERIFY: ...] flags for uncertain corrections
  Rule 12  — Speaker label resolution (Speaker 0/1/2/3 → names)
  Rule 13  — THE REPORTER / THE INTERPRETER label standards
  Rule 14  — Ellipsis preservation (. . . / ... / ....)
  Rule 15  — Percent / height context-dependent cases
  Rule 17  — As-read parentheticals
  Rule 18  — Objection fragment format
  Rule 19  — CROSS-EXAMINATION headers (hyphenated)
  Rule 21  — [SCOPIST: FLAG N:] for unverifiable garbles
  Rule 22  — Interpreter block extraction
  Rule 23  — Verbatim affirmation/negation (Yeah/Nope kept)

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

## RULE 5 — SPEAKER STRUCTURE
Q. lines are asked by examining attorneys.
A. lines are given by the witness.
SP lines (MR. X:, MS. X:, THE REPORTER:, THE VIDEOGRAPHER:) are colloquy.

If a block is misclassified (e.g., the witness's answer is on a Q. line),
correct the label. Never invent testimony.

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

## RULE 12 — SPEAKER LABEL RESOLUTION
Replace generic "Speaker 0:", "Speaker 1:", etc. with the actual
speaker labels from the provided speaker_map.

Format for colloquy (SP lines):
  MR. GARCIA:   (examining attorney)
  MS. DURBIN:   (opposing counsel)
  THE WITNESS:  (when witness speaks outside Q/A structure)
  THE REPORTER: (court reporter)
  THE VIDEOGRAPHER:
  THE INTERPRETER:

All SP labels must be ALL-CAPS followed by a colon and two spaces.

## RULE 13 — REPORTER / INTERPRETER LABELS
Always: THE REPORTER:  (not "THE COURT REPORTER:", not "REPORTER:")
Always: THE INTERPRETER:  (not "INTERPRETER:", not "(Interpreter:)")

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

## RULE 17 — AS-READ PARENTHETICALS
When an attorney reads aloud from a document, set the reading off:
  Q. I'm going to read from page 3.
  (Reading:)
  "The claimant suffered injuries..."
  (End of reading.)
Do not insert these unless the transcript clearly shows a reading.

## RULE 18 — OBJECTION FORMAT
Objections mid-question must be extracted to their own SP line:
  Before: Q. Did you--Objection, form. Did you see the accident?
  After:  Q. Did you --
          MR. DAVIS:  Objection.  Form.
          Q. (BY MR. GARCIA:)  Did you see the accident?

Objection punctuation: "Objection." with period.
Form objection: "Objection.  Form."  (two spaces between)

## RULE 19 — CROSS-EXAMINATION HEADERS
Always hyphenated:
  CROSS-EXAMINATION  (never "CROSS EXAMINATION")
  REDIRECT EXAMINATION
  RECROSS-EXAMINATION

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

## RULE 22 — INTERPRETER BLOCK EXTRACTION
When an interpreter speaks mid-answer, extract to its own SP block:

Before:
  A. Yes -- continuación -- I was there.

After:
  A. Yes --

  THE INTERPRETER:  (Translation in progress.)

  A. I was there.

If the interpreter's words are unclear → THE INTERPRETER:  [inaudible]
Use THE INTERPRETER: — not INTERPRETER: or (Interpreter:)

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

    Raises:
        RuntimeError if API key is missing.
        Exception propagated from the Anthropic client on API failure.
    """
    import anthropic

    api_key = (_CONFIG_API_KEY or os.environ.get('ANTHROPIC_API_KEY', '')).strip()
    if not api_key:
        raise RuntimeError(
            'ANTHROPIC_API_KEY is not set. '
            'Add it to your .env file or set it as an environment variable.'
        )

    def _log(msg: str):
        logger.info('[AICorrector] %s', msg)
        if progress_callback:
            progress_callback(msg)

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

    MAX_CHARS = 18000
    chunks = _split_into_chunks(transcript_text, MAX_CHARS)
    _log(f'Split transcript into {len(chunks)} chunk(s) for AI correction')

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    flag_offset = 0

    for i, chunk in enumerate(chunks):
        _log(f'AI correcting chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)…')

        chunk_prompt = chunk

        user_prompt = _build_user_prompt(
            chunk_prompt,
            proper_nouns,
            speaker_map,
            confirmed_spellings,
            post_record_spellings,
        )

        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=5500,
            system=TRANSCRIPT_CORRECTION_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        corrected_chunk = message.content[0].text.strip()
        results.append(corrected_chunk)

        flag_count = len(re.findall(r'\[SCOPIST: FLAG \d+:', corrected_chunk))
        flag_offset += flag_count

    assembled = '\n\n'.join(results)
    assembled = _renumber_scopist_flags(assembled)

    _log(f'AI correction complete — {flag_offset} scopist flags generated')
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
