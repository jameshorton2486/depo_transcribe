"""
core/training_corpus.py

Helper for the "Save to Training Corpus" button on the Corrections tab.

Copies a single completed case's pipeline outputs into
`training_corpus/{slug}/` per the conventions in
`training_corpus/README.md`. Only invoked when the user clicks the
button — never automatic.

Files written (per call):
    case_id.txt                                   — overwrite
    pipeline_output_pass1_{today}.txt             — overwrite (same-day re-run)
    pipeline_output_pass2_{today}.txt             — only if AI text supplied
    job_config.json                               — overwrite (mirror of source)
    notes.md                                      — only if missing (hand-written)
    ground_truth.txt                              — only if missing; pre-seeded
                                                    with Pass 2 if AI ran, else
                                                    Pass 1, as an editable draft

Files NEVER touched here:
    older dated pipeline_output_*                 — preserved as audit trail
    existing ground_truth.txt / notes.md          — protected from overwrite
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from app_logging import get_logger
from core.job_config_manager import get_job_config_path, load_job_config

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = PROJECT_ROOT / "training_corpus"

_MONTH_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _derive_slug(ufm: dict[str, Any]) -> str | None:
    """Build `{lastname}_{YYYY}_{MM}_{DD}` from UFM fields. None if insufficient data."""
    witness = (ufm.get("witness_name") or "").strip()
    if not witness:
        return None
    last_token = witness.split()[-1]
    lastname = re.sub(r"[^a-z0-9]", "", last_token.lower())
    if not lastname:
        return None

    year = str(ufm.get("depo_date_year") or "").strip()
    day = str(ufm.get("depo_date_day") or "").strip()
    month_name = str(ufm.get("depo_date_month") or "").strip().lower()
    month_num = _MONTH_TO_NUM.get(month_name)
    if not (year.isdigit() and day.isdigit() and month_num):
        return None

    return f"{lastname}_{int(year):04d}_{month_num:02d}_{int(day):02d}"


def _format_cause_number(raw: str) -> str:
    """`2025CI23267` → `2025-CI-23267`. Pass-through if it doesn't match the pattern."""
    raw = (raw or "").strip()
    m = re.fullmatch(r"(\d{4})([A-Za-z]+)(\d+)", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).upper()}-{m.group(3)}"
    return raw


def _stub_notes(slug: str, ufm: dict[str, Any], today_iso: str) -> str:
    cause = _format_cause_number(ufm.get("cause_number") or "")
    return (
        f"# {slug} — corpus notes\n"
        f"\n"
        f"**Case:** {ufm.get('case_style', '')}\n"
        f"**Cause:** {cause}\n"
        f"**Court:** {ufm.get('court_caption', '')}\n"
        f"**Deposition date:** {ufm.get('depo_date', '')}\n"
        f"**Witness:** {ufm.get('witness_name', '')}\n"
        f"**Court reporter:** {ufm.get('reporter_name', '')}\n"
        f"\n"
        f"## Pipeline outputs in this entry\n"
        f"\n"
        f"| File | Pipeline state | When |\n"
        f"|---|---|---|\n"
        f"| `pipeline_output_pass1_{today_iso}.txt` | Pass 1 (deterministic) | {today_iso} |\n"
        f"\n"
        f"## Ground truth status\n"
        f"\n"
        f"`ground_truth.txt` not yet produced.\n"
        f"\n"
        f"## Certification\n"
        f"\n"
        f"Ground truth certified by: __________  Date: __________\n"
    )


def save_to_corpus(
    corrected_path: str,
    ai_corrected_text: str | None = None,
) -> dict[str, Any]:
    """
    Copy a case's outputs into `training_corpus/{slug}/`.

    Returns:
        {
            "success":       bool,
            "slug":          str,
            "corpus_dir":    str,
            "files_written": list[str],   # filenames only
            "files_skipped": list[str],   # e.g. notes.md when it already existed
            "error":         str | None,
        }
    """
    result: dict[str, Any] = {
        "success": False,
        "slug": "",
        "corpus_dir": "",
        "files_written": [],
        "files_skipped": [],
        "error": None,
    }

    src_corrected = Path(corrected_path)
    if not src_corrected.is_file():
        result["error"] = f"Corrected transcript not found: {src_corrected}"
        return result

    # case_root: {case}/Deepgram/{stem}_corrected.txt → {case}
    case_root = src_corrected.parent.parent
    config_data = load_job_config(str(case_root))
    ufm = config_data.get("ufm_fields", {}) if isinstance(config_data, dict) else {}

    slug = _derive_slug(ufm)
    if not slug:
        result["error"] = (
            "Could not derive corpus slug — job_config is missing "
            "witness_name and/or depo_date_{year,month,day}."
        )
        return result

    target_dir = CORPUS_ROOT / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    today_iso = date.today().isoformat()  # YYYY-MM-DD

    # 1. case_id.txt — overwrite
    cause = _format_cause_number(ufm.get("cause_number") or "")
    if not cause:
        result["error"] = "job_config.ufm_fields.cause_number is empty."
        return result
    (target_dir / "case_id.txt").write_text(cause + "\n", encoding="utf-8")
    result["files_written"].append("case_id.txt")

    # 2. pipeline_output_pass1_{today}.txt — overwrite same-day; preserve older
    pass1_name = f"pipeline_output_pass1_{today_iso}.txt"
    shutil.copyfile(src_corrected, target_dir / pass1_name)
    result["files_written"].append(pass1_name)

    # 3. pipeline_output_pass2_{today}.txt — only if AI text supplied
    if ai_corrected_text and ai_corrected_text.strip():
        pass2_name = f"pipeline_output_pass2_{today_iso}.txt"
        (target_dir / pass2_name).write_text(ai_corrected_text, encoding="utf-8")
        result["files_written"].append(pass2_name)

    # 4. job_config.json — overwrite (mirror of source)
    src_config = get_job_config_path(str(case_root))
    if src_config.is_file():
        shutil.copyfile(src_config, target_dir / "job_config.json")
        result["files_written"].append("job_config.json")
    else:
        # Fallback: serialize whatever load_job_config returned
        (target_dir / "job_config.json").write_text(
            json.dumps(config_data, indent=2), encoding="utf-8",
        )
        result["files_written"].append("job_config.json")

    # 5. notes.md — only stub if missing; never overwrite hand-written notes
    notes_path = target_dir / "notes.md"
    if notes_path.exists():
        result["files_skipped"].append("notes.md (already present)")
    else:
        notes_path.write_text(_stub_notes(slug, ufm, today_iso), encoding="utf-8")
        result["files_written"].append("notes.md")

    # 6. ground_truth.txt — only seed if missing; pre-fill with the most
    # recent pipeline output (Pass 2 if AI ran, else Pass 1) so the user
    # has an editable starting draft. Never overwrite — this file becomes
    # hand-corrected and certified.
    ground_truth_path = target_dir / "ground_truth.txt"
    if ground_truth_path.exists():
        result["files_skipped"].append("ground_truth.txt (already present)")
    else:
        if ai_corrected_text and ai_corrected_text.strip():
            ground_truth_path.write_text(ai_corrected_text, encoding="utf-8")
        else:
            shutil.copyfile(src_corrected, ground_truth_path)
        result["files_written"].append("ground_truth.txt")

    result["success"] = True
    result["slug"] = slug
    result["corpus_dir"] = str(target_dir)
    logger.info(
        "[TrainingCorpus] Saved %s — wrote %d, skipped %d",
        slug, len(result["files_written"]), len(result["files_skipped"]),
    )
    return result
