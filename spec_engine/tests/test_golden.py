"""
Golden transcript regression tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

GOLDEN_DIR = Path(__file__).parent / "golden"


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
