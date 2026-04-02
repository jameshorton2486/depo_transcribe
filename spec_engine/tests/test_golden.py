"""
Golden transcript regression tests.

The active golden contract is the correction_runner fixture system:
  spec_engine/tests/golden/{case_name}/
      input.txt
      job_config.json
      expected.txt
      deepgram.json   (optional but preferred)

Each fixture is a committed, human-verified transcript contract. Tests fail
loudly if runtime output changes.

The legacy docx-based `test_coger_golden()` entry point is retained so older
Phase 6 verification checks still import and skip cleanly.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

GOLDEN_DIR = Path(__file__).parent / "golden"
REQUIRED_CASE_FILES = ("input.txt", "job_config.json", "expected.txt")


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

def _discover_correction_cases() -> list[str]:
    if not GOLDEN_DIR.exists():
        return []
    return sorted(
        path.name
        for path in GOLDEN_DIR.iterdir()
        if path.is_dir() and all((path / filename).exists() for filename in REQUIRED_CASE_FILES)
    )


def _validate_correction_fixture(case_name: str) -> None:
    case_dir = GOLDEN_DIR / case_name
    missing = [name for name in REQUIRED_CASE_FILES if not (case_dir / name).exists()]
    assert not missing, f"Golden case '{case_name}' missing required files: {missing}"

    input_text = (case_dir / "input.txt").read_text(encoding="utf-8").strip()
    expected_text = (case_dir / "expected.txt").read_text(encoding="utf-8").strip()
    assert input_text, f"Golden case '{case_name}' has empty input.txt"
    assert expected_text, f"Golden case '{case_name}' has empty expected.txt"

    job_config = json.loads((case_dir / "job_config.json").read_text(encoding="utf-8"))
    assert isinstance(job_config, dict), f"Golden case '{case_name}' job_config.json must be an object"
    ufm = job_config.get("ufm_fields", {})
    assert isinstance(ufm, dict), f"Golden case '{case_name}' ufm_fields must be an object"
    assert ufm.get("speaker_map_verified") is True, (
        f"Golden case '{case_name}' must have speaker_map_verified=true"
    )

    deepgram_json = case_dir / "deepgram.json"
    if deepgram_json.exists():
        payload = json.loads(deepgram_json.read_text(encoding="utf-8"))
        assert isinstance(payload.get("utterances", []), list), (
            f"Golden case '{case_name}' deepgram.json must contain an utterances list"
        )

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
    _validate_correction_fixture(case_name)

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
    corrected_path = results.get("corrected_path")
    assert corrected_path and Path(corrected_path).exists(), (
        f"Correction pipeline did not write corrected_path for '{case_name}'"
    )
    written = Path(corrected_path).read_text(encoding="utf-8").strip()
    assert written == actual, (
        f"Golden case '{case_name}' returned corrected_text that does not match the written file."
    )

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


def test_correction_golden_cases_exist():
    assert _discover_correction_cases(), (
        "No committed golden correction cases found in spec_engine/tests/golden/"
    )


@pytest.mark.parametrize("case_name", _discover_correction_cases())
def test_correction_golden(case_name: str, tmp_path: Path):
    """
    Parametrized correction_runner golden tests discovered from fixture folders.
    """
    _run_correction_golden(case_name, tmp_path)
