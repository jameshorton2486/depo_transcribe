import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
ARCHIVE_DIR = LOG_DIR / "archive"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

RESET = "\033[0m"
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
GRAY = "\033[90m"

LEVEL_COLORS = {
    "DEBUG": GRAY,
    "INFO": GREEN,
    "WARNING": YELLOW,
    "ERROR": RED,
    "CRITICAL": RED,
}


class ColorFormatter(logging.Formatter):
    FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    DATEFMT = "%H:%M:%S"

    def format(self, record):
        color = LEVEL_COLORS.get(record.levelname, RESET)
        return logging.Formatter(
            f"{color}{self.FMT}{RESET}", datefmt=self.DATEFMT
        ).format(record)


class FileFormatter(logging.Formatter):
    FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self):
        super().__init__(fmt=self.FMT, datefmt=self.DATEFMT)


def _make_rotating_handler(filename: str, level: int) -> RotatingFileHandler:
    LOG_DIR.mkdir(exist_ok=True)
    h = RotatingFileHandler(
        LOG_DIR / filename,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    h.setLevel(level)
    h.setFormatter(FileFormatter())
    return h


def _make_console_handler(level: int) -> logging.StreamHandler:
    h = logging.StreamHandler(sys.stdout)
    h.setLevel(level)
    h.setFormatter(ColorFormatter())
    return h


def _setup_root_logger():
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG)
    root.addHandler(_make_console_handler(logging.WARNING))
    root.addHandler(_make_rotating_handler("app.log", logging.INFO))
    root.addHandler(_make_rotating_handler("errors.log", logging.ERROR))
    root.addHandler(_make_rotating_handler("pipeline.log", logging.DEBUG))


def rotate_startup_logs() -> list[Path]:
    """
    Move current run logs into logs/archive/ before a fresh app launch.

    Returns the archive paths created during rotation.
    """
    LOG_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived_paths: list[Path] = []

    for log_file in LOG_DIR.glob("*.log"):
        if not log_file.is_file():
            continue

        archive_path = ARCHIVE_DIR / f"{log_file.stem}_{stamp}{log_file.suffix}"
        counter = 1
        while archive_path.exists():
            archive_path = (
                ARCHIVE_DIR / f"{log_file.stem}_{stamp}_{counter}{log_file.suffix}"
            )
            counter += 1

        try:
            log_file.replace(archive_path)
        except PermissionError:
            continue
        archived_paths.append(archive_path)

    return archived_paths


def get_logger(name: str) -> logging.Logger:
    _setup_root_logger()
    return logging.getLogger(name)


def get_ai_logger() -> logging.Logger:
    _setup_root_logger()
    logger = logging.getLogger("ai")
    if not any(
        isinstance(h, RotatingFileHandler) and "ai.log" in str(h.baseFilename)
        for h in logger.handlers
    ):
        logger.addHandler(_make_rotating_handler("ai.log", logging.DEBUG))
        logger.propagate = True
    return logger


def get_format_logger() -> logging.Logger:
    _setup_root_logger()
    logger = logging.getLogger("formatting")
    if not any(
        isinstance(h, RotatingFileHandler) and "formatting.log" in str(h.baseFilename)
        for h in logger.handlers
    ):
        logger.addHandler(_make_rotating_handler("formatting.log", logging.DEBUG))
        logger.propagate = True
    return logger


def log_section(logger: logging.Logger, title: str):
    bar = "-" * 60
    logger.info(bar)
    logger.info(f"  {title}")
    logger.info(bar)


def log_api_call(
    logger: logging.Logger,
    model: str,
    input_chars: int,
    output_chars: int,
    elapsed_ms: int,
    success: bool,
    error: str = "",
):
    status = "OK" if success else "FAIL"
    msg = (
        f"API {status} | model={model} | "
        f"in={input_chars:,}ch | out={output_chars:,}ch | {elapsed_ms}ms"
    )
    if error:
        msg += f" | error={error[:120]}"
    if success:
        logger.info(msg)
    else:
        logger.error(msg)


# ── Pipeline session tracking ─────────────────────────────────────────────────

_BANNER_WIDTH = 72


def start_pipeline_session(label: str, **context) -> str:
    """
    Write a START banner to pipeline.log marking the beginning of a pipeline run.

    Returns a session_id string (timestamp-based) that can be passed to
    end_pipeline_session() for a matching END banner.

    Args:
        label:    Short description, e.g. "TRANSCRIPTION" or "CORRECTIONS"
        **context: Optional key=value pairs logged with the banner
                   e.g. cause_number="C-2260-25-G", audio_file="coger.wav"

    Usage:
        session_id = start_pipeline_session("TRANSCRIPTION", cause="C-2260-25-G")
        ...
        end_pipeline_session(session_id, "TRANSCRIPTION", success=True, words=12450)
    """
    _setup_root_logger()
    logger = logging.getLogger("pipeline")
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    bar = "═" * _BANNER_WIDTH

    logger.info(bar)
    logger.info("  ▶  START  %s  [%s]", label, session_id)
    for key, val in context.items():
        logger.info("     %-20s %s", f"{key}:", val)
    logger.info(bar)

    return session_id


def end_pipeline_session(
    session_id: str,
    label: str,
    success: bool = True,
    **context,
) -> None:
    """
    Write an END banner to pipeline.log matching a previous start_pipeline_session().

    Args:
        session_id: The value returned by start_pipeline_session()
        label:      Same label used in start_pipeline_session()
        success:    True = completed OK, False = failed
        **context:  Summary values, e.g. corrections=14, words=12450, error="..."
    """
    _setup_root_logger()
    logger = logging.getLogger("pipeline")
    status = "✓  COMPLETE" if success else "✗  FAILED"
    bar = "═" * _BANNER_WIDTH

    logger.info(bar)
    logger.info("  %s  %s  [%s]", status, label, session_id)
    for key, val in context.items():
        logger.info("     %-20s %s", f"{key}:", val)
    logger.info(bar)
    logger.info("")  # blank line between sessions
