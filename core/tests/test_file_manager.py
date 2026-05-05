from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.file_manager import (
    build_case_path,
    create_case_folders,
    find_existing_cause_folder,
    normalize_cause_number,
    normalize_deposition_date,
    resolve_or_create_case,
    verify_case_folders,
)


def test_build_case_path_uses_required_structure():
    path = build_case_path(
        "C:\\Depositions", "2025CI19595", "Coger", "Matthew", "03/24/2026"
    )
    expected = os.path.join("2026", "Mar", "2025CI19595", "coger_matthew")
    assert path.endswith(expected)


def test_build_case_path_accepts_long_form_month_dates():
    path = build_case_path(
        "C:\\Depositions", "2025CI19595", "Coger", "Matthew", "April 10, 2026"
    )
    expected = os.path.join("2026", "Apr", "2025CI19595", "coger_matthew")
    assert path.endswith(expected)


def test_build_case_path_accepts_intake_date_with_at_time_suffix():
    # The cause segment is now the canonical form ("DC2513430"), not the
    # raw input. Any equivalent typing of the cause routes to the same
    # folder — the user's reported pain point.
    path = build_case_path(
        "C:\\Depositions",
        "DC-25-13430",
        "Karam",
        "Bianca",
        "April 9, 2026 at 8:00 a.m.",
    )
    expected = os.path.join("2026", "Apr", "DC2513430", "karam_bianca")
    assert path.endswith(expected)


def test_build_case_path_accepts_iso_date():
    path = build_case_path(
        "C:\\Depositions", "DC-25-13430", "Karam", "Bianca", "2026-04-09"
    )
    expected = os.path.join("2026", "Apr", "DC2513430", "karam_bianca")
    assert path.endswith(expected)


def test_dashed_and_undashed_cause_numbers_route_to_same_folder():
    p1 = build_case_path("C:\\Depositions", "DC-25-13430", "Karam", "Bianca", "2026-04-09")
    p2 = build_case_path("C:\\Depositions", "DC2513430",   "Karam", "Bianca", "2026-04-09")
    p3 = build_case_path("C:\\Depositions", "dc-25-13430", "Karam", "Bianca", "2026-04-09")
    p4 = build_case_path("C:\\Depositions", " DC 25 13430 ", "Karam", "Bianca", "2026-04-09")
    assert p1 == p2 == p3 == p4


def testnormalize_deposition_date_strips_at_suffix():
    assert normalize_deposition_date("April 9, 2026 at 8:00 a.m.") == "April 9, 2026"


def testnormalize_deposition_date_strips_at_with_alternative_time_form():
    assert normalize_deposition_date("4/9/2026 at noon") == "4/9/2026"


def testnormalize_deposition_date_passes_through_clean_input():
    assert normalize_deposition_date("April 9, 2026") == "April 9, 2026"
    assert normalize_deposition_date("2026-04-09") == "2026-04-09"


def testnormalize_deposition_date_handles_empty_and_none_safe():
    assert normalize_deposition_date("") == ""
    assert normalize_deposition_date(None) == ""  # type: ignore[arg-type]


def test_create_case_folders_creates_required_subfolders(tmp_path):
    create_case_folders(
        str(tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew")
    )
    assert (
        tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew" / "source_docs"
    ).is_dir()


def test_verify_case_folders_reports_valid_after_creation(tmp_path):
    case_path = tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew"
    create_case_folders(str(case_path))
    assert verify_case_folders(str(case_path))["valid"] is True


def test_normalize_cause_number_strips_separators_and_uppercases():
    assert normalize_cause_number("DC-25-13430") == "DC2513430"
    assert normalize_cause_number("dc-25-13430") == "DC2513430"
    assert normalize_cause_number("dc 25 13430") == "DC2513430"
    assert normalize_cause_number("DC2513430") == "DC2513430"
    assert normalize_cause_number(" DC/25/13430 ") == "DC2513430"
    assert normalize_cause_number("2025-CI-19595") == "2025CI19595"


def test_normalize_cause_number_handles_empty_safely():
    assert normalize_cause_number("") == "UnknownCause"
    assert normalize_cause_number("   ") == "UnknownCause"
    assert normalize_cause_number(None) == "UnknownCause"  # type: ignore[arg-type]


def test_find_existing_cause_folder_matches_legacy_dashed_form(tmp_path):
    # User has an existing folder from before normalization landed.
    legacy = tmp_path / "DC-25-13430"
    legacy.mkdir()
    found = find_existing_cause_folder(str(tmp_path), "DC2513430")
    assert found is not None and Path(found).name == "DC-25-13430"


def test_find_existing_cause_folder_returns_none_when_no_match(tmp_path):
    (tmp_path / "OTHER123").mkdir()
    assert find_existing_cause_folder(str(tmp_path), "DC-25-13430") is None


def test_resolve_or_create_case_reuses_legacy_dashed_folder(tmp_path):
    # Simulate a pre-existing legacy folder created with the old un-
    # normalized cause string. resolve_or_create_case must reuse it
    # rather than creating a duplicate at the canonical path.
    legacy_case = tmp_path / "2026" / "Apr" / "DC-25-13430" / "karam_bianca"
    legacy_case.mkdir(parents=True)

    canonical_case = tmp_path / "2026" / "Apr" / "DC2513430" / "karam_bianca"
    assert not canonical_case.exists()

    resolved, _ = resolve_or_create_case(
        str(tmp_path), "DC2513430", "Karam", "Bianca", "2026-04-09"
    )

    assert Path(resolved) == legacy_case
    assert not canonical_case.exists()  # canonical path NOT created


def test_resolve_or_create_case_creates_canonical_when_no_legacy(tmp_path):
    resolved, _ = resolve_or_create_case(
        str(tmp_path), "DC-25-13430", "Karam", "Bianca", "2026-04-09"
    )
    assert Path(resolved) == tmp_path / "2026" / "Apr" / "DC2513430" / "karam_bianca"
    assert Path(resolved).is_dir()
