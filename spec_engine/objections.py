"""
Objection extraction from structured blocks.
"""

from __future__ import annotations

import re
from typing import Any, List

from .models import Block, BlockType


OBJECTION_PATTERNS = [
    r"\bexit form\b",
    r"\baction form\b",
    r"\bobjection form\b",
    # 'objection to form' removed: corrections.py now normalizes all ASR garbles
    # to "Objection. Form." (two sentences, verbatim). The classifier handles
    # correctly-formed text via OBJECTION_START_RE. Re-adding this pattern
    # would fire on already-corrected text.
]
CORRECTED_OBJECTION_FORM_RE = re.compile(r"\bobjection\.\s+form\.", re.IGNORECASE)


def _resolve_objection_speaker(job_config: Any) -> str:
    """
    Resolve the display name for objection speaker labels.

    Priority order:
      1. Speaker map — find the entry with OPPOSING COUNSEL or DEFENSE role
      2. defense_counsel list in JobConfig (dataclass or dict form)
      3. Any attorney-labeled speaker who is NOT the examining attorney
      4. Fallback: "COUNSEL"  (never "MR. UNKNOWN")
    """
    import logging as _logging

    _log = _logging.getLogger("spec_engine.objections")

    speaker_map: dict = {}
    if hasattr(job_config, "speaker_map"):
        speaker_map = getattr(job_config, "speaker_map", {}) or {}
    elif isinstance(job_config, dict):
        speaker_map = job_config.get("speaker_map", {}) or {}

    examining_id = None
    if hasattr(job_config, "examining_attorney_id"):
        examining_id = getattr(job_config, "examining_attorney_id", None)
    elif isinstance(job_config, dict):
        examining_id = job_config.get("examining_attorney_id")

    for sid, label in speaker_map.items():
        label_upper = (label or "").upper()
        if "OPPOSING COUNSEL" in label_upper or "DEFENSE" in label_upper:
            _log.debug("Objection speaker resolved from speaker_map: %s", label)
            return label

    if hasattr(job_config, "defense_counsel"):
        counsel_list = getattr(job_config, "defense_counsel", []) or []
        if counsel_list:
            first = counsel_list[0]
            name = getattr(first, "name", "") or ""
            if name.strip():
                title = (getattr(first, "title", "") or "MR.").strip()
                parts = name.strip().split()
                last = parts[-1].upper() if parts else name.upper()
                resolved = f"{title} {last}"
                _log.debug("Objection speaker resolved from defense_counsel: %s", resolved)
                return resolved
    elif isinstance(job_config, dict):
        defense = job_config.get("defense_counsel")
        if isinstance(defense, str) and defense.strip():
            resolved = defense.strip()
            _log.debug(
                "Objection speaker resolved from defense_counsel string: %s",
                resolved,
            )
            return resolved
        if isinstance(defense, list) and defense:
            first = defense[0]
            if isinstance(first, dict) and (first.get("name") or "").strip():
                title = (first.get("title") or "MR.").strip()
                parts = first["name"].strip().split()
                last = parts[-1].upper() if parts else first["name"].upper()
                resolved = f"{title} {last}"
                _log.debug(
                    "Objection speaker resolved from defense_counsel dict: %s",
                    resolved,
                )
                return resolved

    for sid, label in speaker_map.items():
        label_upper = (label or "").upper()
        is_attorney = any(
            token in label_upper
            for token in ("MR.", "MS.", "MRS.", "DR.", "ATTORNEY", "COUNSEL")
        )
        is_examiner = examining_id is not None and str(sid) == str(examining_id)
        if is_attorney and not is_examiner:
            _log.debug("Objection speaker resolved from attorney in speaker_map: %s", label)
            return label

    _log.warning(
        "Could not resolve objection speaker. Using 'COUNSEL' as fallback. "
        "To fix: add defense_counsel to JobConfig, or ensure the speaker_map "
        "contains an entry with 'OPPOSING COUNSEL' in the label."
    )
    return "COUNSEL"


def extract_objections(blocks: List[Block], job_config: Any) -> List[Block]:
    new_blocks: List[Block] = []
    objection_speaker = _resolve_objection_speaker(job_config)

    for block in blocks:
        text = block.text
        match = None
        for pattern in OBJECTION_PATTERNS:
            found_match = re.search(pattern, text, re.IGNORECASE)
            if found_match:
                match = found_match
                break
        if not match:
            corrected_match = CORRECTED_OBJECTION_FORM_RE.search(text)
            if corrected_match:
                match = corrected_match

        if not match:
            new_blocks.append(block)
            continue

        objection_text = match.group(0).strip()
        cleaned = (text[:match.start()] + text[match.end():]).strip(" .")
        if cleaned:
            kept = Block(
                raw_text=block.raw_text,
                text=cleaned + ("" if cleaned.endswith((".", "?", "!")) else "."),
                speaker_id=block.speaker_id,
                speaker_name=block.speaker_name,
                speaker_role=block.speaker_role,
                block_type=block.block_type,
                words=list(block.words),
                flags=list(block.flags),
                meta=dict(block.meta),
            )
            new_blocks.append(kept)

        new_blocks.append(
            Block(
                speaker_id=None,
                raw_text=text,
                text=objection_text,
                speaker_name=objection_speaker,
                speaker_role="OPPOSING_COUNSEL",
                block_type=BlockType.SPEAKER,
                meta={"source": "objection_extraction", "is_objection": True},
            )
        )

    return new_blocks
