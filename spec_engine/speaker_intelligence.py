"""
spec_engine/speaker_intelligence.py

Deterministic post-mapping speaker-role refinement and simple Q/A sequence
repair. This layer enhances the existing speaker mapping without replacing it.
"""

from __future__ import annotations

import copy
import re
from typing import Any, List

from .models import Block
from .speaker_resolver import (
    ROLE_ATTORNEY,
    ROLE_EXAMINING_ATTORNEY,
    ROLE_OPPOSING_COUNSEL,
    ROLE_REPORTER,
    ROLE_UNKNOWN,
    ROLE_WITNESS,
)


SHORT_ANSWERS = {
    "yes.",
    "no.",
    "correct.",
    "okay.",
    "uh-huh.",
}
WITNESS_ANSWER_PREFIXES = (
    "yes",
    "no",
    "correct",
    "right",
    "yeah",
    "yep",
    "yup",
    "nope",
    "nah",
    "uh-huh",
    "uh-uh",
    "mm-hmm",
    "mhmm",
    "i ",
    "i'm",
    "i am",
    "i was",
    "i have",
    "i had",
    "i did",
    "i do",
    "i don't",
    "i did not",
    "i have not",
    "i can",
    "i could",
    "i will",
    "i would",
    "my ",
    "we ",
    "we're",
    "we are",
    "our ",
    "it's ",
    "it is ",
    "there was",
    "there were",
)
NON_WITNESS_SEQUENCE_PREFIXES = (
    "okay",
    "all right",
    "alright",
    "let me",
    "let's",
    "so ",
    "and so",
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
    "can",
    "could",
    "would",
    "will",
    "have",
    "has",
)
OATH_MARKERS = (
    "raise your right hand",
    "do you swear",
    "under penalty of perjury",
)
INLINE_QA_RE = re.compile(
    r"^(?P<question>.+?\?)\s+(?P<answer>(?:Yes|No|Correct|Okay|Uh-huh)\.)$",
    re.IGNORECASE,
)
PREFIX_QUESTION_RE = re.compile(r"^(?P<prefix>.+?[.!])\s+(?P<question>[^?]+\?)$")
MAX_SEQUENCE_ANSWER_WORDS = 18


def _speaker_map_from_job(job_config: Any) -> dict[int, str]:
    if hasattr(job_config, "speaker_map"):
        raw = getattr(job_config, "speaker_map", {}) or {}
    elif isinstance(job_config, dict):
        raw = job_config.get("speaker_map", {}) or {}
    else:
        raw = {}

    result: dict[int, str] = {}
    for key, value in raw.items():
        try:
            result[int(key)] = str(value or "")
        except (TypeError, ValueError):
            continue
    return result


def _job_value(job_config: Any, key: str, default=None):
    if hasattr(job_config, key):
        return getattr(job_config, key, default)
    if isinstance(job_config, dict):
        return job_config.get(key, default)
    return default


def _witness_label(job_config: Any) -> str:
    witness_id = _job_value(job_config, "witness_id")
    speaker_map = _speaker_map_from_job(job_config)
    return speaker_map.get(witness_id, "THE WITNESS")


def _examining_label(job_config: Any) -> str:
    attorney_id = _job_value(job_config, "examining_attorney_id")
    speaker_map = _speaker_map_from_job(job_config)
    return speaker_map.get(attorney_id, "COUNSEL")


def _looks_like_question(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    return normalized.endswith("?") or any(lowered.startswith(word + " ") for word in QUESTION_WORDS)


def _is_short_answer(text: str) -> bool:
    return (text or "").strip().lower() in SHORT_ANSWERS


def _is_attorney_role(role: str) -> bool:
    return role in {ROLE_ATTORNEY, ROLE_EXAMINING_ATTORNEY, ROLE_OPPOSING_COUNSEL}


def _add_audit(block: Block, action: str, detail: str) -> None:
    block.meta.setdefault("speaker_intelligence", []).append(
        {
            "action": action,
            "detail": detail,
        }
    )


def _add_verification_flag(block: Block, detail: str) -> None:
    flags = block.meta.setdefault("verification_flags", [])
    if detail not in flags:
        flags.append(detail)


def _looks_like_witness_answer(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized or _looks_like_question(normalized):
        return False

    lowered = normalized.lower()
    if any(lowered.startswith(prefix) for prefix in NON_WITNESS_SEQUENCE_PREFIXES):
        return False
    if any(lowered.startswith(prefix) for prefix in WITNESS_ANSWER_PREFIXES):
        return True
    return len(normalized.split()) <= MAX_SEQUENCE_ANSWER_WORDS and normalized[0].isupper()


def infer_speaker_roles(blocks: List[Block], job_config: Any) -> List[Block]:
    configured_map = _speaker_map_from_job(job_config)
    previous_role = ""

    for block in blocks:
        text = (block.text or "").strip()
        if not text:
            continue

        if block.speaker_id in configured_map:
            previous_role = getattr(block, "speaker_role", "") or previous_role
            continue

        existing_role = getattr(block, "speaker_role", "") or ""
        if existing_role and existing_role != ROLE_UNKNOWN:
            previous_role = existing_role
            continue

        lowered = text.lower()
        if any(marker in lowered for marker in OATH_MARKERS):
            block.speaker_role = ROLE_REPORTER
            block.speaker_name = "THE REPORTER"
            _add_audit(block, "infer_role", "oath_detection")
        elif _is_short_answer(text):
            block.speaker_role = ROLE_WITNESS
            block.speaker_name = _witness_label(job_config)
            _add_audit(block, "infer_role", "short_answer")
        elif _looks_like_question(text):
            block.speaker_role = ROLE_ATTORNEY
            block.speaker_name = _examining_label(job_config)
            _add_audit(block, "infer_role", "question_detection")
        elif _is_attorney_role(previous_role) and _looks_like_witness_answer(text):
            block.speaker_role = ROLE_WITNESS
            block.speaker_name = _witness_label(job_config)
            block.speaker_id = _job_value(job_config, "witness_id", block.speaker_id)
            _add_audit(block, "infer_role", "sequence_after_question")
            _add_verification_flag(
                block,
                "speaker role inferred as witness from Q/A sequence — verify from audio",
            )
        elif previous_role == ROLE_WITNESS and _looks_like_question(text):
            block.speaker_role = ROLE_ATTORNEY
            block.speaker_name = _examining_label(job_config)
            block.speaker_id = _job_value(job_config, "examining_attorney_id", block.speaker_id)
            _add_audit(block, "infer_role", "sequence_after_answer")
            _add_verification_flag(
                block,
                "speaker role inferred as counsel from Q/A sequence — verify from audio",
            )

        if getattr(block, "speaker_role", "") and getattr(block, "speaker_role", "") != ROLE_UNKNOWN:
            previous_role = block.speaker_role

    return blocks


def enforce_qa_sequence(blocks: List[Block], job_config: Any) -> List[Block]:
    result: List[Block] = []

    for block in blocks:
        text = (block.text or "").strip()
        match = INLINE_QA_RE.match(text)
        if match:
            prefix_block = None
            question_text = match.group("question").strip()
            prefix_match = PREFIX_QUESTION_RE.match(question_text)
            if prefix_match:
                prefix_block = copy.deepcopy(block)
                prefix_block.text = prefix_match.group("prefix").strip()
                _add_audit(prefix_block, "split_inline_qa", "prefix")
                question_text = prefix_match.group("question").strip()

            question_block = copy.deepcopy(block)
            answer_block = copy.deepcopy(block)

            question_block.text = question_text
            question_block.speaker_role = ROLE_ATTORNEY
            question_block.speaker_name = _examining_label(job_config)
            question_block.speaker_id = _job_value(job_config, "examining_attorney_id", question_block.speaker_id)
            _add_audit(question_block, "split_inline_qa", "question")

            answer_block.text = match.group("answer").strip()
            answer_block.speaker_role = ROLE_WITNESS
            answer_block.speaker_name = _witness_label(job_config)
            answer_block.speaker_id = _job_value(job_config, "witness_id", answer_block.speaker_id)
            _add_audit(answer_block, "split_inline_qa", "answer")

            if prefix_block is not None:
                result.append(prefix_block)
            result.extend([question_block, answer_block])
            continue

        if result:
            previous = result[-1]
            previous_role = getattr(previous, "speaker_role", "") or ""
            current_role = getattr(block, "speaker_role", "") or ""
            if (
                _is_attorney_role(previous_role)
                and current_role != ROLE_WITNESS
                and _looks_like_witness_answer(text)
            ):
                block = copy.deepcopy(block)
                block.speaker_role = ROLE_WITNESS
                block.speaker_name = _witness_label(job_config)
                block.speaker_id = _job_value(job_config, "witness_id", block.speaker_id)
                _add_audit(block, "enforce_qa_sequence", "attorney_to_witness_sequence_answer")
                _add_verification_flag(
                    block,
                    "speaker role inferred as witness from Q/A sequence — verify from audio",
                )
            elif (
                previous_role == ROLE_WITNESS
                and not _is_attorney_role(current_role)
                and _looks_like_question(text)
            ):
                block = copy.deepcopy(block)
                block.speaker_role = ROLE_ATTORNEY
                block.speaker_name = _examining_label(job_config)
                block.speaker_id = _job_value(job_config, "examining_attorney_id", block.speaker_id)
                _add_audit(block, "enforce_qa_sequence", "witness_to_attorney_sequence_question")
                _add_verification_flag(
                    block,
                    "speaker role inferred as counsel from Q/A sequence — verify from audio",
                )

        result.append(block)

    return result
