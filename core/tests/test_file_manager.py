from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.file_manager import (
    build_case_path,
    create_case_folders,
    verify_case_folders,
)


def test_build_case_path_uses_required_structure():
    path = build_case_path("C:\\Depositions", "2025CI19595", "Coger", "Matthew", "03/24/2026")
    expected = os.path.join("2026", "Mar", "2025CI19595", "coger_matthew")
    assert path.endswith(expected)


def test_create_case_folders_creates_required_subfolders(tmp_path):
    create_case_folders(str(tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew"))
    assert (tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew" / "source_docs").is_dir()


def test_verify_case_folders_reports_valid_after_creation(tmp_path):
    case_path = tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew"
    create_case_folders(str(case_path))
    assert verify_case_folders(str(case_path))["valid"] is True
