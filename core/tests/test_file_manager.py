from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.file_manager import (
    build_case_path,
    create_case_folders,
    load_job_vocabulary,
    save_job_vocabulary,
    verify_case_folders,
)


def test_build_case_path_uses_required_structure():
    path = build_case_path("C:\\Depositions", "2025CI19595", "Coger", "Matthew", "03/24/2026")
    assert path.endswith("2026\\Mar\\2025CI19595\\coger_matthew")


def test_create_case_folders_creates_required_subfolders(tmp_path):
    create_case_folders(str(tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew"))
    assert (tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew" / "source_docs").is_dir()


def test_verify_case_folders_reports_valid_after_creation(tmp_path):
    case_path = tmp_path / "2026" / "Mar" / "2025CI19595" / "coger_matthew"
    create_case_folders(str(case_path))
    assert verify_case_folders(str(case_path))["valid"] is True


def test_save_job_vocabulary_creates_file(tmp_path):
    saved = save_job_vocabulary(
        case_folder=str(tmp_path),
        intake_result=None,
        final_keyterms=["Matthew Coger", "Murphy Oil USA"],
        reporter_terms=[],
    )
    assert saved is not None
    assert os.path.isfile(saved)


def test_save_job_vocabulary_content(tmp_path):
    save_job_vocabulary(
        case_folder=str(tmp_path),
        intake_result=None,
        final_keyterms=["Matthew Coger", "Murphy Oil USA"],
        reporter_terms=["Smith System"],
    )
    data = load_job_vocabulary(str(tmp_path))
    assert data is not None
    assert "Matthew Coger" in data["final_keyterms"]
    assert "Smith System" in data["reporter_terms"]


def test_load_job_vocabulary_returns_none_if_missing(tmp_path):
    assert load_job_vocabulary(str(tmp_path)) is None


def test_save_job_vocabulary_term_counts(tmp_path):
    save_job_vocabulary(
        case_folder=str(tmp_path),
        intake_result=None,
        final_keyterms=[f"Term {i}" for i in range(15)],
    )
    data = load_job_vocabulary(str(tmp_path))
    assert data["term_counts"]["total"] == 15


def test_save_job_vocabulary_saves_timestamp(tmp_path):
    save_job_vocabulary(str(tmp_path), None, ["Matthew Coger"])
    data = load_job_vocabulary(str(tmp_path))
    assert "saved_at" in data
    assert len(data["saved_at"]) > 0


def test_save_job_vocabulary_invalid_folder():
    result = save_job_vocabulary(
        case_folder="C:/does/not/exist",
        intake_result=None,
        final_keyterms=["Test"],
    )
    assert result is None
