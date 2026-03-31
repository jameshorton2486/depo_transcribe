"""
Case folder path building, creation, and verification helpers.
"""

from __future__ import annotations

import logging
import json
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

REQUIRED_SUBFOLDERS = ["source_docs", "Deepgram"]

# ── Private constants used only by the deprecated vocabulary functions below ──
_KEYTERMS_FILENAME = "keyterms.json"


def build_case_path(
    base_folder: str,
    cause_number: str,
    witness_last: str,
    witness_first: str,
    deposition_date: str | None = None,
) -> str:
    if deposition_date:
        try:
            dt = datetime.strptime(deposition_date, "%m/%d/%Y")
        except ValueError:
            logger.warning("Invalid date format '%s', using today.", deposition_date)
            dt = datetime.today()
    else:
        dt = datetime.today()

    year = str(dt.year)
    month = MONTH_ABBR[dt.month]
    cause = cause_number.strip() or "UnknownCause"
    last = witness_last.strip().lower() or "unknown"
    first = witness_first.strip().lower() or "unknown"
    witness_folder = f"{last}_{first}"
    return os.path.join(base_folder, year, month, cause, witness_folder)


def create_case_folders(case_path: str) -> dict:
    result = {"case_path": case_path, "created": [], "existing": [], "errors": []}
    all_paths = [case_path] + [os.path.join(case_path, sub) for sub in REQUIRED_SUBFOLDERS]

    for path in all_paths:
        if os.path.isdir(path):
            result["existing"].append(path)
            logger.info("[FileManager] Exists: %s", path)
            continue

        try:
            os.makedirs(path, exist_ok=True)
            result["created"].append(path)
            logger.info("[FileManager] Created: %s", path)
        except Exception as exc:
            result["errors"].append(path)
            logger.error("[FileManager] Failed to create %s: %s", path, exc)

    return result


def verify_case_folders(case_path: str) -> dict:
    result = {"valid": True, "missing": [], "present": []}

    for sub in REQUIRED_SUBFOLDERS:
        path = os.path.join(case_path, sub)
        if os.path.isdir(path):
            result["present"].append(sub)
        else:
            result["missing"].append(sub)
            result["valid"] = False

    return result


def resolve_or_create_case(
    base_folder: str,
    cause_number: str,
    witness_last: str,
    witness_first: str,
    deposition_date: str | None = None,
) -> tuple[str, dict]:
    case_path = build_case_path(
        base_folder,
        cause_number,
        witness_last,
        witness_first,
        deposition_date,
    )
    status = create_case_folders(case_path)
    return case_path, status


def save_job_vocabulary(
    case_folder: str,
    intake_result: Any,
    final_keyterms: list[str],
    reporter_terms: list[str] | None = None,
) -> str | None:
    """
    DEPRECATED — superseded by core.job_config_manager.merge_and_save().
    Retained only because existing tests cover this function.
    Do not call from new code.
    """
    logger.warning(
        "[FileManager] save_job_vocabulary() is deprecated. "
        "Use core.job_config_manager.merge_and_save() instead."
    )
    if not case_folder or not os.path.isdir(case_folder):
        logger.warning("[FileManager] Case folder not found: %s", case_folder)
        return None

    path = os.path.join(case_folder, _KEYTERMS_FILENAME)
    term_counts = {
        "total": len(final_keyterms),
        "reporter": len(reporter_terms or []),
        "PERSON": 0,
        "COMPANY": 0,
        "LOCATION": 0,
        "LEGAL": 0,
        "TECHNICAL": 0,
        "CUSTOM": 0,
    }

    vocabulary_terms: list[dict[str, str]] = []
    if intake_result and getattr(intake_result, "vocabulary_terms", None):
        for term in intake_result.vocabulary_terms:
            vocabulary_terms.append(
                {
                    "term": term.term,
                    "term_type": term.term_type,
                    "field_name": term.field_name,
                    "reason": term.reason,
                }
            )
            if term.term_type in term_counts:
                term_counts[term.term_type] += 1

    case_info = {}
    if intake_result:
        case_info = {
            "cause_number": intake_result.cause_number,
            "case_style": intake_result.case_style,
            "court": intake_result.court,
            "deposition_date": intake_result.deposition_date,
            "deposition_method": intake_result.deposition_method,
            "plaintiffs": intake_result.plaintiffs,
            "defendants": intake_result.defendants,
            "deponents": intake_result.deponents,
            "ordering_attorney": intake_result.ordering_attorney,
            "copy_attorneys": intake_result.copy_attorneys,
            "reporter_name": intake_result.reporter_name,
            "reporter_csr": intake_result.reporter_csr,
            "reporter_firm": intake_result.reporter_firm,
            "reporter_address": intake_result.reporter_address,
            "subpoena_duces_tecum": intake_result.subpoena_duces_tecum,
            "signature_waived": intake_result.signature_waived,
            "video_recorded": intake_result.video_recorded,
        }

    payload = {
        "saved_at": datetime.now().isoformat(),
        "case_info": case_info,
        "vocabulary_terms": vocabulary_terms,
        "final_keyterms": final_keyterms,
        "reporter_terms": reporter_terms or [],
        "confirmed_spellings": (
            dict(getattr(intake_result, "confirmed_spellings", {}))
            if intake_result else {}
        ),
        "term_counts": term_counts,
    }

    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        logger.info("[FileManager] Saved keyterms.json  %s terms  %s", len(final_keyterms), path)
        return path
    except Exception as exc:
        logger.error("[FileManager] Failed to save keyterms.json: %s", exc)
        return None


def load_job_vocabulary(case_folder: str) -> dict | None:
    """
    DEPRECATED — superseded by core.job_config_manager.load_job_config().
    Retained only because existing tests cover this function.
    Do not call from new code.
    """
    logger.warning(
        "[FileManager] load_job_vocabulary() is deprecated. "
        "Use core.job_config_manager.load_job_config() instead."
    )
    path = os.path.join(case_folder, _KEYTERMS_FILENAME)
    if not os.path.isfile(path):
        logger.info("[FileManager] No keyterms.json found in: %s", case_folder)
        return None

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        logger.info(
            "[FileManager] Loaded keyterms.json  %s terms",
            len(data.get("final_keyterms", [])),
        )
        return data
    except Exception as exc:
        logger.error("[FileManager] Failed to load keyterms.json: %s", exc)
        return None
