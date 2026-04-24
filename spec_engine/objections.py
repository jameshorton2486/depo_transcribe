"""
Objection extraction from structured blocks.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List

from .models import Block, BlockType

_log = logging.getLogger("spec_engine.objections")


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

# Instructions like "You can answer" sometimes appear as a separate block
# immediately after an objection. These get consumed and appended to the
# objection block to avoid leaving them as unattributed orphan COLLOQUY blocks.
_YOU_CAN_ANSWER_RE = re.compile(
    r"^(?:you\s+(?:can|may)\s+answer"
    r"|go\s+ahead\s+and\s+answer"
    r"|you\s+can\s+still\s+answer"
    r"|answer\s+if\s+you\s+(?:can|like)"
    r"|you\s+can\s+go\s+ahead)\.?$",
    re.IGNORECASE,
)

# Reporter label tokens — used to exclude the reporter from objection
# speaker resolution. Without this, a reporter labeled "Ms. Bardot" would
# match the attorney token check and be returned as the objection speaker.
_REPORTER_LABEL_TOKENS = frozenset({
    "REPORTER", "CSR", "COURT REPORTER", "NOTARY",
})


def _resolve_objection_speaker(job_config: Any) -> str:
    """
    Resolve the display name for objection speaker labels.

    Priority order:
      1. Speaker map — find the entry with OPPOSING COUNSEL or DEFENSE role
      2. defense_counsel list in JobConfig (dataclass or dict form)
      3. Any attorney-labeled speaker who is NOT the examining attorney
         AND NOT the reporter
      4. Fallback: "COUNSEL"  (never "MR. UNKNOWN")
    """
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
        # Exclude the reporter — "Ms. Bardot" would otherwise match the
        # attorney token check and be returned as the objection speaker.
        if any(token in label_upper for token in _REPORTER_LABEL_TOKENS):
            continue
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
    """
    Extract objection phrases from Q/A blocks and emit them as SPEAKER blocks.

    Skips blocks that have already been classified as SPEAKER or COLLOQUY —
    those are already properly attributed, and re-extracting from them would
    duplicate the objection with the wrong speaker.

    If the block immediately after an extracted objection is a "you can
    answer" instruction, it is appended to the objection block rather than
    left as an unattributed orphan.
    """
    objection_speaker = _resolve_objection_speaker(job_config)
    _log.debug(
        "[OBJECTIONS] processing %d blocks - speaker=%s",
        len(blocks), objection_speaker,
    )

    new_blocks: List[Block] = []
    extracted = 0
    merged_instructions = 0

    i = 0
    while i < len(blocks):
        block = blocks[i]
        text = block.text

        # Skip already-classified speaker turns — CORRECTED_OBJECTION_FORM_RE
        # would otherwise re-match inside them and re-attribute the objection.
        if block.block_type in (BlockType.SPEAKER, BlockType.COLLOQUY):
            new_blocks.append(block)
            i += 1
            continue

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
            i += 1
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

        # Consume a following "you can answer" instruction into this objection.
        objection_suffix = ""
        if i + 1 < len(blocks):
            next_block = blocks[i + 1]
            if _YOU_CAN_ANSWER_RE.match((next_block.text or "").strip()):
                objection_suffix = "  " + (next_block.text or "").strip()
                merged_instructions += 1
                i += 1

        new_blocks.append(
            Block(
                speaker_id=None,
                raw_text=text,
                text=objection_text + objection_suffix,
                speaker_name=objection_speaker,
                speaker_role="OPPOSING_COUNSEL",
                block_type=BlockType.SPEAKER,
                meta={"source": "objection_extraction", "is_objection": True},
            )
        )
        extracted += 1
        i += 1

    _log.debug(
        "[OBJECTIONS] complete - %d extracted, %d instructions merged, %d->%d blocks",
        extracted, merged_instructions, len(blocks), len(new_blocks),
    )
    return new_blocks
