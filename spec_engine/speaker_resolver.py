"""
Speaker resolution helpers for the block-based transcript pipeline.

This layer normalizes speaker IDs, interprets the configured speaker map, and
provides a stable role/display label before classification runs.
"""

from __future__ import annotations

import re
from typing import Any, Tuple


ROLE_UNKNOWN = "UNKNOWN"
ROLE_WITNESS = "WITNESS"
ROLE_REPORTER = "REPORTER"
ROLE_VIDEOGRAPHER = "VIDEOGRAPHER"
ROLE_INTERPRETER = "INTERPRETER"
ROLE_ATTORNEY = "ATTORNEY"
ROLE_EXAMINING_ATTORNEY = "EXAMINING_ATTORNEY"
ROLE_OPPOSING_COUNSEL = "OPPOSING_COUNSEL"


def normalize_speaker_id(raw_id: Any) -> int:
    """
    Normalize any speaker identifier into an int.
    Accepts values like 0, "0", and "Speaker 0".
    """
    if isinstance(raw_id, bool):
        raise ValueError(f"Cannot normalize boolean speaker_id: {raw_id!r}")
    if isinstance(raw_id, int):
        return raw_id
    text = str(raw_id or "").strip()
    match = re.search(r"(\d+)$", text)
    if match:
        return int(match.group(1))
    raise ValueError(f"Cannot normalize speaker_id: {raw_id!r}")


def _speaker_map_from_job(job_config: Any) -> dict[int, str]:
    if hasattr(job_config, "speaker_map"):
        raw = getattr(job_config, "speaker_map", {}) or {}
    elif isinstance(job_config, dict):
        raw = job_config.get("speaker_map", {}) or {}
    else:
        raw = {}

    resolved: dict[int, str] = {}
    for key, value in raw.items():
        try:
            resolved[normalize_speaker_id(key)] = str(value or "").strip()
        except ValueError:
            continue
    return resolved


def normalize_speaker_role(label: str) -> str:
    normalized = (label or "").strip().upper()
    if not normalized:
        return ROLE_UNKNOWN
    if "WITNESS" in normalized:
        return ROLE_WITNESS
    if "VIDEOGRAPHER" in normalized:
        return ROLE_VIDEOGRAPHER
    if "INTERPRETER" in normalized:
        return ROLE_INTERPRETER
    if "REPORTER" in normalized:
        return ROLE_REPORTER
    if "EXAMINING" in normalized:
        return ROLE_EXAMINING_ATTORNEY
    if "COUNSEL" in normalized:
        return ROLE_OPPOSING_COUNSEL
    if any(token in normalized for token in ("ATTORNEY", "MR.", "MS.", "MRS.", "DR.")):
        return ROLE_ATTORNEY
    return ROLE_UNKNOWN


def normalize_display_name(label: str, speaker_id: int) -> str:
    normalized = (label or "").strip()
    if not normalized:
        return f"SPEAKER {speaker_id}"
    upper = normalized.upper()
    if upper == "THE COURT REPORTER":
        return "THE REPORTER"
    return normalized


def resolve_speaker(speaker_id: Any, job_config: Any) -> Tuple[int, str, str]:
    """
    Resolve a speaker into (normalized_id, speaker_role, display_name).
    """
    sid = normalize_speaker_id(speaker_id)
    speaker_map = _speaker_map_from_job(job_config)
    configured = speaker_map.get(sid, "")
    role = normalize_speaker_role(configured)
    display_name = normalize_display_name(configured, sid)
    return sid, role, display_name

