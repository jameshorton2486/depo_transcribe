"""
Case folder path building, creation, and verification helpers.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

REQUIRED_SUBFOLDERS = ["source_docs", "Deepgram"]

_DATE_FORMATS = ("%m/%d/%Y", "%B %d, %Y")


def build_case_path(
    base_folder: str,
    cause_number: str,
    witness_last: str,
    witness_first: str,
    deposition_date: str | None = None,
) -> str:
    if deposition_date:
        dt = None
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(deposition_date, fmt)
                break
            except ValueError:
                continue
        if dt is None:
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
