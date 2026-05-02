from pathlib import Path

import app_logging


def test_rotate_startup_logs_moves_current_logs_to_archive(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    archive_dir = log_dir / "archive"
    log_dir.mkdir()
    (log_dir / "app.log").write_text("current run", encoding="utf-8")
    (log_dir / "errors.log").write_text("errors", encoding="utf-8")

    monkeypatch.setattr(app_logging, "LOG_DIR", log_dir)
    monkeypatch.setattr(app_logging, "ARCHIVE_DIR", archive_dir)

    archived = app_logging.rotate_startup_logs()

    assert len(archived) == 2
    assert not (log_dir / "app.log").exists()
    assert not (log_dir / "errors.log").exists()
    assert archive_dir.is_dir()
    assert sorted(path.name for path in archived) == sorted(
        path.name for path in archive_dir.glob("*.log")
    )


def test_rotate_startup_logs_ignores_missing_logs(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    archive_dir = log_dir / "archive"

    monkeypatch.setattr(app_logging, "LOG_DIR", log_dir)
    monkeypatch.setattr(app_logging, "ARCHIVE_DIR", archive_dir)

    archived = app_logging.rotate_startup_logs()

    assert archived == []
    assert log_dir.is_dir()
    assert archive_dir.is_dir()


def test_rotate_startup_logs_skips_locked_files(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    archive_dir = log_dir / "archive"
    log_dir.mkdir()
    locked_log = log_dir / "app.log"
    locked_log.write_text("locked", encoding="utf-8")

    monkeypatch.setattr(app_logging, "LOG_DIR", log_dir)
    monkeypatch.setattr(app_logging, "ARCHIVE_DIR", archive_dir)

    original_replace = Path.replace

    def _fake_replace(self, target):
        if self == locked_log:
            raise PermissionError("file is locked")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", _fake_replace)

    archived = app_logging.rotate_startup_logs()

    assert archived == []
    assert locked_log.exists()
