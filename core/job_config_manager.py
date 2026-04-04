"""
core/job_config_manager.py

Single entry point for reading and writing job_config.json.

No other module should build the path or open this file directly.
Always use load_job_config(), save_job_config(), or merge_and_save().

FILE LOCATION
-------------
    {case_root}/source_docs/job_config.json

FILE BEHAVIOR
-------------
- Always overwrite on save — never create timestamped duplicates.
- source_docs/ is created automatically if it does not exist.
- save_job_config() stamps "version" on every write.

EXPECTED STRUCTURE
------------------
{
    "version": 1,
    "utt_split": 1.2,
    "ufm_fields": {
        "cause_number":    "2025-CI-19595",
        "witness_name":    "Matthew Coger",
        "state":           "Texas",
        ...
    },
    "confirmed_spellings": {
        "Koger":  "Coger",
        "Cojer":  "Coger"
    }
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app_logging import get_logger
from core.config import (
    JOB_CONFIG_DIR,
    JOB_CONFIG_FILENAME,
    JOB_CONFIG_VERSION,
)

logger = get_logger(__name__)


# ── Path helper ───────────────────────────────────────────────────────────────

def get_job_config_path(case_root: str) -> Path:
    """Return the canonical Path for job_config.json given a case root folder."""
    return Path(case_root) / JOB_CONFIG_DIR / JOB_CONFIG_FILENAME


# ── Load ──────────────────────────────────────────────────────────────────────

def load_job_config(case_root: str) -> dict[str, Any]:
    """
    Load job_config.json from {case_root}/source_docs/.

    Returns an empty dict if the file does not exist or cannot be parsed.
    Never raises an exception — all errors are logged.

    Callers must treat an empty return value as "no config on disk yet"
    and behave accordingly (e.g. return a default JobConfig).
    """
    path = get_job_config_path(case_root)

    if not path.exists():
        logger.info("[JobConfig] File not found: %s", path)
        return {}

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data: dict = json.load(fh)
    except Exception as exc:
        logger.error("[JobConfig] Failed to load %s: %s", path, exc)
        return {}


    # Version check
    version = data.get("version")
    if version is None:
        logger.warning("[JobConfig] No 'version' key — treating as legacy file: %s", path)
    elif version != JOB_CONFIG_VERSION:
        logger.warning(
            "[JobConfig] Version mismatch — file=%s expected=%s: %s",
            version, JOB_CONFIG_VERSION, path,
        )

    logger.info(
        "[JobConfig] Loaded: ufm_fields=%d keys  confirmed_spellings=%d  keyterms=%d  version=%s",
        len(data.get("ufm_fields", {})),
        len(data.get("confirmed_spellings", {})),
        len(data.get("deepgram_keyterms", [])),
        version,
    )
    return data


# ── Save ──────────────────────────────────────────────────────────────────────

def save_job_config(case_root: str, data: dict[str, Any]) -> Path | None:
    """
    Overwrite job_config.json in {case_root}/source_docs/.

    Always performed on the data dict before writing:
      - Stamps "version" key
      - Logs a warning if confirmed_spellings is empty (accuracy risk)

    Creates source_docs/ if it does not exist.
    Returns the Path that was written, or None on failure.
    """
    path = get_job_config_path(case_root)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[JobConfig] Cannot create directory %s: %s", path.parent, exc)
        return None

    # ── Stamp version ─────────────────────────────────────────────────────────
    data["version"] = JOB_CONFIG_VERSION


    # Normalize Deepgram keyterms to a stable list[str] shape
    raw_keyterms = data.get("deepgram_keyterms")
    if raw_keyterms is None:
        pass
    elif isinstance(raw_keyterms, list):
        data["deepgram_keyterms"] = [str(t).strip() for t in raw_keyterms if str(t).strip()]
    else:
        logger.warning("[JobConfig] deepgram_keyterms must be a list; dropping invalid value of type %s", type(raw_keyterms).__name__)
        data.pop("deepgram_keyterms", None)

    # ── Validate confirmed_spellings ──────────────────────────────────────────
    spellings: dict = data.get("confirmed_spellings", {})
    if not spellings:
        logger.warning(
            "[JobConfig] confirmed_spellings is empty — "
            "name corrections will not run for this case"
        )
    else:
        logger.info("[JobConfig] confirmed_spellings: %d entries", len(spellings))

    # ── Log summary ───────────────────────────────────────────────────────────
    logger.info(
        "[JobConfig] Saving → %s  "
        "(ufm_fields=%d  confirmed_spellings=%d  keyterms=%d)",
        path,
        len(data.get("ufm_fields", {})),
        len(spellings),
        len(data.get("deepgram_keyterms", [])),
    )

    # ── Write ─────────────────────────────────────────────────────────────────
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        return path
    except Exception as exc:
        logger.error("[JobConfig] Failed to save %s: %s", path, exc)
        return None


# ── Merge + Save ──────────────────────────────────────────────────────────────

def merge_and_save(case_root: str, **sections: Any) -> Path | None:
    """
    Load the existing job_config.json, merge new sections in, then save.

    Accepted keyword arguments:
        model                 (str)   — selected Deepgram model for this case
        audio_quality         (str)   — selected preprocessing quality tier
        ufm_fields            (dict)  — UFM page fields
        confirmed_spellings   (dict)  — Deepgram → correct spelling map
        low_confidence_words  (list)  — words below confidence threshold
        utt_split             (float) — Deepgram utterance split setting

    Any section key passed as None is ignored (existing value preserved).

    Example:
        merge_and_save(
            case_root,
            ufm_fields={"cause_number": "2025-CI-19595", ...},
            confirmed_spellings={"Koger": "Coger"},
        )

    Returns the Path written, or None on failure.
    """
    existing = load_job_config(case_root)

    for key, value in sections.items():
        if value is not None:
            existing[key] = value

    return save_job_config(case_root, existing)
