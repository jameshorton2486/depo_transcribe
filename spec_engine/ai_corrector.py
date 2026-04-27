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
import time
from typing import Any

from app_logging import get_logger
from config import ANTHROPIC_API_KEY as _CONFIG_API_KEY
from spec_engine.prompt_packs import load_prompt_pack

logger = get_logger(__name__)

VERBATIM_TOKEN_RE = re.compile(
    r'\b(?:uh-huh|uh-uh|uh|um|ah|yeah|yep|yup|nope|nah|gonna|wanna|gotta)\b',
    re.IGNORECASE,
)
SPEAKER_PREFIX_RE = re.compile(r"^\s*([A-Z][A-Z .'\-]+:)")
# Texas stutters / false starts use a double hyphen, not a single hyphen.
DOUBLE_HYPHEN_STUTTER_RE = re.compile(r"\b\w+--\w*\b")
FALSE_START_RE = re.compile(r"\b\w+\s*--")
SCOPIST_FLAG_RE = re.compile(r'\[SCOPIST: FLAG \d+:')
WORD_RE = re.compile(r"\b[\w']+\b")
MAX_LENGTH_DELTA_RATIO = 0.30
MAX_WORD_CHANGE_RATIO = 0.15
_MAX_RETRIES = 3
_RETRY_BASE_DELAY_SEC = 2.0


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


def _verbatim_counts_preserved(original: str, candidate: str) -> bool:
    """
    Compare verbatim token counts in the restored text, not placeholder keys.

    The old validation path generated fresh __VERBATIM_N__ placeholders from
    the original text and then checked for those keys in the restored candidate.
    That can never succeed because the candidate has already had placeholders
    restored back to real words.
    """
    from collections import Counter

    original_tokens = [m.group(0).lower() for m in VERBATIM_TOKEN_RE.finditer(original)]
    candidate_tokens = [m.group(0).lower() for m in VERBATIM_TOKEN_RE.finditer(candidate)]
    return Counter(original_tokens) == Counter(candidate_tokens)


def _extract_speaker_prefix(line: str) -> str:
    match = SPEAKER_PREFIX_RE.match(line)
    return match.group(1).strip() if match else ""


def _extract_special_verbatim_forms(text: str) -> list[str]:
    forms = [match.group(0) for match in DOUBLE_HYPHEN_STUTTER_RE.finditer(text)]
    forms.extend(match.group(0) for match in FALSE_START_RE.finditer(text))
    return forms


def _preserves_special_verbatim_forms(original: str, candidate: str) -> bool:
    return _extract_special_verbatim_forms(original) == _extract_special_verbatim_forms(candidate)


def _line_preserves_protected_content(original_line: str, candidate_line: str) -> bool:
    original_prefix = _extract_speaker_prefix(original_line)
    if original_prefix and original_prefix != _extract_speaker_prefix(candidate_line):
        return False
    return _preserves_special_verbatim_forms(original_line, candidate_line)


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


def _check_structure(original: str, candidate: str) -> str:
    """Return ``""`` if structure is preserved, or a granular sub-reason.

    Sub-reasons (stable strings — log-grep tooling depends on them):
      - ``"structure_line_count"`` — line count differs between input/output
      - ``"structure_signatures"`` — line type sequence (Q/A/SP/PAREN/TEXT/BLANK) differs
      - ``"structure_speaker_prefix"`` — a speaker label changed (e.g. MR. SMITH → THE REPORTER)

    The Caram post-NOD revert analysis (2026-04-27) showed `structure` as
    the dominant validator block (3 of 6 reverts). Splitting it tells the
    operator which structural change the AI is making most often, so the
    next prompt-tuning or threshold decision has a target.
    """
    original_lines = original.splitlines()
    candidate_lines = candidate.splitlines()
    if len(original_lines) != len(candidate_lines):
        return "structure_line_count"

    original_signatures = [_line_signature(line) for line in original_lines]
    candidate_signatures = [_line_signature(line) for line in candidate_lines]
    if original_signatures != candidate_signatures:
        return "structure_signatures"

    for original_line, candidate_line in zip(original_lines, candidate_lines):
        original_prefix = _extract_speaker_prefix(original_line)
        if original_prefix and original_prefix != _extract_speaker_prefix(candidate_line):
            return "structure_speaker_prefix"

    return ""


def _preserves_structure(original: str, candidate: str) -> bool:
    return _check_structure(original, candidate) == ""


def _within_length_delta(original: str, candidate: str, max_ratio: float = MAX_LENGTH_DELTA_RATIO) -> bool:
    baseline = max(len(original), 1)
    return abs(len(candidate) - len(original)) / baseline <= max_ratio


def _word_change_ratio(original: str, candidate: str) -> float:
    original_words = WORD_RE.findall(original)
    candidate_words = WORD_RE.findall(candidate)
    baseline = max(len(original_words), 1)
    shared = sum(1 for old, new in zip(original_words, candidate_words) if old == new)
    delta = max(len(original_words), len(candidate_words)) - shared
    return delta / baseline


def _validate_ai_output(original: str, candidate: str) -> tuple[bool, str]:
    """Validate AI-corrected chunk against original.

    Returns ``(passed, reason)`` where ``reason`` is an empty string on
    success, or a short snake_case identifier of the specific check that
    failed. The reason is logged at the call site so a 50%+ revert rate
    can be diagnosed without re-running the model — see the
    AICorrector revert-rate diagnostic for why this granularity exists.
    """
    if not _verbatim_counts_preserved(original, candidate):
        return False, "verbatim_count"
    if not _preserves_special_verbatim_forms(original, candidate):
        return False, "special_verbatim_forms"
    structure_reason = _check_structure(original, candidate)
    if structure_reason:
        return False, structure_reason
    if not _within_length_delta(original, candidate):
        return False, "length_delta"
    if _word_change_ratio(original, candidate) > MAX_WORD_CHANGE_RATIO:
        return False, "word_change_ratio"

    original_lines = original.splitlines()
    candidate_lines = candidate.splitlines()
    if len(original_lines) != len(candidate_lines):
        # Defensive: _preserves_structure already rejects line-count
        # mismatches, so this branch is unreachable in practice. Kept
        # for safety; if it ever fires, surface a distinct reason so we
        # know the structural pre-check has drifted.
        return False, "line_count"
    if not all(
        _line_preserves_protected_content(original_line, candidate_line)
        for original_line, candidate_line in zip(original_lines, candidate_lines)
    ):
        return False, "protected_content"
    return True, ""


# ── AI correction runner ──────────────────────────────────────────────────────

# Order of CASE METADATA fields shown to the AI. Listed top-down so the
# fields most likely to anchor a phonetic correction (cause number,
# witness name) come first. CSR and court fields anchor the reporter's
# preamble passage, where Deepgram routinely garbles formal phrases.
_CASE_METADATA_FIELDS: list[tuple[str, str]] = [
    ("cause_number", "Cause Number"),
    ("witness_name", "Witness"),
    ("reporter_name", "Reporter"),
    ("csr_number", "CSR No."),
    ("judicial_district", "Judicial District"),
    ("court_caption", "Court"),
    ("depo_date", "Deposition Date"),
]


def _build_user_prompt(
    transcript_text: str,
    proper_nouns: list[str],
    speaker_map: dict,
    confirmed_spellings: dict,
    post_record_spellings: list = None,
    case_metadata: dict | None = None,
    user_prompt_template: str = "{context}Please apply all rules to the following transcript:\n\n{transcript}",
) -> str:
    """Build the user-turn prompt with case-specific context."""
    parts = []

    if case_metadata:
        # Skip empty values so a partially-populated job_config doesn't
        # render "Reporter: " with no name; an empty anchor is worse
        # than no anchor at all.
        rendered = [
            f"  {label}: {case_metadata[key]}"
            for key, label in _CASE_METADATA_FIELDS
            if str(case_metadata.get(key, "") or "").strip()
        ]
        if rendered:
            parts.append(
                "CASE METADATA (use these formal values when correcting "
                "the reporter's preamble or any reference to the case "
                "itself):\n" + "\n".join(rendered)
            )

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


def _api_call_with_retry(
    client: Any,
    model_name: str,
    max_tokens: int,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
    chunk_index: int,
    log_fn,
) -> str | None:
    """
    Retry transient Anthropic API failures with exponential backoff.
    """
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            message = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            content = getattr(message, "content", None) or []
            if not content:
                raise RuntimeError("Anthropic response missing content")
            return content[0].text.strip()
        except Exception as exc:
            last_exc = exc
            status_code = getattr(exc, "status_code", None)
            error_name = exc.__class__.__name__.lower()

            if status_code in {401, 403} or "authentication" in error_name:
                log_fn(
                    f"Chunk {chunk_index}: API authentication error — check ANTHROPIC_API_KEY: {exc}"
                )
                return None

            if attempt >= _MAX_RETRIES:
                break

            delay = _RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
            log_fn(
                f"Chunk {chunk_index}: API error ({type(exc).__name__}, "
                f"attempt {attempt}/{_MAX_RETRIES}) — retrying in {delay:.0f}s: {exc}"
            )
            time.sleep(delay)

    log_fn(
        f"Chunk {chunk_index}: All {_MAX_RETRIES} API attempts failed "
        f"— reverting to original. Last error: {last_exc}"
    )
    return None


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

    # Pull case metadata from either the JobConfig dataclass (top-level
    # attributes) or a dict-shaped config (the loaded job_config.json,
    # where these fields live under "ufm_fields"). Empty values are
    # filtered later inside _build_user_prompt so a partially-populated
    # config doesn't render labels with no value.
    case_metadata: dict = {}
    for key, _label in _CASE_METADATA_FIELDS:
        if hasattr(job_config, key):
            case_metadata[key] = getattr(job_config, key, "") or ""
        elif isinstance(job_config, dict):
            ufm = job_config.get("ufm_fields", {}) if isinstance(job_config.get("ufm_fields"), dict) else {}
            case_metadata[key] = (
                job_config.get(key)
                or ufm.get(key)
                or ""
            )

    try:
        prompt_pack = load_prompt_pack()
    except Exception as exc:
        _log(f'Prompt pack unavailable: {exc} — AI correction skipped')
        return transcript_text

    model_name = os.environ.get('ANTHROPIC_MODEL', '').strip() or prompt_pack.model
    MAX_CHARS = 8000
    chunks = _split_into_chunks(transcript_text, MAX_CHARS)
    _log(f'Split transcript into {len(chunks)} chunk(s) for AI correction')

    client = anthropic.Anthropic(api_key=api_key)
    results = []

    for i, chunk in enumerate(chunks):
        _log(f'AI correcting chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)…')

        chunk_prompt, protected = _protect_verbatim(chunk)

        user_prompt = _build_user_prompt(
            chunk_prompt,
            proper_nouns,
            speaker_map,
            confirmed_spellings,
            post_record_spellings,
            case_metadata,
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

        corrected_protected_chunk = _api_call_with_retry(
            client=client,
            model_name=model_name,
            max_tokens=prompt_pack.max_tokens,
            temperature=prompt_pack.temperature,
            system_prompt=prompt_pack.system_prompt,
            user_prompt=user_prompt,
            chunk_index=i + 1,
            log_fn=_log,
        )

        if corrected_protected_chunk is None:
            results.append(chunk)
            continue

        if not _all_protected_tokens_preserved(corrected_protected_chunk, protected):
            _log('AI output removed verbatim-protected tokens — reverting to original chunk')
            results.append(chunk)
            continue

        corrected_chunk = _restore_verbatim(corrected_protected_chunk, protected)
        passed, reason = _validate_ai_output(chunk, corrected_chunk)
        if not passed:
            _log(f'AI output failed validation ({reason}) — reverting to original chunk')
            results.append(chunk)
            continue

        results.append(corrected_chunk)

    assembled = '\n'.join(results)
    assembled = _renumber_scopist_flags(assembled)

    total_flags = len(SCOPIST_FLAG_RE.findall(assembled))
    _log(f'AI correction complete — {total_flags} scopist flags generated')
    return assembled


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """
    Split transcript text into chunks at Q/A block boundaries.

    The transcript text typically uses single newlines between Q/A and speaker
    lines. We only break chunks before a Q. or speaker line, never mid-answer.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = []
    current_len = 0

    for line in text.splitlines():
        line_len = len(line) + 1
        line_sig = _line_signature(line)

        if (
            current
            and current_len + line_len > max_chars
            and line_sig in {"Q", "SP"}
        ):
            chunks.append('\n'.join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append('\n'.join(current))
    return chunks


def _renumber_scopist_flags(text: str) -> str:
    """Renumber all [SCOPIST: FLAG N:] markers sequentially from 1."""
    counter = [0]

    def _replace(m: re.Match) -> str:
        counter[0] += 1
        return f'[SCOPIST: FLAG {counter[0]}:'

    return re.sub(r'\[SCOPIST: FLAG \d+:', _replace, text)
