"""
Speaker identity mapping and persistence for block-based processing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from .models import Block
from .speaker_resolver import (
    ROLE_ATTORNEY,
    ROLE_EXAMINING_ATTORNEY,
    ROLE_OPPOSING_COUNSEL,
    ROLE_REPORTER,
    ROLE_UNKNOWN,
    ROLE_VIDEOGRAPHER,
    ROLE_WITNESS,
    resolve_speaker,
)


REPORTER_MARKERS = (
    "raise your right hand",
    "please raise your right hand",
    "solemnly swear",
    "solemnly affirm",
    "do you swear",
    "do you affirm",
    "state your agreement",
    "state your appearances",
)
VIDEOGRAPHER_MARKERS = (
    "today's date is",
    "the time is",
    "beginning of the video deposition",
    "we are on the record",
    "we are off the record",
    "back on the record",
    "deposition concluded",
)
ATTORNEY_NARRATIVE_MARKERS = (
    "i'm going to show you",
    "i am going to show you",
    "let me show you",
    "i'm marking",
    "i am marking",
    "let's mark",
    "i am handing you",
    "i'm handing you",
)
ANSWER_STARTERS = (
    "yes",
    "no",
    "correct",
    "right",
    "yeah",
    "yep",
    "yup",
    "nope",
    "nah",
    "i ",
    "it's ",
    "it is ",
    "my ",
    "uh",
    "um",
)
QUESTION_WORDS = ("who", "what", "when", "where", "why", "how", "did", "do", "does", "is", "are", "can", "could", "would", "will", "have", "has")
IMPERATIVE_QUESTION_STARTERS = ("state", "tell", "describe", "explain", "identify", "name", "mark")


def _speaker_map_from_job_int(job_config: Any) -> Dict[int, str]:
    if hasattr(job_config, "speaker_map"):
        raw = getattr(job_config, "speaker_map", {}) or {}
    elif isinstance(job_config, dict):
        raw = job_config.get("speaker_map", {}) or {}
    else:
        raw = {}
    resolved: Dict[int, str] = {}
    for key, value in raw.items():
        try:
            resolved[int(key)] = value
        except (TypeError, ValueError):
            continue
    return resolved


def _job_key(job_config: Any) -> str:
    if hasattr(job_config, "cause_number"):
        cause = (getattr(job_config, "cause_number", "") or "").strip()
        style = (getattr(job_config, "case_style", "") or "").strip()
    elif isinstance(job_config, dict):
        cause = (job_config.get("cause_number", "") or "").strip()
        style = (job_config.get("case_style", "") or "").strip()
    else:
        cause = ""
        style = ""
    return cause or style


def _speaker_map_from_job(job_config: Any) -> Dict[str, str]:
    if hasattr(job_config, "speaker_map"):
        return {str(k): v for k, v in getattr(job_config, "speaker_map", {}).items()}
    if isinstance(job_config, dict):
        return {str(k): v for k, v in (job_config.get("speaker_map", {}) or {}).items()}
    return {}


def _persisted_map_path() -> Path:
    path = Path("work_files") / "speaker_map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_persisted_maps() -> Dict[str, Dict[str, str]]:
    path = _persisted_map_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_persisted_maps(data: Dict[str, Dict[str, str]]) -> None:
    _persisted_map_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _generic_display_name(name: str, speaker_id: int) -> bool:
    normalized = (name or "").strip().upper()
    return not normalized or normalized == f"SPEAKER {speaker_id}"


def _looks_like_question(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    return (
        normalized.endswith("?")
        or any(lowered.startswith(word + " ") for word in QUESTION_WORDS)
        or any(lowered.startswith(word + " ") for word in IMPERATIVE_QUESTION_STARTERS)
    )


def _looks_like_answer(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized or _looks_like_question(normalized):
        return False
    lowered = normalized.lower()
    return any(lowered.startswith(starter) for starter in ANSWER_STARTERS)


def _known_id_for_role(job_config: Any, target_role: str) -> int | None:
    speaker_map = _speaker_map_from_job_int(job_config)
    for speaker_id, label in speaker_map.items():
        upper = (label or "").upper()
        if target_role == ROLE_REPORTER and "REPORTER" in upper:
            return speaker_id
        if target_role == ROLE_VIDEOGRAPHER and "VIDEOGRAPHER" in upper:
            return speaker_id
        if target_role == ROLE_WITNESS and "WITNESS" in upper:
            return speaker_id
    if target_role == ROLE_WITNESS:
        return getattr(job_config, "witness_id", None) if hasattr(job_config, "witness_id") else job_config.get("witness_id") if isinstance(job_config, dict) else None
    if target_role in (ROLE_EXAMINING_ATTORNEY, ROLE_ATTORNEY):
        return getattr(job_config, "examining_attorney_id", None) if hasattr(job_config, "examining_attorney_id") else job_config.get("examining_attorney_id") if isinstance(job_config, dict) else None
    return None


def _configured_label_for_id(job_config: Any, speaker_id: int | None, fallback: str) -> str:
    if speaker_id is None:
        return fallback
    speaker_map = _speaker_map_from_job_int(job_config)
    return speaker_map.get(speaker_id, fallback)


def _infer_speaker(
    block: Block,
    job_config: Any,
    previous_role: str | None,
    last_attorney_id: int | None,
) -> tuple[int, str, str] | None:
    text = (block.text or "").strip()
    lowered = text.lower()

    if any(marker in lowered for marker in VIDEOGRAPHER_MARKERS):
        sid = _known_id_for_role(job_config, ROLE_VIDEOGRAPHER)
        label = _configured_label_for_id(job_config, sid, "THE VIDEOGRAPHER")
        return sid if sid is not None else block.speaker_id, ROLE_VIDEOGRAPHER, label

    if any(marker in lowered for marker in REPORTER_MARKERS):
        sid = _known_id_for_role(job_config, ROLE_REPORTER)
        label = _configured_label_for_id(job_config, sid, "THE REPORTER")
        return sid if sid is not None else block.speaker_id, ROLE_REPORTER, label

    if _looks_like_question(text) or any(lowered.startswith(marker) for marker in ATTORNEY_NARRATIVE_MARKERS):
        sid = last_attorney_id if last_attorney_id is not None else _known_id_for_role(job_config, ROLE_EXAMINING_ATTORNEY)
        if sid is not None:
            label = _configured_label_for_id(job_config, sid, "COUNSEL")
            role = ROLE_EXAMINING_ATTORNEY if sid == _known_id_for_role(job_config, ROLE_EXAMINING_ATTORNEY) else ROLE_ATTORNEY
            return sid, role, label

    if previous_role in (ROLE_ATTORNEY, ROLE_EXAMINING_ATTORNEY, ROLE_OPPOSING_COUNSEL) and _looks_like_answer(text):
        sid = _known_id_for_role(job_config, ROLE_WITNESS)
        label = _configured_label_for_id(job_config, sid, "THE WITNESS")
        return sid if sid is not None else block.speaker_id, ROLE_WITNESS, label

    return None


def map_speakers(blocks: List[Block], job_config: Any) -> List[Block]:
    """
    Apply speaker names from the current job config and persist them by job key.
    """
    persisted = _load_persisted_maps()
    key = _job_key(job_config)
    speaker_map = _speaker_map_from_job(job_config)

    merged = dict(persisted.get(key, {})) if key else {}
    merged.update(speaker_map)
    if key and merged:
        persisted[key] = merged
        _save_persisted_maps(persisted)

    previous_role: str | None = None
    last_attorney_id: int | None = None

    for block in blocks:
        if block.speaker_id is None:
            continue
        speaker_id, speaker_role, speaker_name = resolve_speaker(
            block.speaker_id,
            {"speaker_map": merged},
        )
        if (
            speaker_role == ROLE_UNKNOWN
            or _generic_display_name(speaker_name, speaker_id)
        ):
            inferred = _infer_speaker(block, job_config, previous_role, last_attorney_id)
            if inferred is not None:
                speaker_id, speaker_role, speaker_name = inferred
        block.speaker_id = speaker_id
        block.speaker_role = speaker_role
        block.speaker_name = speaker_name
        if speaker_role in (ROLE_ATTORNEY, ROLE_EXAMINING_ATTORNEY, ROLE_OPPOSING_COUNSEL):
            last_attorney_id = speaker_id
        if speaker_role != ROLE_UNKNOWN:
            previous_role = speaker_role

    return blocks
