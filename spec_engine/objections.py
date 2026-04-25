"""
Objection extraction from structured blocks.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List

from .models import Block, BlockType


__all__ = ["extract_objections"]


_log = logging.getLogger("spec_engine.objections")


OBJECTION_PATTERNS = [
    r"\bexit form\b",
    r"\baction form\b",
    r"\bobjection form\b",
    # 'objection to form' removed: corrections.py now normalizes all ASR garbles
    # to "Objection.  Form." (two sentences, two-space separator, verbatim).
    # The classifier handles
    # correctly-formed text via OBJECTION_START_RE. Re-adding this pattern
    # would fire on already-corrected text.
]
# Pre-compiled view of OBJECTION_PATTERNS — built once at import so
# extract_objections() does not re-compile each pattern per block.
# OBJECTION_PATTERNS itself stays as a list of strings to preserve the
# public surface for any importers that read it as raw patterns.
_OBJECTION_PATTERN_RES = [
    re.compile(pattern, re.IGNORECASE) for pattern in OBJECTION_PATTERNS
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

# Attorney label tokens — used to identify attorney-style speaker labels
# during objection speaker fallback resolution. Mirrors the structure of
# _REPORTER_LABEL_TOKENS for consistency.
_ATTORNEY_LABEL_TOKENS = frozenset({
    "MR.", "MS.", "MRS.", "DR.", "ATTORNEY", "COUNSEL",
})


# ── JobConfig accessor helper ────────────────────────────────────────────────
# JobConfig may arrive as either a dataclass-style object or a plain dict.
# Centralizes the dict-or-attr lookup that was previously inlined twice in
# _resolve_objection_speaker. Note: the defense_counsel handling is NOT
# routed through this helper — it does shape-dependent parsing that differs
# between the object and dict branches.

def _get_config_value(job_config: Any, key: str, default: Any = None) -> Any:
    """Read a value from JobConfig (object) or dict, returning default if missing."""
    if job_config is None:
        return default
    if hasattr(job_config, key):
        return getattr(job_config, key, default)
    if isinstance(job_config, dict):
        return job_config.get(key, default)
    return default


def _extract_counsel_name_title(entry: Any) -> tuple[str, str]:
    """
    Pull (name, title) out of a counsel entry. Handles both shapes:
    a CounselInfo-style object (test fixtures, in-memory promotion)
    and a plain dict (JSON-loaded job_config). The dataclass branch
    of _resolve_objection_speaker previously only handled the object
    shape — when defense_counsel arrived as a list of dicts on a
    dataclass-shaped JobConfig, getattr(first, "name") returned ""
    and the branch silently fell through.
    """
    if isinstance(entry, dict):
        name = (entry.get("name") or "").strip()
        title = (entry.get("title") or "MR.").strip()
    else:
        name = (getattr(entry, "name", "") or "").strip()
        title = (getattr(entry, "title", "") or "MR.").strip()
    return name, title


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
    speaker_map = _get_config_value(job_config, "speaker_map", {}) or {}
    if not isinstance(speaker_map, dict):
        speaker_map = {}

    examining_id = _get_config_value(job_config, "examining_attorney_id")

    for sid, label in speaker_map.items():
        label_upper = (label or "").upper()
        if "OPPOSING COUNSEL" in label_upper or "DEFENSE" in label_upper:
            _log.debug("Objection speaker resolved from speaker_map: %s", label)
            return label

    if hasattr(job_config, "defense_counsel"):
        counsel_list = getattr(job_config, "defense_counsel", []) or []
        if counsel_list:
            name, title = _extract_counsel_name_title(counsel_list[0])
            if name:
                parts = name.split()
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
            name, title = _extract_counsel_name_title(defense[0])
            if name:
                parts = name.split()
                last = parts[-1].upper() if parts else name.upper()
                resolved = f"{title} {last}"
                _log.debug(
                    "Objection speaker resolved from defense_counsel list: %s",
                    resolved,
                )
                return resolved

    witness_id = _get_config_value(job_config, "witness_id")

    for sid, label in speaker_map.items():
        label_upper = (label or "").upper()
        # Exclude the reporter — "Ms. Bardot" would otherwise match the
        # attorney token check and be returned as the objection speaker.
        if any(token in label_upper for token in _REPORTER_LABEL_TOKENS):
            continue
        is_attorney = any(token in label_upper for token in _ATTORNEY_LABEL_TOKENS)
        is_examiner = examining_id is not None and str(sid) == str(examining_id)
        # Also exclude the witness. A witness labeled "MR. SINGH" matches
        # the attorney token check (Mr.) — without this guard the loop
        # would happily return the witness's own label as the objection
        # speaker if the speaker_map ordering put the witness before any
        # genuine attorney.
        is_witness = witness_id is not None and str(sid) == str(witness_id)
        if is_attorney and not is_examiner and not is_witness:
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
        for pattern in _OBJECTION_PATTERN_RES:
            found_match = pattern.search(text)
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
