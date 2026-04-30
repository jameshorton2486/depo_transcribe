from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.file_manager import (
    _normalize_deposition_date,
    build_case_path,
    create_case_folders,
    verify_case_folders,
)


def test_build_case_path_uses_required_structure():
    path = build_case_path("C:\\Depositions", "2025CI19595", "Coger", "Matthew", "03/24/2026")
    expected = os.path.join("2026", "Mar", "2025CI19595", "coger_matthew")
    assert path.endswith(expected)


def test_build_case_path_accepts_long_form_month_dates():
    path = build_case_path("C:\\Depositions", "2025CI19595", "Coger", "Matthew", "April 10, 2026")
    expected = os.path.join("2026", "Apr", "2025CI19595", "coger_matthew")
    assert path.endswith(expected)


def test_build_case_path_accepts_intake_date_with_at_time_suffix():
    # The exact runtime-log input that previously fell back to today's
    # date because neither %m/%d/%Y nor %B %d, %Y matched the trailing
    # "at 8:00 a.m." text. Should now route to 2026/Apr/, not today.
    path = build_case_path(
        "C:\\Depositions",
        "DC-25-13430",
        "Karam",
        "Bianca",
        "April 9, 2026 at 8:00 a.m.",
    )
    expected = os.path.join("2026", "Apr", "DC-25-13430", "karam_bianca")
    assert path.endswith(expected)


def test_build_case_path_accepts_iso_date():
    # %Y-%m-%d added to _DATE_FORMATS in this commit; verify it parses.
    path = build_case_path("C:\\Depositions", "DC-25-13430", "Karam", "Bianca", "2026-04-09")
    expected = os.path.join("2026", "Apr", "DC-25-13430", "karam_bianca")
    assert path.endswith(expected)


def test_normalize_deposition_date_strips_at_suffix():
    assert _normalize_deposition_date("April 9, 2026 at 8:00 a.m.") == "April 9, 2026"


def test_normalize_deposition_date_strips_at_with_alternative_time_form():
    assert _normalize_deposition_date("4/9/2026 at noon") == "4/9/2026"


def test_normalize_deposition_date_passes_through_clean_input():
    assert _normalize_deposition_date("April 9, 2026") == "April 9, 2026"
    assert _normalize_deposition_date("2026-04-09") == "2026-04-09"


def test_normalize_deposition_date_handles_empty_and_none_safe():
    assert _normalize_deposition_date("") == ""
    assert _normalize_deposition_date(None) == ""  # type: ignore[arg-type]


def test_create_case_folders_creates_required_subfolders(tmp_path):
    create_case_folders(str(tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew"))
    assert (tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew" / "source_docs").is_dir()


def test_verify_case_folders_reports_valid_after_creation(tmp_path):
    case_path = tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew"
    create_case_folders(str(case_path))
    assert verify_case_folders(str(case_path))["valid"] is True
