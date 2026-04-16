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

Called from ui/tab_corrections.py via the "AI Correct" button only.
Never runs automatically. Deterministic corrections and AI correction
are separate explicit user actions.
"""

from __future__ import annotations

import os
import re
import hashlib
from typing import Any

from app_logging import get_logger
from config import ANTHROPIC_API_KEY as _CONFIG_API_KEY
from spec_engine.prompt_packs import load_prompt_pack

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


_DEFAULT_PROMPT_PACK = load_prompt_pack("claude_like_v1")
TRANSCRIPT_CORRECTION_SYSTEM_PROMPT = _DEFAULT_PROMPT_PACK.system_prompt


# ── AI correction runner ──────────────────────────────────────────────────────

def _build_user_prompt(
    transcript_text: str,
    proper_nouns: list[str],
    speaker_map: dict,
    confirmed_spellings: dict,
    post_record_spellings: list = None,
    user_prompt_template: str = "{context}Please apply all rules to the following transcript:\n\n{transcript}",
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

    return user_prompt_template.format(context=context_block, transcript=transcript_text)


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


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
    prompt_pack = load_prompt_pack()
    model_name = os.environ.get('ANTHROPIC_MODEL', '').strip() or prompt_pack.model

    for i, chunk in enumerate(chunks):
        _log(f'AI correcting chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)…')

        chunk_prompt, protected = _protect_verbatim(chunk)

        user_prompt = _build_user_prompt(
            chunk_prompt,
            proper_nouns,
            speaker_map,
            confirmed_spellings,
            post_record_spellings,
            prompt_pack.user_prompt_template,
        )
        logger.info(
            '[AICorrector] Prompt pack=%s model=%s system_hash=%s user_hash=%s chunk_chars=%s',
            prompt_pack.id,
            model_name,
            _hash_text(prompt_pack.system_prompt),
            _hash_text(user_prompt),
            len(chunk),
        )

        message = client.messages.create(
            model=model_name,
            max_tokens=prompt_pack.max_tokens,
            system=prompt_pack.system_prompt,
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
