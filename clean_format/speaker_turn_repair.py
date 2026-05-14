"""Conservative deterministic speaker-turn repair for raw transcripts.

This module runs at the very start of ``clean_format.formatter.format_transcript``,
BEFORE low-confidence marker injection and BEFORE the Anthropic cleanup
call. It identifies single Deepgram utterances that obviously fuse a
question and an answer (or two consecutive questions, or a question
followed by a witness narrative), and splits them into separate
transcript blocks so the downstream cleanup pass has cleaner boundaries
to work with.

Design constraints (per ``CLAUDE.md`` and the investigation charter):

- **Deterministic only.** No model calls, no probabilistic
  attribution, no heuristic guesses about WHO the witness is.
- **Conservative.** Every rule has minimum-length and structural
  guards designed to prefer FALSE NEGATIVES over FALSE POSITIVES.
  Missing a bad merge is acceptable; splitting valid testimony is not.
- **Speaker label preserved.** When a block is split, both resulting
  segments inherit the original Deepgram speaker label. The repair
  inserts a structural boundary; it does NOT invent a new speaker.
  Anthropic / spec_engine classifier downstream may still re-type
  the segments as Q. / A. based on content, but no part of this
  module makes that claim.
- **Provenance preserved.** ``SpeakerTurnRepairResult`` records the
  original text and the reason for the split, suitable for offline
  audit.
- **No DOCX, no Anthropic, no Deepgram coupling.** Pure text
  transformation.
- **Idempotent.** Re-running on an already-repaired transcript
  produces the same output (no rule fires on the already-split
  segments).

Rule summary:

- ``RULE_A_EMBEDDED_SHORT_ANSWER`` — block ends with a question mark
  followed by a canonical short witness answer ("Yes.", "No.",
  "Correct.", etc.). Split between the two.
- ``RULE_B_RAPID_QA_CASCADE`` — block contains
  ``<question>? <short answer>. <question>?``. Split into three.
- ``RULE_C_QUESTION_TO_ANSWER`` — block contains ``<question>?``
  followed by a first-person witness sentence opener ("I'm", "I am",
  "My practice", etc.). Split into two.
- ``RULE_D_MULTI_QUESTION`` — block contains two consecutive
  interrogative sentences from the same speaker. Split between them.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SpeakerTurnRepairResult:
    """Audit record for one block submitted to the repair pipeline.

    Attributes
    ----------
    original_text:
        The exact body of the input block (without the speaker label),
        unchanged. Required by the legal-verbatim provenance contract.
    repaired_segments:
        List of body texts. Length 1 means "no repair fired" — the
        single element equals ``original_text``. Length 2+ means a
        rule produced a structural split.
    repair_applied:
        ``True`` iff a rule fired and produced ``len(repaired_segments) > 1``.
    repair_reason:
        Identifier of the rule that fired. Empty string when no repair.
    confidence:
        ``"high"`` / ``"medium"`` / ``"low"`` — coarse self-rating of
        how strong the structural signal was. Today every rule emits
        ``"high"`` because rules only fire on tight patterns; the field
        exists for future rules that may want to expose uncertainty.
    metadata:
        Free-form dict carrying e.g. the speaker label that the
        segments inherit, the question count, etc. For logging and
        offline audit only.
    """

    original_text: str
    repaired_segments: list[str]
    repair_applied: bool
    repair_reason: str = ""
    confidence: str = "high"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants — conservative patterns
# ---------------------------------------------------------------------------

# Canonical witness short-answer tokens, case-insensitive at use site.
# Kept narrow: only the words the spec calls out plus a small,
# well-established legal-deposition vocabulary. Filler-like
# "okay"/"alright" are intentionally excluded — they're often
# attorney conversational fillers, not witness answers.
_SHORT_ANSWER_TOKENS = (
    "yes",
    "no",
    "correct",
    "right",
    "uh-huh",
    "uh huh",
    "mm-hmm",
    "i do",
    "i did",
    "i have",
    "i was",
    "i don't",
)

# First-person witness sentence openers used by Rule C. Conservative —
# every phrase must be unambiguous about who is speaking (a witness in
# direct testimony). Excluded: bare "I think" (attorneys say this too),
# "We talked" (could be either party).
_WITNESS_OPENERS = (
    "I'm",
    "I am",
    "I have",
    "I had",
    "I was",
    "I treat",
    "I performed",
    "I do",
    "I did",
    "I don't",
    "I didn't",
    "I haven't",
    "My office",
    "My practice",
    "My patients",
    "We do",
    "We have",
    "We did",
)

# Interrogative sentence-start words for Rule D (multi-question split).
# A bare "if/and/but" start would be too loose; we require classic
# question-starters.
_QUESTION_STARTERS = (
    "Who",
    "What",
    "When",
    "Where",
    "Why",
    "How",
    "Do",
    "Did",
    "Does",
    "Is",
    "Are",
    "Was",
    "Were",
    "Can",
    "Could",
    "Would",
    "Will",
    "Have",
    "Has",
    "Had",
    "Could",
    "Should",
)

# Minimum word count for the "question portion" of any rule. Anything
# shorter is too small to be confident it really was a question; we
# prefer to leave it merged than to split a tiny fragment off.
_MIN_QUESTION_WORDS = 3

# Minimum word count for the "post-question" body in Rule C. A bare
# "I'm." is too short to be a confident answer — could be a stutter.
_MIN_ANSWER_WORDS_RULE_C = 2

# Repair reason constants — referenced by tests, logs, and the audit
# report. Kept stable so external code can pattern-match on them.
RULE_A = "RULE_A_EMBEDDED_SHORT_ANSWER"
RULE_B = "RULE_B_RAPID_QA_CASCADE"
RULE_C = "RULE_C_QUESTION_TO_ANSWER_SHIFT"
RULE_D = "RULE_D_MULTI_QUESTION"

# ---------------------------------------------------------------------------
# Block parsing helpers
# ---------------------------------------------------------------------------

# Match "Speaker 0: text" or "Speaker 0:\ttext" or "Mr. Smith: text" at
# the start of a block. The colon is required; everything before the
# first colon is treated as the label.
_BLOCK_LABEL_RE = re.compile(r"^(?P<label>[^:\n]{1,80}):\s*(?P<body>.*)$", re.DOTALL)


def _parse_block(block: str) -> tuple[str, str]:
    """Return ``(speaker_label, body)`` for a single transcript block.

    If the block lacks a recognizable ``<label>:`` prefix, the label
    is the empty string and the body is the full block. Repair rules
    still run on the body; the emitter just won't have a label to
    attach to the resulting segments and will re-emit them as raw
    paragraphs.
    """
    block = block.strip()
    match = _BLOCK_LABEL_RE.match(block)
    if not match:
        return "", block
    label = match.group("label").strip()
    body = match.group("body").strip()
    return label, body


def _format_block(speaker_label: str, body: str) -> str:
    """Reconstitute a block from a label and a body."""
    body = (body or "").strip()
    if not body:
        return ""
    if not speaker_label:
        return body
    return f"{speaker_label}: {body}"


# ---------------------------------------------------------------------------
# Rule A — embedded short answer
# ---------------------------------------------------------------------------

# Match a block whose body ends with: <question text>? <SHORT_ANSWER>.
# Trailing whitespace allowed; nothing else after the short answer.
# The short-answer alternation is built dynamically so the constant
# above remains the single source of truth.
_RULE_A_SHORT_ANSWER_ALT = "|".join(
    re.escape(t) for t in sorted(_SHORT_ANSWER_TOKENS, key=len, reverse=True)
)
_RULE_A_RE = re.compile(
    r"^(?P<q>.+?\?)\s+(?P<a>(?:"
    + _RULE_A_SHORT_ANSWER_ALT
    + r"))\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _try_rule_a(body: str) -> SpeakerTurnRepairResult | None:
    """Detect ``<question>? <SHORT_ANSWER>.`` ending the entire body."""
    match = _RULE_A_RE.match(body)
    if not match:
        return None
    question = match.group("q").strip()
    answer_token = match.group("a").strip()

    if len(question.split()) < _MIN_QUESTION_WORDS:
        return None

    # Build the answer text canonically: capitalize first letter,
    # ensure trailing period. We don't paraphrase content; the
    # capitalization is a structural normalization, not a meaning
    # change.
    canonical_answer = answer_token[0].upper() + answer_token[1:].lower()
    if not canonical_answer.endswith("."):
        canonical_answer += "."

    return SpeakerTurnRepairResult(
        original_text=body,
        repaired_segments=[question, canonical_answer],
        repair_applied=True,
        repair_reason=RULE_A,
        confidence="high",
        metadata={
            "question_words": len(question.split()),
            "answer_token": answer_token.lower(),
        },
    )


# ---------------------------------------------------------------------------
# Rule B — rapid Q/A cascade
# ---------------------------------------------------------------------------

# Match ``<Q1>? <SHORT_ANSWER>. <Q2>...`` inside a single body. The trailing
# Q2 must (a) start with a question-starter or end with `?`, and (b) be
# at least _MIN_QUESTION_WORDS long. Anchored to the start so we don't
# fire mid-utterance accidentally.
_RULE_B_RE = re.compile(
    r"^(?P<q1>.+?\?)\s+"
    r"(?P<a>(?:"
    + _RULE_A_SHORT_ANSWER_ALT
    + r"))\.\s+"
    r"(?P<q2>[A-Z].+)$",
    re.IGNORECASE | re.DOTALL,
)


def _try_rule_b(body: str) -> SpeakerTurnRepairResult | None:
    match = _RULE_B_RE.match(body)
    if not match:
        return None

    question1 = match.group("q1").strip()
    answer_token = match.group("a").strip()
    rest = match.group("q2").strip()

    if len(question1.split()) < _MIN_QUESTION_WORDS:
        return None

    # The "rest" must itself look like a question — either it ends
    # with `?` or it starts with a canonical question-starter.
    rest_first_word = rest.split(maxsplit=1)[0].rstrip(",.;:")
    is_question_like = rest.endswith("?") or rest_first_word in _QUESTION_STARTERS
    if not is_question_like:
        return None

    if len(rest.split()) < _MIN_QUESTION_WORDS:
        return None

    canonical_answer = answer_token[0].upper() + answer_token[1:].lower() + "."

    return SpeakerTurnRepairResult(
        original_text=body,
        repaired_segments=[question1, canonical_answer, rest],
        repair_applied=True,
        repair_reason=RULE_B,
        confidence="high",
        metadata={
            "question1_words": len(question1.split()),
            "answer_token": answer_token.lower(),
            "question2_words": len(rest.split()),
        },
    )


# ---------------------------------------------------------------------------
# Rule C — question → answer shift (first-person witness opener)
# ---------------------------------------------------------------------------

# Match ``<Q>? <first-person witness sentence opener> <rest>``. The
# witness opener alternation is computed from the constant.
_RULE_C_OPENER_ALT = "|".join(
    re.escape(o) for o in sorted(_WITNESS_OPENERS, key=len, reverse=True)
)
_RULE_C_RE = re.compile(
    r"^(?P<q>.+?\?)\s+(?P<answer>(?:"
    + _RULE_C_OPENER_ALT
    + r")\b.*)$",
    re.DOTALL,
)


def _try_rule_c(body: str) -> SpeakerTurnRepairResult | None:
    match = _RULE_C_RE.match(body)
    if not match:
        return None

    question = match.group("q").strip()
    answer = match.group("answer").strip()

    if len(question.split()) < _MIN_QUESTION_WORDS:
        return None
    if len(answer.split()) < _MIN_ANSWER_WORDS_RULE_C:
        return None

    # Guard: don't fire if the post-question text is itself another
    # question (Rule D's job).
    if answer.rstrip().endswith("?"):
        return None

    # Guard: a leading "I'm sorry" is conversational, not testimony.
    lowered_answer = answer.lower()
    if lowered_answer.startswith(("i'm sorry", "i am sorry")):
        return None

    return SpeakerTurnRepairResult(
        original_text=body,
        repaired_segments=[question, answer],
        repair_applied=True,
        repair_reason=RULE_C,
        confidence="high",
        metadata={
            "question_words": len(question.split()),
            "answer_words": len(answer.split()),
            "answer_opener": answer.split(maxsplit=1)[0],
        },
    )


# ---------------------------------------------------------------------------
# Rule D — multi-question absorption
# ---------------------------------------------------------------------------

# Match ``<Q1>? <Q2>?`` — two consecutive same-speaker interrogatives.
# Q2 must start with a known question-starter to suppress false
# positives (e.g. a witness saying "I'm... a doctor. You know?" should
# NOT match).
_RULE_D_QUESTION_STARTERS_ALT = "|".join(
    re.escape(s) for s in _QUESTION_STARTERS
)
_RULE_D_RE = re.compile(
    r"^(?P<q1>.+?\?)\s+"
    r"(?P<q2>(?:" + _RULE_D_QUESTION_STARTERS_ALT + r")\b.+\?)\s*$",
    re.DOTALL,
)


def _try_rule_d(body: str) -> SpeakerTurnRepairResult | None:
    match = _RULE_D_RE.match(body)
    if not match:
        return None

    q1 = match.group("q1").strip()
    q2 = match.group("q2").strip()

    if len(q1.split()) < _MIN_QUESTION_WORDS:
        return None
    if len(q2.split()) < _MIN_QUESTION_WORDS:
        return None

    return SpeakerTurnRepairResult(
        original_text=body,
        repaired_segments=[q1, q2],
        repair_applied=True,
        repair_reason=RULE_D,
        confidence="high",
        metadata={
            "question1_words": len(q1.split()),
            "question2_words": len(q2.split()),
        },
    )


# ---------------------------------------------------------------------------
# Rule orchestrator
# ---------------------------------------------------------------------------

# Order matters: most specific patterns first. Rule B (3-split) is
# more specific than Rule A or D; Rule A (terminal short answer) is
# more specific than Rule C (first-person opener). We try them in
# descending specificity so a block that matches multiple rules
# produces the cleanest split.
_RULE_FUNCTIONS = (
    _try_rule_b,
    _try_rule_a,
    _try_rule_d,
    _try_rule_c,
)


def repair_block_body(body: str) -> SpeakerTurnRepairResult:
    """Apply rules in priority order; first match wins.

    ``body`` is the body text of a single transcript block (no
    speaker label prefix). Returns a ``SpeakerTurnRepairResult``
    whose ``repaired_segments`` is the single-element list
    ``[body]`` when no rule fires.
    """
    body = (body or "").strip()
    if not body:
        return SpeakerTurnRepairResult(
            original_text=body,
            repaired_segments=[],
            repair_applied=False,
        )

    for rule_fn in _RULE_FUNCTIONS:
        result = rule_fn(body)
        if result is not None:
            return result

    return SpeakerTurnRepairResult(
        original_text=body,
        repaired_segments=[body],
        repair_applied=False,
    )


# ---------------------------------------------------------------------------
# Whole-transcript driver
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TranscriptRepairSummary:
    """Aggregate audit data for a single transcript-level repair pass."""

    block_count: int = 0
    blocks_repaired: int = 0
    splits_emitted: int = 0
    rule_counts: dict[str, int] = field(default_factory=dict)
    records: list[SpeakerTurnRepairResult] = field(default_factory=list)


def repair_transcript_blocks(
    raw_text: str,
) -> tuple[str, TranscriptRepairSummary]:
    """Walk every double-newline-separated block and apply repair rules.

    Returns ``(repaired_text, summary)``. The repaired text preserves
    the original block ordering and speaker labels; only the
    structural boundaries inside merged blocks have changed.

    Empty input returns ``("", TranscriptRepairSummary())``.
    """
    summary = TranscriptRepairSummary()
    if not raw_text or not raw_text.strip():
        return "", summary

    out_blocks: list[str] = []
    for block in raw_text.split("\n\n"):
        block = block.strip("\n")
        if not block.strip():
            continue

        summary.block_count += 1
        speaker_label, body = _parse_block(block)
        result = repair_block_body(body)
        summary.records.append(result)

        if not result.repair_applied:
            out_blocks.append(_format_block(speaker_label, body))
            continue

        # Record the rule count.
        summary.blocks_repaired += 1
        summary.splits_emitted += len(result.repaired_segments) - 1
        summary.rule_counts[result.repair_reason] = (
            summary.rule_counts.get(result.repair_reason, 0) + 1
        )

        # Re-emit each segment with the SAME speaker label. The repair
        # never asserts a new speaker.
        for segment in result.repaired_segments:
            formatted = _format_block(speaker_label, segment)
            if formatted:
                out_blocks.append(formatted)

    repaired_text = "\n\n".join(out_blocks)
    return repaired_text, summary


def format_summary_log_line(summary: TranscriptRepairSummary) -> str:
    """Return a one-line ``[SPEAKER_REPAIR] …`` log string."""
    parts = [
        f"blocks={summary.block_count}",
        f"repairs={summary.blocks_repaired}",
        f"splits={summary.splits_emitted}",
    ]
    for rule, count in sorted(summary.rule_counts.items()):
        parts.append(f"{rule.lower()}={count}")
    return "[SPEAKER_REPAIR] " + " ".join(parts)
