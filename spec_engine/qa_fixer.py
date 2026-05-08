"""Q/A structural enforcement only for classified transcript blocks."""

from __future__ import annotations

import re

from .models import TranscriptBlock

_SPEAKER_IN_QA_RE = re.compile(
    r"^\s*(?:[A-Z][A-Z.\-'\s]+:|SPEAKER\s+\d+:|BY\s+[A-Z.\-'\s]+:)"
)
QUESTION_WORDS = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "did",
    "do",
    "does",
    "is",
    "are",
    "was",
    "were",
    "can",
    "could",
    "would",
    "will",
    "have",
    "has",
    "had",
    "please",
)
STANDALONE_ANSWER_WORDS = {
    "yes",
    "no",
    "yeah",
    "nope",
    "correct",
    "incorrect",
    "right",
    "wrong",
    "i do",
    "i did",
    "i didn't",
    "uh-huh",
    "nuh-uh",
    "okay",
    "ok",
}


def _directive_examiner_name(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("BY "):
        cleaned = cleaned[3:]
    return cleaned.rstrip(":").strip()


_FRAGMENT_MARKERS = (",.", ",", ";")
_MIN_WORDS_FOR_QUESTION_WORD_START = 4


def _is_likely_question(text: str) -> bool:
    """Return True only when ``text`` strongly looks like a complete question.

    Rules (all must hold):
      * Trimmed text is non-empty.
      * Trimmed text does NOT end with a fragment marker (``,`` ``,.`` ``;``).
      * Either:
          - Trimmed text ends with ``?``, OR
          - Trimmed lowercased text starts with a known question word AND has
            at least ``_MIN_WORDS_FOR_QUESTION_WORD_START`` words AND does not
            end with ``,``.

    Tighter than the prior implementation, which fired on EITHER an
    ends-with-``?`` test OR a starts-with-question-word test with no
    minimum length and no fragment-marker exclusion. The prior rule
    produced 19–22% false-question rates on real production transcripts.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if any(stripped.endswith(marker) for marker in _FRAGMENT_MARKERS):
        return False
    if stripped.endswith("?"):
        return True
    lower = stripped.lower()
    starts_with_q_word = any(
        lower == word or lower.startswith(word + " ") for word in QUESTION_WORDS
    )
    if not starts_with_q_word:
        return False
    word_count = len(stripped.split())
    return word_count >= _MIN_WORDS_FOR_QUESTION_WORD_START


def _is_likely_answer(
    text: str,
    prior_type: str | None,
    prior_speaker: str | None,
    current_speaker: str,
    current_classifier_type: str,
) -> bool:
    """Return True only when ``text`` strongly looks like an answer.

    Rules (all must hold):
      * The immediately prior emitted block's type was ``question``.
      * The prior emitted block's speaker is known and DIFFERS from the
        current block's speaker. Same-speaker continuations are not
        answers — they're the asker continuing to talk.
      * Either:
          - Trimmed lowercased text, with trailing sentence-ending
            punctuation stripped, is in ``STANDALONE_ANSWER_WORDS``
            (canonical bare answer like ``Yes.`` / ``No.`` / ``Correct.``), OR
          - The classifier originally typed this block as ``colloquy``
            AND ``_is_likely_question`` returns False on the text. This
            is the contextual-colloquy fallback: a witness's substantive
            response to a question (e.g. "Gilberto Rodriguez Cavazos.")
            doesn't match the bare-word set but is still semantically
            an answer when the speaker has changed and the text isn't
            itself a question.

    The speaker-change requirement is what prevents a question-asker's
    own follow-up text from being mistyped as an answer to their own
    question. The trailing-punctuation strip lives in the helper rather
    than in the constant: ``"Yes."``, ``"Yes"``, and ``"Yes!"`` all match
    the canonical ``"yes"`` entry without polluting the constant.

    The prior implementation accepted ``len(text.split()) <= 6`` as
    sufficient grounds for re-typing as ``answer``. That clause is
    replaced here by the speaker-change + contextual-colloquy rule,
    which captures the same "witness's short response after a question"
    intuition without typing every short colloquy line that happens to
    follow a question.
    """
    if prior_type != "question":
        return False
    if prior_speaker is None or current_speaker == prior_speaker:
        return False

    stripped = text.strip().lower().rstrip(".,!?;:")
    if stripped in STANDALONE_ANSWER_WORDS:
        return True

    if current_classifier_type == "colloquy" and not _is_likely_question(text):
        return True

    return False


def enforce_qa_sequence(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    """
    FINAL PASS: Enforce strict Q/A structure.

    This does NOT replace detection logic.
    It CORRECTS structure after detection.

    Re-typing rules (Step 2A — Path A tightening):
      * Pre-deposition gate: any non-``colloquy`` block opens the gate.
        Classifier-assigned ``oath``, ``directive``, ``question``, and
        ``answer`` all signal "we're past pre-deposition logistics."
        Until the gate opens, blocks pass through with their
        classifier-assigned type unchanged — preventing pre-deposition
        pleasantries ("Hello, can you hear us?") from being mistyped
        as testimony.
      * After the gate opens, ``_is_likely_question`` and
        ``_is_likely_answer`` decide re-typing with deterministic rules.
        Both helpers receive enough context (text + prior emitted type
        + prior emitted speaker + current speaker + current classifier
        type) to apply the speaker-change rule that distinguishes a
        witness's substantive answer from the asker's own continuation
        text. See those helpers for the exact criteria.

    Existing behaviors preserved:
      * ``directive`` and ``oath`` blocks pass through with no re-typing.
      * The back-merge of a detected ``answer`` into a prior ``question``
        when ``last_type != "question"`` is unchanged. (Currently
        unreachable in linear walks; preserved pending separate audit.)
    """
    fixed: list[TranscriptBlock] = []
    last_type: str | None = None
    prior_speaker: str | None = None
    seen_deposition_marker: bool = False

    for block in blocks:
        # Any non-colloquy classifier-assigned type opens the gate. This
        # covers production (oath/directive arrive first) and synthetic
        # test inputs that pre-classify question/answer from "\tQ.\t"
        # markers without an explicit oath/directive block.
        if block.type != "colloquy":
            seen_deposition_marker = True

        if block.type in {"directive", "oath"}:
            fixed.append(block)
            last_type = block.type
            prior_speaker = block.speaker
            continue

        normalized = block
        original_classifier_type = block.type

        if seen_deposition_marker:
            if _is_likely_question(block.text):
                normalized = TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type="question",
                    source_type=block.source_type,
                    examiner=block.examiner,
                )
            elif _is_likely_answer(
                block.text,
                last_type,
                prior_speaker,
                block.speaker,
                original_classifier_type,
            ):
                normalized = TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type="answer",
                    source_type=block.source_type,
                    examiner=block.examiner,
                )

        # Currently unreachable in linear walks; preserved pending separate audit.
        if normalized.type == "answer" and last_type != "question":
            if fixed and fixed[-1].type == "question":
                previous = fixed[-1]
                fixed[-1] = TranscriptBlock(
                    speaker=previous.speaker,
                    text=f"{previous.text} {normalized.text}".strip(),
                    type=previous.type,
                    source_type=previous.source_type,
                    examiner=previous.examiner,
                )
                last_type = fixed[-1].type
                prior_speaker = fixed[-1].speaker
                continue

        fixed.append(normalized)
        last_type = normalized.type
        prior_speaker = normalized.speaker

    return fixed


def enforce_structure(blocks: list[TranscriptBlock]) -> list[TranscriptBlock]:
    """Apply examiner tracking and structural safety checks."""
    current_examiner: str | None = None
    pending_question: TranscriptBlock | None = None
    fixed: list[TranscriptBlock] = []

    for block in blocks:
        if block.type == "directive":
            current_examiner = _directive_examiner_name(block.text)
            pending_question = None
            fixed.append(
                TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type=block.type,
                    source_type=block.source_type,
                    examiner=current_examiner,
                )
            )
            continue

        if block.type == "question":
            if pending_question is not None:
                if pending_question.speaker == block.speaker:
                    # Same-speaker continuation: merge into the prior Q.
                    # Realistic case — attorneys split a compound question
                    # across utterances; Deepgram diarization and the AI
                    # splitter both produce these. Different-speaker
                    # consecutive Qs still raise (genuine missing answer).
                    merged_text = (
                        f"{pending_question.text} {block.text}".strip()
                    )
                    merged = TranscriptBlock(
                        speaker=pending_question.speaker,
                        text=merged_text,
                        type="question",
                        source_type=pending_question.source_type,
                        examiner=pending_question.examiner,
                    )
                    fixed[-1] = merged
                    pending_question = merged
                    continue
                raise ValueError(
                    "No Q without A: encountered consecutive question blocks"
                )
            if _SPEAKER_IN_QA_RE.match(block.text):
                raise ValueError(
                    "No speaker text inside Q/A blocks: invalid question content"
                )
            fixed.append(
                TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type=block.type,
                    source_type=block.source_type,
                    examiner=current_examiner,
                )
            )
            # Track the appended block (with examiner attribution), not the
            # input block — same-speaker merges read pending_question.examiner.
            pending_question = fixed[-1]
            continue

        if block.type == "answer":
            if _SPEAKER_IN_QA_RE.match(block.text):
                raise ValueError(
                    "No speaker text inside Q/A blocks: invalid answer content"
                )
            pending_question = None
            fixed.append(
                TranscriptBlock(
                    speaker=block.speaker,
                    text=block.text,
                    type=block.type,
                    source_type=block.source_type,
                    examiner=current_examiner,
                )
            )
            continue

        pending_question = None
        fixed.append(
            TranscriptBlock(
                speaker=block.speaker,
                text=block.text,
                type=block.type,
                source_type=block.source_type,
                examiner=current_examiner,
            )
        )

    fixed = enforce_qa_sequence(fixed)

    # Pass 2: applies the same same-speaker-merge rule as pass 1, this
    # time to blocks whose types may have been changed by
    # enforce_qa_sequence's loose Q/A re-detection.
    pending_question: TranscriptBlock | None = None
    final_fixed: list[TranscriptBlock] = []
    for block in fixed:
        if block.type == "question":
            if pending_question is not None:
                if pending_question.speaker == block.speaker:
                    merged_text = (
                        f"{pending_question.text} {block.text}".strip()
                    )
                    merged = TranscriptBlock(
                        speaker=pending_question.speaker,
                        text=merged_text,
                        type="question",
                        source_type=pending_question.source_type,
                        examiner=pending_question.examiner,
                    )
                    final_fixed[-1] = merged
                    pending_question = merged
                    continue
                raise ValueError(
                    "No Q without A: encountered consecutive question blocks"
                )
            pending_question = block
            final_fixed.append(block)
        elif block.type == "answer":
            if pending_question is None:
                raise ValueError(
                    "No orphan answers: answer encountered without a prior question"
                )
            pending_question = None
            final_fixed.append(block)
        else:
            pending_question = None
            final_fixed.append(block)

    if pending_question is not None:
        raise ValueError(
            "No Q without A: transcript ended with an unanswered question"
        )

    return final_fixed
