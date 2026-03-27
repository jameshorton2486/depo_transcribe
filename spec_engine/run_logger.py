"""
Per-run diagnostic logging for the DepoPro transcript pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from app_logging import get_logger

_APP_ROOT = Path(__file__).resolve().parent.parent
_LOG_BASE = _APP_ROOT / "logs"
_RUNS_DIR = _LOG_BASE / "runs"

_logger = get_logger(__name__)


def _serialise(obj: Any) -> Any:
    """Recursively convert dataclasses and enums to JSON-safe values."""
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for field_name in obj.__dataclass_fields__:
            result[field_name] = _serialise(getattr(obj, field_name))
        return result
    if isinstance(obj, list):
        return [_serialise(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if hasattr(obj, "value"):
        return obj.value
    return obj


class RunLogger:
    """
    Manages one timestamped diagnostic session for a single transcript run.
    """

    def __init__(self, cause_number: str = ""):
        safe = re.sub(r"[^\w\-]", "_", cause_number or "unknown")
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = f"{ts}_{safe}" if safe != "unknown" else ts

        self.run_dir = _RUNS_DIR / name
        self._log = self.run_dir / "pipeline.log"
        self._corr = self.run_dir / "corrections.jsonl"
        self._start = datetime.now()
        self._steps = 0
        self._corrections = 0

        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self._write(f"=== DepoPro Run Start ===  cause={cause_number or '(none)'}")
            self._write(f"run_dir={self.run_dir}")
            _logger.info("RunLogger started: %s", self.run_dir)
        except Exception as exc:
            _logger.warning("RunLogger init failed: %s", exc)

    def log_step(self, message: str, **stats) -> None:
        self._steps += 1
        stat_str = "  ".join(f"{k}={v}" for k, v in stats.items())
        line = f"[STEP {self._steps:02d}] {message}"
        if stat_str:
            line += f"  |  {stat_str}"
        self._write(line)

    def log_warning(self, message: str) -> None:
        self._write(f"[WARN]  {message}")
        _logger.warning("[RUN] %s", message)

    def log_error(self, message: str, exc: Optional[Exception] = None) -> None:
        self._write(f"[ERROR] {message}")
        if exc:
            self._write(f"        {type(exc).__name__}: {exc}")
        _logger.error("[RUN] %s", message, exc_info=exc)

    def snapshot(self, name: str, blocks: List[Any]) -> None:
        path = self.run_dir / f"{name}.json"
        try:
            data = [_serialise(b) for b in blocks]
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._write(f"[SNAP]  {name}.json  ({len(blocks)} blocks)")
        except Exception as exc:
            self.log_error(f"snapshot({name}) failed", exc=exc)

    def log_correction(
        self,
        block_index: int,
        original: str,
        corrected: str,
        rule: str,
        confidence: str = "HIGH",
    ) -> None:
        self._corrections += 1
        record = {
            "n": self._corrections,
            "block": block_index,
            "original": (original or "")[:300],
            "corrected": (corrected or "")[:300],
            "rule": rule,
            "confidence": confidence,
        }
        try:
            with self._corr.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            _logger.warning("Correction log write failed: %s", exc)

    def log_corrections_from_blocks(self, blocks: List[Any]) -> None:
        for block in blocks:
            records = (getattr(block, "meta", {}) or {}).get("corrections", [])
            for record in records:
                self.log_correction(
                    block_index=getattr(record, "block_index", 0),
                    original=getattr(record, "original", ""),
                    corrected=getattr(record, "corrected", ""),
                    rule=getattr(record, "pattern", ""),
                )

    def write_diff(self, before_text: str, after_text: str) -> None:
        path = self.run_dir / "diff.txt"
        before_lines = (before_text or "").splitlines()
        after_lines = (after_text or "").splitlines()
        max_len = max(len(before_lines), len(after_lines), 1)

        diff_lines: List[str] = []
        changes = 0
        for i in range(max_len):
            before = before_lines[i] if i < len(before_lines) else ""
            after = after_lines[i] if i < len(after_lines) else ""
            if before != after:
                diff_lines.append(f"-  {before}")
                diff_lines.append(f"+  {after}")
                diff_lines.append("")
                changes += 1

        try:
            content = "\n".join(diff_lines) if diff_lines else "(No differences detected)"
            path.write_text(content, encoding="utf-8")
            self._write(f"[DIFF]  diff.txt  ({changes} changed line(s))")
        except Exception as exc:
            self.log_error("write_diff failed", exc=exc)

    def write_validation(self, validation_result: Any) -> None:
        path = self.run_dir / "validation_report.txt"
        errors = getattr(validation_result, "errors", [])
        warnings = getattr(validation_result, "warnings", [])
        passed = getattr(validation_result, "passed", not errors)

        lines = [
            "=== VALIDATION REPORT ===",
            f"Status: {'PASSED' if passed else 'FAILED'}",
            f"Errors: {len(errors)}   Warnings: {len(warnings)}",
            "",
        ]
        if errors:
            lines.append(f"ERRORS ({len(errors)}):")
            lines.extend(f"  ✗  {error}" for error in errors)
            lines.append("")
        if warnings:
            lines.append(f"WARNINGS ({len(warnings)}):")
            lines.extend(f"  ⚠  {warning}" for warning in warnings)

        try:
            path.write_text("\n".join(lines), encoding="utf-8")
            self._write(
                f"[VALID] validation_report.txt  ({len(errors)} error(s), {len(warnings)} warning(s))"
            )
        except Exception as exc:
            self.log_error("write_validation failed", exc=exc)

    def close(self, success: bool = True) -> None:
        elapsed = (datetime.now() - self._start).total_seconds()
        self._write(
            f"=== Run {'Complete' if success else 'FAILED'} ===  "
            f"steps={self._steps}  corrections={self._corrections}  elapsed={elapsed:.1f}s"
        )
        _logger.info(
            "RunLogger closed: %s  steps=%d  corrections=%d  elapsed=%.1fs",
            self.run_dir.name,
            self._steps,
            self._corrections,
            elapsed,
        )

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close(success=(exc_type is None))
        return False

    def _write(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            with self._log.open("a", encoding="utf-8") as fh:
                fh.write(f"{ts}  {message}\n")
        except Exception:
            pass
