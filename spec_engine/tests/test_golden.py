"""
Golden transcript regression tests.

Two test types:
  1. spec_engine/processor tests  — parse a .docx, run process_blocks(),
     compare block-level output with expected.txt
     (original system — files in golden/  named  {case}_input.docx etc.)

  2. correction_runner tests      — set up a real Deepgram folder structure,
     run run_correction_job(), compare corrected_text with expected.txt
     (new system — files in golden/{case_name}/  subfolders)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

GOLDEN_DIR = Path(__file__).parent / "golden"


# ── Type 1: spec_engine/processor tests (original) ───────────────────────────

def _run_golden(name: str):
    input_docx = GOLDEN_DIR / f"{name}_input.docx"
    config_json = GOLDEN_DIR / f"{name}_job_config.json"
    expected_txt = GOLDEN_DIR / f"{name}_expected.txt"

    if not all(path.exists() for path in [input_docx, config_json, expected_txt]):
        pytest.skip(
            f"Golden files for '{name}' not yet committed to spec_engine/tests/golden/. See README.md."
        )

    from spec_engine.models import JobConfig
    from spec_engine.parser import parse_blocks
    from spec_engine.processor import process_blocks

    cfg = JobConfig.from_json(config_json.read_text(encoding="utf-8"))
    blocks = parse_blocks(str(input_docx))
    result = process_blocks(blocks, cfg)

    actual_lines = []
    for block in result:
        block_type = block.block_type.value if hasattr(block.block_type, "value") else str(block.block_type)
        actual_lines.append(f"{block_type}: {block.text}")
    actual = "\n".join(actual_lines)

    expected = expected_txt.read_text(encoding="utf-8")
    assert actual.strip() == expected.strip()


def test_coger_golden():
    _run_golden("coger")


def test_golden_dir_exists():
    assert GOLDEN_DIR.exists()


# ── Type 2: correction_runner integration tests ───────────────────────────────

def _run_correction_golden(case_name: str, tmp_path: Path):
    """
    End-to-end golden test for the correction_runner pipeline.

    Folder structure required in golden/{case_name}/:
        input.txt         — raw transcript (Speaker N: format)
        deepgram.json     — Deepgram utterances JSON (optional but recommended)
        job_config.json   — full job_config with ufm_fields + confirmed_spellings
        expected.txt      — verified corrected output (locked to pipeline output)

    On failure, prints a unified diff so the exact regression is visible.
    """
    case_dir = GOLDEN_DIR / case_name

    required = [case_dir / "input.txt", case_dir / "job_config.json", case_dir / "expected.txt"]
    if not all(p.exists() for p in required):
        pytest.skip(
            f"Golden files for correction case '{case_name}' not committed. "
            f"Required: input.txt, job_config.json, expected.txt"
        )

    # ── Build real folder structure ───────────────────────────────────────────
    deepgram_dir = tmp_path / "Deepgram"
    source_docs  = tmp_path / "source_docs"
    deepgram_dir.mkdir()
    source_docs.mkdir()

    stem = f"{case_name}_golden"
    shutil.copy(case_dir / "input.txt",       deepgram_dir / f"{stem}.txt")
    shutil.copy(case_dir / "job_config.json", source_docs  / "job_config.json")

    deepgram_json = case_dir / "deepgram.json"
    if deepgram_json.exists():
        shutil.copy(deepgram_json, deepgram_dir / f"{stem}.json")

    # ── Run correction pipeline ───────────────────────────────────────────────
    from core.correction_runner import run_correction_job

    results: dict = {}
    run_correction_job(
        transcript_path=str(deepgram_dir / f"{stem}.txt"),
        done_callback=lambda r: results.update(r),
    )

    assert results.get("success"), (
        f"Correction pipeline FAILED for '{case_name}': {results.get('error')}"
    )

    actual   = (results.get("corrected_text") or "").strip()
    expected = (case_dir / "expected.txt").read_text(encoding="utf-8").strip()

    if actual == expected:
        return  # ✓ PASS

    # ── Failure: print unified diff ───────────────────────────────────────────
    from core.diff_engine import format_unified_diff

    diff_output = format_unified_diff(expected, actual, fromfile="expected", tofile="actual")
    pytest.fail(
        f"\nGolden test FAILED: '{case_name}'\n"
        f"Corrections applied: {results.get('correction_count', 0)}\n\n"
        f"{diff_output}"
    )


@pytest.mark.parametrize("case_name", ["case_001"])
def test_correction_golden(case_name: str, tmp_path: Path):
    """
    Parametrized correction_runner golden tests.
    Add new case names to the list above as cases are committed.
    """
    _run_correction_golden(case_name, tmp_path)

