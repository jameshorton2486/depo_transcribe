"""
Case folder path building, creation, and verification helpers.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)

MONTH_ABBR = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

REQUIRED_SUBFOLDERS = ["source_docs", "Deepgram"]

_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y")

# Intake-produced strings often append a start time after the date
# ("April 9, 2026 at 8:00 a.m."). Strip that suffix before strptime so
# the strict formats above have a chance to match instead of falling
# through to today's date.
_TRAILING_AT_SUFFIX = re.compile(r"\s+at\s+.*$", re.IGNORECASE)


def normalize_deposition_date(value: str) -> str:
    """Strip a trailing ' at HH:MM ...' suffix and surrounding whitespace."""
    return _TRAILING_AT_SUFFIX.sub("", value or "").strip()


def normalize_cause_number(value: str) -> str:
    """Return the canonical form of a cause number used for folder routing.

    Strips every non-alphanumeric character and uppercases letters so
    that all common typings of a cause number resolve to the same folder:

        "DC-25-13430"     → "DC2513430"
        "DC2513430"       → "DC2513430"
        " dc 25 13430 "   → "DC2513430"
        "2025-CI-19595"   → "2025CI19595"
        "2025/CI/19595"   → "2025CI19595"

    Empty / whitespace-only input → "UnknownCause" so the caller still
    gets a usable folder name.
    """
    if not value:
        return "UnknownCause"
    canonical = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return canonical or "UnknownCause"


def find_existing_cause_folder(parent_dir: str, cause_number: str) -> str | None:
    """Return the existing case folder under `parent_dir` whose name has the
    same canonical form as `cause_number`, or None if no match.

    Lets the app honor legacy folders named with the old (un-normalized)
    cause string when the user re-types the cause number in a different
    style. Returns the absolute path or None.
    """
    if not parent_dir or not os.path.isdir(parent_dir):
        return None
    target = normalize_cause_number(cause_number)
    try:
        entries = os.listdir(parent_dir)
    except OSError:
        return None
    for name in entries:
        full = os.path.join(parent_dir, name)
        if not os.path.isdir(full):
            continue
        if normalize_cause_number(name) == target:
            return full
    return None


def build_case_path(
    base_folder: str,
    cause_number: str,
    witness_last: str,
    witness_first: str,
    deposition_date: str | None = None,
) -> str:
    """Build the canonical case folder path.

    The cause-number segment is `normalize_cause_number(cause_number)`,
    so two calls with equivalent-but-differently-formatted cause numbers
    (e.g., "DC-25-13430" vs "DC2513430") return the same path.
    """
    if deposition_date:
        candidate = normalize_deposition_date(deposition_date)
        dt = None
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(candidate, fmt)
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
    cause = normalize_cause_number(cause_number)
    last = witness_last.strip().lower() or "unknown"
    first = witness_first.strip().lower() or "unknown"
    witness_folder = f"{last}_{first}"
    return os.path.join(base_folder, year, month, cause, witness_folder)


def create_case_folders(case_path: str) -> dict:
    result = {"case_path": case_path, "created": [], "existing": [], "errors": []}
    all_paths = [case_path] + [
        os.path.join(case_path, sub) for sub in REQUIRED_SUBFOLDERS
    ]

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
    """Resolve a case folder, reusing a legacy folder if its name's canonical
    form matches the requested cause number.

    Order of attempts:
      1. The canonical case path. If it already exists on disk, use it.
      2. Scan the canonical parent (year/month) for any folder whose name
         normalizes to the same canonical cause. If found, reuse it —
         this lets "DC-25-13430" continue to find an existing folder
         named with the old un-normalized form.
      3. Otherwise create the canonical path.
    """
    canonical_path = build_case_path(
        base_folder, cause_number, witness_last, witness_first, deposition_date,
    )

    if os.path.isdir(canonical_path):
        status = create_case_folders(canonical_path)
        return canonical_path, status

    # Hunt for a legacy folder under the same year/month whose cause name
    # normalizes to the requested one. The cause folder is the parent of
    # the witness folder, hence parents[1].
    witness_segment = os.path.basename(canonical_path)
    cause_parent = os.path.dirname(os.path.dirname(canonical_path))
    legacy_cause_dir = find_existing_cause_folder(cause_parent, cause_number)
    if legacy_cause_dir is not None:
        legacy_case = os.path.join(legacy_cause_dir, witness_segment)
        if os.path.isdir(legacy_case):
            status = create_case_folders(legacy_case)
            return legacy_case, status

    status = create_case_folders(canonical_path)
    return canonical_path, status
