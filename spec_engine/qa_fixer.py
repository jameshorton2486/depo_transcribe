"""
Q/A structure repair for block-based processing.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List

from .models import Block, BlockType

__all__ = [
    "fix_qa_structure",
    "split_inline_answers",
    "split_inline_questions_from_answers",
    "split_answer_prefixed_questions",
]

_log = logging.getLogger("spec_engine.qa_fixer")


# ── Tunable thresholds ───────────────────────────────────────────────────────
# Word-count ceiling for an utterance to be considered a generic short answer
# fragment in _looks_like_generic_answer_fragment.
MAX_GENERIC_ANSWER_FRAGMENT_WORDS = 8
# Word-count ceiling below which a same-speaker continuation block is folded
# into the previous block (Deepgram pause fragmentation cleanup).
TINY_CONTINUATION_WORD_COUNT = 3
# Jaccard similarity threshold (0.0-1.0) above which two consecutive same-
# speaker blocks are treated as chunk-overlap duplicates. Matches the
# duplicate-detection semantics in spec_engine/corrections.py.
NEAR_DUPLICATE_SIMILARITY_THRESHOLD = 0.85
# Two blocks must start within this many seconds of each other to be treated
# as chunk-overlap duplicates. Matches DUPLICATE_BLOCK_TIME_WINDOW_S in
# spec_engine/corrections.py.
NEAR_DUPLICATE_TIME_WINDOW_S = 1.0


ANSWER_TOKENS = (
    "yes", "no", "yeah", "yep", "nope",
    # corrections.py normalizes "uh uh" → "uh-uh" before qa_fixer runs
    "uh-huh", "uh-uh", "mm-hmm", "mhmm", "correct", "right",
    "yes,", "no,", "yes sir", "no sir", "yes ma'am", "no ma'am",
    "i do", "i don't", "i do not", "i did", "i did not",
    "i remember", "i recall", "i don't recall", "i don't remember",
)

# Broader answer-token prefixes used by `split_answer_prefixed_questions`
# to detect QUESTION blocks whose first sentence is a misattributed witness
# reply ("I will. Would you state your name?"). Includes ANSWER_TOKENS plus
# the modal-verb / first-person reply forms common in deposition testimony.
# Kept separate from ANSWER_TOKENS so the existing inline-answer splitters
# stay tight (those run earlier and feed Q-tail material into this stage).
ANSWER_PREFIX_TOKENS = ANSWER_TOKENS + (
    "i will", "i won't", "i will not",
    "i would", "i wouldn't", "i would not",
    "i could", "i couldn't", "i could not",
    "i can", "i can't", "i cannot",
    "i was", "i wasn't", "i was not",
    "i'm", "i am", "i'm not", "i am not",
    "i have", "i have not", "i haven't",
    "i think", "i believe",
)

# Period-suffixed entries were dead code — _merge_orphaned_continuations
# strips '.,!?' before the set intersection, so "correct." can never match.
STANDALONE_ANSWER_WORDS = frozenset({
    "correct", "right", "yes", "no", "true", "false",
    "absolutely", "exactly", "certainly", "agreed", "indeed",
    "uh-huh", "uh-uh", "mm-hmm", "mhmm",
    "yeah", "yep", "yup", "nope", "nah",
})

# Filler-only blocks are standalone testimony — must never be merged into a
# preceding block, or the affirmation/negation is silently deleted.
_FILLER_ONLY_RE = re.compile(
    r"^(?:uh[-\s]?huh|uh[-\s]?uh|mm[-\s]?hmm|mhmm|yeah|yep|yup|nope|nah)\.?$",
    re.IGNORECASE,
)

QUESTION_WORDS = ("who", "what", "when", "where", "why", "how", "did", "do", "does", "is", "are", "can", "could", "would", "will", "were", "was", "have", "has", "had")
IMPERATIVE_QUESTION_STARTERS = ("state", "tell", "describe", "explain", "identify", "name")
# Sentence-leading tokens that almost always signal a speaker shift inside an
# otherwise answer-led remainder. Used by _continues_answer to pick the latest
# answer-compatible boundary in `_extract_answer_and_continuation` (option d).
# Mirrors COLLOQUY_STARTERS (which `_looks_like_generic_answer_fragment` already
# uses to disqualify colloquy-led text from being treated as an answer
# fragment) and adds a few examiner-question lead-ins.
_TRANSITION_STARTERS = (
    # Mirrors COLLOQUY_STARTERS — kept inline because COLLOQUY_STARTERS is
    # defined later in this module.
    "okay",
    "all right",
    "alright",
    "now ",
    "then ",
    "just ",
    "let me",
    "let's",
    "let us",
    # Examiner-side question lead-ins.
    "so ",
    "and so",
    "and then,",
    "what about",
)
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
# "and " and "so " removed — witness answers commonly begin with these
# ("And then he left.", "So I stopped.") and should not be blocked from
# being recognized as answer fragments.
COLLOQUY_STARTERS = (
    "let's ",
    "let me ",
    "just ",
    "okay",
    "all right",
    "now ",
    "then ",
)

TOKEN_RE = re.compile(r"[a-z0-9']+")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
REPORTER_PREAMBLE_START_RE = re.compile(
    r"\bthis\s+is\s+cause\s+number\b"
    r"|\bcause\s+number\b"
    r"|\bthis\s+deposition\s+is\s+being\s+taken\s+in\s+accordance\s+with\b"
    r"|\bcounsel,\s+will\s+you\s+please\s+state\s+your\s+agreement\b",
    re.IGNORECASE,
)
# Inline Q/A split: matches a question + remainder. Non-greedy + DOTALL so the
# split happens at the first '?', not the last. Pre-compiled at module load
# so split_inline_answers() doesn't recompile per block.
_INLINE_QA_SPLIT_RE = re.compile(r"(.+?\?)\s+(.+)", re.DOTALL)
# Proper-noun fragment detector used by _looks_like_generic_answer_fragment.
# Pre-compiled at module load so it isn't rebuilt on every fragment check.
_PROPER_NOUN_FRAGMENT_RE = re.compile(
    r"[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,5}\.?"
)


def _get_config_value(job_config: Any, key: str, default: Any = None) -> Any:
    """Read a value from JobConfig (object) or dict, returning default if missing."""
    if job_config is None:
        return default
    if hasattr(job_config, key):
        return getattr(job_config, key, default)
    if isinstance(job_config, dict):
        return job_config.get(key, default)
    return default


def _resolve_speaker_identity(
    job_config: Any, id_key: str, original: Block
) -> tuple[Any, str | None]:
    """
    Resolve (speaker_id, speaker_name) from JobConfig + a speaker-ID key.

    Replaces the previously-duplicated _witness_identity/_examiner_identity
    pair. The asymmetric str() fallback for dict-style configs is preserved
    verbatim — when job_config is a plain dict the speaker_map may contain
    string keys that need a second lookup, but object-style configs are
    expected to have proper int keys.
    """
    if hasattr(job_config, id_key):
        speaker_id = getattr(job_config, id_key, original.speaker_id)
    elif isinstance(job_config, dict):
        speaker_id = job_config.get(id_key, original.speaker_id)
    else:
        speaker_id = original.speaker_id

    speaker_name: str | None = None
    if hasattr(job_config, "speaker_map"):
        speaker_name = (getattr(job_config, "speaker_map", {}) or {}).get(speaker_id)
    elif isinstance(job_config, dict):
        speaker_map = job_config.get("speaker_map", {}) or {}
        speaker_name = speaker_map.get(speaker_id)
        if speaker_name is None:
            speaker_name = speaker_map.get(str(speaker_id))
    return speaker_id, speaker_name


def _witness_identity(job_config: Any, original: Block) -> tuple[Any, str | None]:
    return _resolve_speaker_identity(job_config, "witness_id", original)


def _examiner_identity(job_config: Any, original: Block) -> tuple[Any, str | None]:
    return _resolve_speaker_identity(job_config, "examining_attorney_id", original)


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


def _looks_like_generic_answer_fragment(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized or _looks_like_question_text(normalized):
        return False

    lowered = normalized.lower()
    if lowered.startswith(COLLOQUY_STARTERS):
        return False
    if lowered.startswith(ANSWER_TOKENS):
        return True

    words = normalized.split()
    if len(words) > MAX_GENERIC_ANSWER_FRAGMENT_WORDS:
        return False

    if _PROPER_NOUN_FRAGMENT_RE.fullmatch(normalized):
        return True

    return normalized[0].isupper()


def _continues_answer(sentence: str) -> bool:
    """
    Decide whether a sentence inside a remainder still reads as part of the
    witness answer (rather than a speaker shift back to the examiner).

    Used to pick the LATEST answer-compatible sentence boundary in
    `_extract_answer_and_continuation` so multi-sentence answers like
    "Yes. I can access it." are not prematurely truncated to "Yes." when the
    actual bleed boundary is later in the block.
    """
    s = (sentence or "").strip()
    if not s:
        return False
    if s.endswith("?"):
        return False
    lowered = s.lower()
    if any(lowered.startswith(w + " ") for w in QUESTION_WORDS):
        return False
    if lowered.startswith(_TRANSITION_STARTERS):
        return False
    return True


def _extract_answer_and_continuation(remainder: str) -> tuple[str, str | None] | None:
    """
    Pull a witness-answer prefix off the front of `remainder`, returning
    (answer_text, continuation_text_or_None).

    Iterates sentence boundaries and selects the LATEST cumulative prefix
    where every sentence after the first still continues the answer (option d
    in the qa-fixer trace). This handles cases like
    "Yes. I can access it. Okay. What about" — the bleed is at "Okay.", not
    after the first period — so the answer becomes "Yes. I can access it."
    and the continuation becomes "Okay. What about".
    """
    text = (remainder or "").strip()
    if not text:
        return None

    lowered = text.lower()
    if not lowered.startswith(ANSWER_TOKENS):
        return None

    parts = SENTENCE_END_RE.split(text)
    if len(parts) == 1:
        return parts[0].strip(), None

    last_answer_idx = 0
    for i in range(1, len(parts)):
        if _continues_answer(parts[i]):
            last_answer_idx = i
        else:
            break

    answer_text = "  ".join(p.strip() for p in parts[: last_answer_idx + 1] if p.strip())
    continuation_text = "  ".join(p.strip() for p in parts[last_answer_idx + 1 :] if p.strip())
    if not answer_text:
        return None
    return answer_text, (continuation_text or None)


def _is_reporter_block(block: Block) -> bool:
    speaker_name = (block.speaker_name or "").upper()
    speaker_role = (block.speaker_role or "").upper()
    return "REPORTER" in speaker_name or "REPORTER" in speaker_role


def _merge_reporter_preamble_blocks(blocks: List[Block]) -> List[Block]:
    """
    Join the reporter's opening multi-paragraph preamble before later Q/A fixes.
    """
    if not blocks:
        return blocks

    result: List[Block] = []
    i = 0
    while i < len(blocks):
        current = blocks[i]
        if (
            _is_reporter_block(current)
            and REPORTER_PREAMBLE_START_RE.search((current.text or "").strip())
        ):
            merged = current
            j = i + 1
            while j < len(blocks):
                nxt = blocks[j]
                if not _is_reporter_block(nxt):
                    break
                if merged.speaker_id != nxt.speaker_id:
                    break
                merged = Block(
                    raw_text=((merged.raw_text or "") + " " + (nxt.raw_text or "")).strip(),
                    text=((merged.text or "").rstrip() + " " + (nxt.text or "").lstrip()).strip(),
                    speaker_id=merged.speaker_id,
                    speaker_name=merged.speaker_name,
                    speaker_role=merged.speaker_role,
                    block_type=merged.block_type,
                    words=list(merged.words) + list(nxt.words),
                    flags=list(merged.flags),
                    meta={**merged.meta, "merged_reporter_preamble": True},
                )
                j += 1
            result.append(merged)
            i = j
            continue

        result.append(current)
        i += 1
    return result


def split_inline_answers(blocks: List[Block], job_config: Any = None) -> List[Block]:
    """
    Split blocks like 'Did you go there? Yes.' into Q + A blocks.
    """
    new_blocks: List[Block] = []

    for block in blocks:
        if block.block_type != BlockType.QUESTION:
            new_blocks.append(block)
            continue

        text = block.text.strip()
        # Non-greedy + DOTALL: split on the first '?', not the last.
        # _INLINE_QA_SPLIT_RE is pre-compiled at module load.
        match = _INLINE_QA_SPLIT_RE.match(text)
        if not match:
            new_blocks.append(block)
            continue

        q_part, remainder = match.groups()
        extracted = _extract_answer_and_continuation(remainder)
        if extracted is None and block.meta.get("split_followup_question_from_answer"):
            stripped_remainder = remainder.strip()
            if stripped_remainder and _looks_like_generic_answer_fragment(stripped_remainder):
                extracted = (stripped_remainder, None)
        if not extracted:
            new_blocks.append(block)
            continue
        a_part, continuation = extracted

        witness_id, witness_name = _witness_identity(job_config, block)
        examiner_id, examiner_name = _examiner_identity(job_config, block)
        q_block = Block(
            raw_text=block.raw_text,
            text=q_part.strip(),
            speaker_id=block.speaker_id,
            speaker_name=block.speaker_name,
            speaker_role=block.speaker_role,
            block_type=BlockType.QUESTION,
            words=list(block.words),
            meta=dict(block.meta),
        )
        a_block = Block(
            raw_text=block.raw_text,
            text=a_part.strip(),
            speaker_id=witness_id,
            speaker_name=witness_name,
            block_type=BlockType.ANSWER,
            words=[],
            meta={**block.meta, "split_from_question": True},
        )
        new_blocks.extend([q_block, a_block])

        if continuation:
            followup_type = (
                BlockType.QUESTION
                if _looks_like_question_text(continuation)
                else BlockType.COLLOQUY
            )
            q2_block = Block(
                raw_text=block.raw_text,
                text=continuation,
                speaker_id=examiner_id,
                speaker_name=examiner_name,
                speaker_role=block.speaker_role,
                block_type=followup_type,
                words=[],
                meta={
                    **block.meta,
                    "split_followup_question": followup_type == BlockType.QUESTION,
                    "split_followup_continuation": followup_type == BlockType.COLLOQUY,
                },
            )
            new_blocks.append(q2_block)

    return new_blocks


def split_inline_questions_from_answers(blocks: List[Block], job_config: Any = None) -> List[Block]:
    """
    Split blocks like 'No, sir. Are you currently employed?' into A + Q blocks.
    """
    new_blocks: List[Block] = []

    for block in blocks:
        if block.block_type != BlockType.ANSWER:
            new_blocks.append(block)
            continue

        extracted = _extract_answer_and_continuation(block.text.strip())
        if not extracted:
            new_blocks.append(block)
            continue

        a_part, continuation = extracted
        if not continuation:
            new_blocks.append(block)
            continue

        # Continuation may be a complete question (emit as Q) OR a truncated
        # examiner-transition fragment ("Okay. What about", "So tell me...")
        # that doesn't end with '?' but reliably signals a speaker shift.
        # Per the option-d trace, relying on _looks_like_question_text alone
        # leaves bleed cases like "Yes. I can access it. Okay. What about"
        # unsplit. Fall back to a transition-starter check and emit as
        # COLLOQUY in that case — mirrors the COLLOQUY fallback already used
        # by split_inline_answers (qa_fixer.py:409-413).
        continuation_lower = continuation.lower()
        is_question = _looks_like_question_text(continuation)
        is_transition = continuation_lower.startswith(_TRANSITION_STARTERS)
        if not (is_question or is_transition):
            new_blocks.append(block)
            continue

        followup_type = BlockType.QUESTION if is_question else BlockType.COLLOQUY

        examiner_id, examiner_name = _examiner_identity(job_config, block)
        a_block = Block(
            raw_text=block.raw_text,
            text=a_part,
            speaker_id=block.speaker_id,
            speaker_name=block.speaker_name,
            speaker_role=block.speaker_role,
            block_type=BlockType.ANSWER,
            words=list(block.words),
            meta={**block.meta, "split_from_answer": True},
        )
        q_block = Block(
            raw_text=block.raw_text,
            text=continuation,
            speaker_id=examiner_id,
            speaker_name=examiner_name,
            block_type=followup_type,
            words=[],
            meta={
                **block.meta,
                "split_followup_question": followup_type == BlockType.QUESTION,
                "split_followup_continuation": followup_type == BlockType.COLLOQUY,
                "split_followup_question_from_answer": True,
            },
        )
        new_blocks.extend([a_block, q_block])

    return new_blocks


def split_answer_prefixed_questions(blocks: List[Block], job_config: Any = None) -> List[Block]:
    """
    Split a QUESTION block whose first sentence(s) are a misattributed witness
    answer (e.g. "I will. Would you state your name?").

    Mirror image of `split_inline_questions_from_answers`: it handles blocks
    classified as QUESTION (because they end with '?') even though they
    actually begin with a witness reply that bled in from the previous turn.

    Uses ANSWER_PREFIX_TOKENS (broader than ANSWER_TOKENS) and the same
    option-d cumulative-prefix logic as `_extract_answer_and_continuation`,
    so multi-sentence answers like "Yes. I will." are kept together when the
    actual question begins later in the block.
    """
    new_blocks: List[Block] = []

    for block in blocks:
        if block.block_type != BlockType.QUESTION:
            new_blocks.append(block)
            continue

        text = (block.text or "").strip()
        if not text:
            new_blocks.append(block)
            continue
        lowered = text.lower()
        if not lowered.startswith(ANSWER_PREFIX_TOKENS):
            new_blocks.append(block)
            continue

        parts = SENTENCE_END_RE.split(text)
        if len(parts) < 2:
            new_blocks.append(block)
            continue

        last_answer_idx = 0
        for i in range(1, len(parts)):
            if _continues_answer(parts[i]):
                last_answer_idx = i
            else:
                break

        if last_answer_idx >= len(parts) - 1:
            # Nothing left for the question — leave block alone.
            new_blocks.append(block)
            continue

        a_text = "  ".join(p.strip() for p in parts[: last_answer_idx + 1] if p.strip())
        q_text = "  ".join(p.strip() for p in parts[last_answer_idx + 1 :] if p.strip())
        if not a_text or not q_text:
            new_blocks.append(block)
            continue
        if not _looks_like_question_text(q_text):
            new_blocks.append(block)
            continue

        witness_id, witness_name = _witness_identity(job_config, block)
        a_block = Block(
            raw_text=block.raw_text,
            text=a_text,
            speaker_id=witness_id,
            speaker_name=witness_name,
            block_type=BlockType.ANSWER,
            words=[],
            meta={**block.meta, "split_from_answer_prefixed_question": True},
        )
        q_block = Block(
            raw_text=block.raw_text,
            text=q_text,
            speaker_id=block.speaker_id,
            speaker_name=block.speaker_name,
            speaker_role=block.speaker_role,
            block_type=BlockType.QUESTION,
            words=list(block.words),
            meta={**block.meta, "split_from_answer_prefixed_question_q": True},
        )
        new_blocks.extend([a_block, q_block])

    return new_blocks


def _merge_orphaned_continuations(blocks: List[Block]) -> List[Block]:
    """
    Merge a tiny continuation block into the preceding same-speaker block.
    Handles Deepgram pause fragmentation.
    """
    if not blocks:
        return blocks

    result = [blocks[0]]
    mergeable_types = (BlockType.QUESTION, BlockType.ANSWER, BlockType.COLLOQUY)

    for block in blocks[1:]:
        prev = result[-1]
        word_count = len((block.text or "").split())
        same_speaker = prev.speaker_id == block.speaker_id
        same_type = prev.block_type == block.block_type
        is_tiny = word_count <= TINY_CONTINUATION_WORD_COUNT
        is_mergeable = block.block_type in mergeable_types

        # Filler-only blocks ("Uh-huh.", "Mm-hmm.") are standalone testimony.
        if _FILLER_ONLY_RE.match((block.text or "").strip()):
            result.append(block)
            continue

        if block.block_type == BlockType.ANSWER:
            block_words = {
                w.strip('.,!?').lower()
                for w in (block.text or "").split()
            }
            if block_words & STANDALONE_ANSWER_WORDS:
                result.append(block)
                continue

        # Don't merge into a previous block that is already a complete
        # sentence — the tiny block is a separate utterance, not a
        # continuation. ("I'm done." + "You're sure?" must stay separate.)
        prev_is_complete = (prev.text or "").rstrip()[-1:] in ".?!"

        if (
            same_speaker
            and same_type
            and is_tiny
            and is_mergeable
            and not prev_is_complete
        ):
            _log.debug(
                "[QA_FIXER] Merged continuation: %r + %r",
                prev.text[-40:], block.text[:40],
            )
            merged = Block(
                raw_text=((prev.raw_text or "") + " " + (block.raw_text or "")).strip(),
                text=((prev.text or "").rstrip() + " " + (block.text or "").lstrip()).strip(),
                speaker_id=prev.speaker_id,
                speaker_name=prev.speaker_name,
                speaker_role=prev.speaker_role,
                block_type=prev.block_type,
                words=list(prev.words) + list(block.words),
                flags=list(prev.flags),
                meta={**prev.meta, "merged_continuation": True},
            )
            result[-1] = merged
        else:
            result.append(block)
    return result


def _remove_near_duplicate_blocks(blocks: List[Block]) -> List[Block]:
    """
    Remove near-duplicate consecutive blocks from chunk overlap artifacts.
    """
    if not blocks:
        return blocks

    result = [blocks[0]]
    for block in blocks[1:]:
        prev = result[-1]
        if prev.block_type != block.block_type or prev.speaker_id != block.speaker_id:
            result.append(block)
            continue

        prev_words = set(TOKEN_RE.findall((prev.text or "").lower()))
        curr_words = set(TOKEN_RE.findall((block.text or "").lower()))
        if not prev_words or not curr_words:
            result.append(block)
            continue

        union = prev_words | curr_words
        similarity = len(prev_words & curr_words) / len(union) if union else 0.0
        prev_start = (prev.meta or {}).get("start")
        curr_start = (block.meta or {}).get("start")
        try:
            time_diff = abs(float(curr_start) - float(prev_start))
        except (TypeError, ValueError):
            time_diff = None

        if (
            similarity >= NEAR_DUPLICATE_SIMILARITY_THRESHOLD
            and time_diff is not None
            and time_diff < NEAR_DUPLICATE_TIME_WINDOW_S
        ):
            if len(block.text or "") > len(prev.text or ""):
                result[-1] = block
        else:
            result.append(block)
    return result


def fix_qa_structure(blocks: List[Block], job_config: Any = None) -> List[Block]:
    """
    Apply Q/A structural repairs in priority order.
    """
    input_count = len(blocks)
    _log.debug("[QA_FIXER] start - %d blocks", input_count)

    blocks = _merge_reporter_preamble_blocks(blocks)
    _log.debug("[QA_FIXER] after reporter preamble merge - %d blocks", len(blocks))

    before = len(blocks)
    blocks = split_inline_answers(blocks, job_config=job_config)
    _log.debug("[QA_FIXER] after 1st inline-answer split - %d->%d", before, len(blocks))

    before = len(blocks)
    blocks = split_inline_questions_from_answers(blocks, job_config=job_config)
    _log.debug("[QA_FIXER] after question-from-answer split - %d->%d", before, len(blocks))

    before = len(blocks)
    blocks = split_inline_answers(blocks, job_config=job_config)
    _log.debug("[QA_FIXER] after 2nd inline-answer split - %d->%d", before, len(blocks))

    before = len(blocks)
    blocks = split_answer_prefixed_questions(blocks, job_config=job_config)
    _log.debug("[QA_FIXER] after answer-prefixed-Q split - %d->%d", before, len(blocks))

    before = len(blocks)
    blocks = _merge_orphaned_continuations(blocks)
    _log.debug("[QA_FIXER] after orphan merge - %d->%d", before, len(blocks))

    before = len(blocks)
    blocks = _remove_near_duplicate_blocks(blocks)
    _log.debug(
        "[QA_FIXER] after near-dup removal - %d->%d (removed %d)",
        before, len(blocks), before - len(blocks),
    )

    _log.debug(
        "[QA_FIXER] complete - %d -> %d blocks (net %+d)",
        input_count, len(blocks), len(blocks) - input_count,
    )
    return blocks
