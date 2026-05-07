"""Detector for merged multi-exchange utterances.

This module currently exposes ``is_merged_utterance``: a deterministic
classifier that returns True when an utterance text shows signals of
multiple Q/A turns concatenated by Deepgram diarization. AI-driven
splitting will be added in a follow-up step; this module is the
detection-only foundation.
"""

from __future__ import annotations

import re

from .qa_fixer import QUESTION_WORDS, STANDALONE_ANSWER_WORDS

_MIN_BLOCK_WORDS = 15
_LONG_BLOCK_WORDS = 60
_LONG_BLOCK_MIN_SENTENCE_ENDS = 2
_QMARK_MIN_SEPARATION = 5

_QUESTION_WORD_AFTER_SENTENCE_END_RE = re.compile(
    r"[.!?]\s+(?:" + "|".join(QUESTION_WORDS) + r")\b",
    re.IGNORECASE,
)

_ANSWER_WORD_MID_BLOCK_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in STANDALONE_ANSWER_WORDS) + r")\b"
    r"\s*[.!?]\s+\S",
    re.IGNORECASE,
)

_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")


def _has_separated_question_marks(text: str) -> bool:
    """True when the text contains 2+ ``?`` characters separated by
    at least ``_QMARK_MIN_SEPARATION`` non-``?`` characters."""
    positions = [i for i, c in enumerate(text) if c == "?"]
    if len(positions) < 2:
        return False
    for i in range(len(positions) - 1):
        if positions[i + 1] - positions[i] > _QMARK_MIN_SEPARATION:
            return True
    return False


def _has_question_word_after_sentence_end(text: str) -> bool:
    return bool(_QUESTION_WORD_AFTER_SENTENCE_END_RE.search(text))


def _has_answer_word_mid_block(text: str) -> bool:
    return bool(_ANSWER_WORD_MID_BLOCK_RE.search(text))


def _is_long_block_with_sentence_ends(text: str, word_count: int) -> bool:
    if word_count < _LONG_BLOCK_WORDS:
        return False
    sentence_ends = len(_SENTENCE_END_RE.findall(text))
    return sentence_ends >= _LONG_BLOCK_MIN_SENTENCE_ENDS


def is_merged_utterance(text: str) -> bool:
    """Return True when the utterance shows signals of multiple Q/A
    exchanges concatenated by Deepgram diarization.

    Rules (any one fires, after the length floor):
      0. Word count must be at least ``_MIN_BLOCK_WORDS`` (15). Below
         this floor, never flag.
      1. Two or more ``?`` characters separated by at least
         ``_QMARK_MIN_SEPARATION`` (5) non-``?`` characters.
      2. Sentence-ending punctuation followed by a known question word.
      3. A standalone-answer word mid-block, followed by sentence-ending
         punctuation, followed by more substantive text.
      4. Long block (>= 60 words) containing at least 2 sentence-ending
         punctuation marks.

    Pure-rule, deterministic, silent. No AI, no logging, no mutation.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    word_count = len(stripped.split())
    if word_count < _MIN_BLOCK_WORDS:
        return False
    if _has_separated_question_marks(stripped):
        return True
    if _has_question_word_after_sentence_end(stripped):
        return True
    if _has_answer_word_mid_block(stripped):
        return True
    if _is_long_block_with_sentence_ends(stripped, word_count):
        return True
    return False


# ─── AI splitter ──────────────────────────────────────────────────────────────


import hashlib  # noqa: E402  — kept here to localize splitter dependencies
import json     # noqa: E402
import logging  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

try:
    from anthropic import Anthropic  # noqa: E402
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore[assignment]

from config import ANTHROPIC_API_KEY  # noqa: E402

# Resolve AI_MODEL from the same place clean_format/formatter.py imports it.
# If this import path is wrong, STOP and report — do not guess a model name.
from core.config import AI_MODEL  # noqa: E402

logger = logging.getLogger(__name__)

_MAX_TOKENS = 4096
_DEFAULT_MAX_AI_CALLS = 200

_SPLIT_SYSTEM_PROMPT = """You split court reporter deposition utterances that have been incorrectly concatenated by automatic diarization. The input is a single utterance string that may contain multiple sequential turns (questions and answers from different speakers, merged into one block). Your job is to split it back into separate utterances when possible.

Output rules (strict):

1. Output ONLY a JSON array. No prose, no markdown fences, no commentary.

2. Each element is an object with exactly two keys: "text" (string) and "type" (one of "question", "answer", "colloquy").

3. The space-joined concatenation of all "text" values MUST equal the original input modulo whitespace. Do NOT add words. Do NOT remove words. Do NOT paraphrase. Do NOT correct grammar. Do NOT change capitalization beyond what is in the original.

4. Preserve all filler words (uh, um, you know, etc.) and verbatim speech. Court reporters require verbatim accuracy — fillers are evidence.

5. If you cannot identify clear turn boundaries (the text is one continuous statement, or it's pre-deposition pleasantries, or it's a long answer with embedded asides), return a SINGLE-element array containing the original text typed as "colloquy". Do not invent boundaries.

The transcript is from a Texas legal deposition. Q is typically the examining attorney; A is typically the witness. "Colloquy" covers anything that isn't a clean Q or A: videographer announcements, off-record statements, pre-deposition introductions, objections, sidebars."""


@dataclass
class SplitterMetadata:
    original_count: int = 0
    split_count: int = 0
    flagged_count: int = 0
    ai_calls: int = 0
    cache_hits: int = 0
    validation_failures: int = 0
    skipped_over_cap: int = 0
    model: str = ""


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _normalize_for_validation(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _validate_splits(original_text: str, splits) -> tuple[bool, str]:
    if not isinstance(splits, list):
        return False, "splits is not a list"
    if not splits:
        return False, "splits is empty"
    for i, item in enumerate(splits):
        if not isinstance(item, dict):
            return False, f"split[{i}] is not a dict"
        if "text" not in item or "type" not in item:
            return False, f"split[{i}] is missing 'text' or 'type'"
        if item["type"] not in ("question", "answer", "colloquy"):
            return False, f"split[{i}] has invalid type {item['type']!r}"
        if not isinstance(item["text"], str) or not item["text"].strip():
            return False, f"split[{i}] has empty text"
    concat = " ".join(s["text"] for s in splits)
    if _normalize_for_validation(concat) != _normalize_for_validation(original_text):
        return False, "concatenated splits do not match original"
    return True, "ok"


def _strip_code_fences(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _call_ai_split(client, text: str) -> list[dict] | None:
    """Single AI call. Returns the parsed list on success, None on any failure."""
    try:
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SPLIT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        parts = []
        for item in getattr(response, "content", []) or []:
            t = getattr(item, "text", "")
            if t:
                parts.append(t)
        raw = "\n".join(parts)
        if not raw.strip():
            logger.warning("AI returned empty response")
            return None
        cleaned = _strip_code_fences(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("AI returned invalid JSON: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 — this is the AI integration boundary
        logger.warning("AI call failed: %s", exc)
        return None


def _utterance_text(utt: dict) -> str:
    return ((utt.get("transcript") if isinstance(utt, dict) else None)
            or (utt.get("text") if isinstance(utt, dict) else None)
            or "").strip()


def split_utterances(
    utterances: list[dict],
    *,
    max_ai_calls: int = _DEFAULT_MAX_AI_CALLS,
    client=None,
) -> tuple[list[dict], SplitterMetadata]:
    """Split merged utterances using AI, with deterministic detection.

    Args:
        utterances: list of utterance dicts (production shape — must
            have ``transcript`` or ``text``).
        max_ai_calls: hard cap on AI calls per invocation. After the
            cap, remaining flagged utterances pass through unchanged
            and ``skipped_over_cap`` reflects the count.
        client: optional pre-constructed Anthropic client (for tests).
            When ``None``, the function constructs one from
            ``ANTHROPIC_API_KEY``.

    Returns:
        ``(split_utterances, metadata)`` — output preserves order;
        non-flagged utterances pass through unchanged; flagged ones
        are either replaced by their splits or pass through if AI
        failed or the cost cap was hit.

    Raises:
        RuntimeError: if ``client`` is None and ``ANTHROPIC_API_KEY``
            is not set, or if the ``anthropic`` package is not
            installed.
    """
    if client is None:
        if Anthropic is None:
            raise RuntimeError("anthropic package is not installed")
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

    cache: dict[str, list[dict]] = {}
    meta = SplitterMetadata(
        original_count=len(utterances),
        model=AI_MODEL,
    )
    output: list[dict] = []

    for utt in utterances:
        text = _utterance_text(utt)
        if not text or not is_merged_utterance(text):
            output.append(utt)
            continue

        meta.flagged_count += 1
        h = _content_hash(text)

        if h in cache:
            meta.cache_hits += 1
            splits = cache[h]
        else:
            if meta.ai_calls >= max_ai_calls:
                meta.skipped_over_cap += 1
                output.append(utt)
                continue
            meta.ai_calls += 1
            ai_result = _call_ai_split(client, text)
            if ai_result is None:
                meta.validation_failures += 1
                output.append(utt)
                continue
            ok, reason = _validate_splits(text, ai_result)
            if not ok:
                meta.validation_failures += 1
                logger.warning("AI split validation failed: %s", reason)
                output.append(utt)
                continue
            cache[h] = ai_result
            splits = ai_result

        # If AI returned a single-element array, treat as a no-op pass-through
        # (the prompt instructs the model to do this when boundaries are unclear).
        if len(splits) == 1:
            output.append(utt)
            continue

        for s in splits:
            new_utt = dict(utt) if isinstance(utt, dict) else {}
            if "transcript" in new_utt:
                new_utt["transcript"] = s["text"]
            new_utt["text"] = s["text"]
            new_utt["_split_source"] = "ai"
            new_utt["_split_type_hint"] = s["type"]
            output.append(new_utt)

    meta.split_count = len(output)
    return output, meta
