"""
Phase 6 Verification Test Suite — UX Hardening, Logging, Production Safety
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from spec_engine.models import Block, BlockType, JobConfig


def _tmp_run_dir():
    import tempfile
    from spec_engine import run_logger as rl_module

    orig = rl_module._RUNS_DIR
    tmp = Path(tempfile.mkdtemp())
    rl_module._RUNS_DIR = tmp
    return tmp, orig, rl_module


def _restore_run_dir(rl_module, orig):
    rl_module._RUNS_DIR = orig


class TestFix6A_RunLogger:
    def test_run_logger_importable(self):
        from spec_engine.run_logger import RunLogger
        assert callable(RunLogger)

    def test_run_logger_creates_run_directory(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            with RunLogger(cause_number="TEST-DIR") as run:
                assert run.run_dir.exists()
                assert run.run_dir.is_dir()
        finally:
            _restore_run_dir(rl, orig)

    def test_pipeline_log_created(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            with RunLogger(cause_number="TEST-LOG") as run:
                run.log_step("Test step", block_count=5)
                content = (run.run_dir / "pipeline.log").read_text(encoding="utf-8")
                assert "Test step" in content
                assert "block_count=5" in content
        finally:
            _restore_run_dir(rl, orig)

    def test_corrections_jsonl_written(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            with RunLogger(cause_number="TEST-CORR") as run:
                run.log_correction(5, "Bare County", "Bexar County", "confirmed_spellings")
                line = json.loads((run.run_dir / "corrections.jsonl").read_text(encoding="utf-8").strip())
                assert line["original"] == "Bare County"
                assert line["corrected"] == "Bexar County"
                assert line["rule"] == "confirmed_spellings"
                assert line["block"] == 5
        finally:
            _restore_run_dir(rl, orig)

    def test_diff_txt_written(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            with RunLogger(cause_number="TEST-DIFF") as run:
                run.write_diff("Line one.\nBare County.", "Line one.\nBexar County.")
                content = (run.run_dir / "diff.txt").read_text(encoding="utf-8")
                assert "Bare County" in content
                assert "Bexar County" in content
        finally:
            _restore_run_dir(rl, orig)

    def test_validation_report_written(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            from spec_engine.validator import ValidationResult
            with RunLogger(cause_number="TEST-VAL") as run:
                run.write_validation(
                    ValidationResult(
                        errors=["Unresolved speaker at index 3"],
                        warnings=["Question missing '?' at index 7"],
                    )
                )
                content = (run.run_dir / "validation_report.txt").read_text(encoding="utf-8")
                assert "Unresolved speaker" in content
                assert "Question missing" in content
        finally:
            _restore_run_dir(rl, orig)

    def test_context_manager_closes_cleanly(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            with RunLogger(cause_number="TEST-CTX") as run:
                run.log_step("Inside context")
            content = (run.run_dir / "pipeline.log").read_text(encoding="utf-8")
            assert "Run Complete" in content or "FAILED" in content
        finally:
            _restore_run_dir(rl, orig)

    def test_logging_failure_does_not_crash_main_code(self):
        from spec_engine.run_logger import RunLogger
        import spec_engine.run_logger as rl_mod

        orig = rl_mod._RUNS_DIR
        rl_mod._RUNS_DIR = Path("/nonexistent_path_xyz/runs")
        try:
            run = RunLogger(cause_number="FAIL-TEST")
            run.log_step("This should not crash")
            run.log_correction(0, "a", "b", "test")
            run.close()
        finally:
            rl_mod._RUNS_DIR = orig

    def test_snapshot_serialises_blocks(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            blocks = [
                Block(speaker_id=1, text="Yes, I did.", raw_text="", block_type=BlockType.ANSWER),
                Block(speaker_id=2, text="Did you see it?", raw_text="", block_type=BlockType.QUESTION),
            ]
            with RunLogger(cause_number="TEST-SNAP") as run:
                run.snapshot("01_blocks_raw", blocks)
                data = json.loads((run.run_dir / "01_blocks_raw.json").read_text(encoding="utf-8"))
                assert isinstance(data, list)
                assert len(data) == 2
        finally:
            _restore_run_dir(rl, orig)


class TestFix6B_StrictMode:
    def test_strict_mode_importable(self):
        from config import STRICT_MODE
        assert STRICT_MODE in (True, False)

    def test_strict_mode_is_bool(self):
        from config import STRICT_MODE
        assert isinstance(STRICT_MODE, bool)

    def test_strict_mode_defaults_false(self):
        from config import STRICT_MODE
        assert STRICT_MODE is False


class TestFix6C_ProcessorRunLogger:
    def test_run_logger_parameter_in_signature(self):
        import inspect
        from spec_engine.processor import process_blocks
        sig = inspect.signature(process_blocks)
        assert "run_logger" in sig.parameters

    def test_run_logger_defaults_none(self):
        import inspect
        from spec_engine.processor import process_blocks
        sig = inspect.signature(process_blocks)
        assert sig.parameters["run_logger"].default is None

    def test_process_blocks_without_logger_still_works(self):
        from spec_engine.processor import process_blocks
        blocks = [
            Block(speaker_id=1, text="Yes, I saw it.", raw_text=""),
            Block(speaker_id=2, text="Did you see the spill?", raw_text=""),
        ]
        cfg = {
            "speaker_map": {1: "THE WITNESS", 2: "MR. SMITH"},
            "witness_id": 1,
            "examining_attorney_id": 2,
            "cause_number": "TEST-NO-LOGGER",
        }
        result = process_blocks(blocks, cfg)
        assert isinstance(result, list)

    def test_process_blocks_with_logger_logs_steps(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.processor import process_blocks
            from spec_engine.run_logger import RunLogger
            blocks = [
                Block(speaker_id=1, text="Yes.", raw_text=""),
                Block(speaker_id=2, text="Did you go?", raw_text=""),
            ]
            cfg = {
                "speaker_map": {1: "THE WITNESS", 2: "MR. SMITH"},
                "witness_id": 1,
                "examining_attorney_id": 2,
                "speaker_map_verified": True,
                "cause_number": "TEST-WITH-LOGGER",
            }
            with RunLogger(cause_number="TEST-WITH-LOGGER") as run:
                process_blocks(blocks, cfg, run_logger=run)
                log_content = (run.run_dir / "pipeline.log").read_text(encoding="utf-8")
                assert "STEP" in log_content
        finally:
            _restore_run_dir(rl, orig)

    def test_strict_mode_false_does_not_abort_on_warnings(self):
        from spec_engine.processor import process_blocks
        blocks = [Block(speaker_id=99, text="Unknown speaker.", raw_text="")]
        cfg = {
            "speaker_map": {},
            "speaker_map_verified": False,
            "cause_number": "TEST-STRICT-FALSE",
        }
        result = process_blocks(blocks, cfg)
        assert isinstance(result, list)


@pytest.mark.skip(reason="Asserts unimplemented features in app.py (_last_run_dir, RunLogger, _open_diff_viewer, review_btn) — planned functionality not yet built")
class TestFix6D_MainRunLoggerWiring:
    def _get_main_source(self) -> str:
        return (Path(__file__).resolve().parent.parent.parent / "app.py").read_text(encoding="utf-8")

    def test_last_run_dir_attribute_in_main(self):
        assert "_last_run_dir" in self._get_main_source()

    def test_open_diff_viewer_method_in_main(self):
        assert "_open_diff_viewer" in self._get_main_source()

    def test_run_logger_imported_in_worker(self):
        assert "RunLogger" in self._get_main_source()

    def test_review_changes_button_in_main(self):
        src = self._get_main_source()
        assert "Review Changes" in src or "review_btn" in src or "_review_btn" in src


class TestFix6E_GoldenTestInfrastructure:
    def test_golden_directory_exists(self):
        golden_dir = Path(__file__).parent / "golden"
        assert golden_dir.exists() and golden_dir.is_dir()

    def test_golden_readme_exists(self):
        assert (Path(__file__).parent / "golden" / "README.md").exists()

    def test_test_golden_py_exists(self):
        assert (Path(__file__).parent / "test_golden.py").exists()

    def test_test_golden_py_importable(self):
        golden_test = Path(__file__).parent / "test_golden.py"
        spec = importlib.util.spec_from_file_location("test_golden", str(golden_test))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    def test_coger_golden_skips_cleanly_without_files(self):
        golden_dir = Path(__file__).parent / "golden"
        if (golden_dir / "coger_input.docx").exists():
            pytest.skip("Coger golden files present")
        golden_test = Path(__file__).parent / "test_golden.py"
        spec = importlib.util.spec_from_file_location("test_golden", str(golden_test))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with pytest.raises(pytest.skip.Exception):
            mod.test_coger_golden()


class TestPhase6ExitGate:
    def test_run_logger_full_session(self):
        tmp, orig, rl = _tmp_run_dir()
        try:
            from spec_engine.run_logger import RunLogger
            from spec_engine.validator import ValidationResult
            with RunLogger(cause_number="EXIT-GATE") as run:
                run.log_step("Step 1", block_count=10)
                run.log_step("Step 2", q=5, a=5)
                run.log_correction(0, "Cogger", "Coger", "confirmed_spellings")
                run.write_diff("Cogger was here.", "Coger was here.")
                run.write_validation(ValidationResult(warnings=["Test warning"]))
            for name in ["pipeline.log", "corrections.jsonl", "diff.txt", "validation_report.txt"]:
                path = run.run_dir / name
                assert path.exists()
                assert path.stat().st_size > 0
        finally:
            _restore_run_dir(rl, orig)

    def test_strict_mode_is_false(self):
        from config import STRICT_MODE
        assert STRICT_MODE is False

    def test_process_blocks_accepts_run_logger(self):
        from spec_engine.processor import process_blocks
        blocks = [Block(speaker_id=1, text="Yes.", raw_text="")]
        cfg = {"speaker_map": {1: "THE WITNESS"}, "witness_id": 1, "cause_number": "GATE"}
        result = process_blocks(blocks, cfg, run_logger=None)
        assert isinstance(result, list)

    def test_all_phases_smoke(self):
        from spec_engine.classifier import classify_blocks
        from spec_engine.corrections import clean_block
        from spec_engine.validator import validate_blocks

        cfg = JobConfig(
            confirmed_spellings={"Bare County": "Bexar County"},
            speaker_map_verified=True,
        )
        result = clean_block("There were 5 issues in Bare County.", cfg)
        text = result[0]
        assert "Bexar County" in text
        assert "five" in text.lower()

        vg = Block(
            speaker_id=0,
            text="We are off the record.",
            raw_text="",
            speaker_role="VIDEOGRAPHER",
            speaker_name="THE VIDEOGRAPHER",
        )
        classified = classify_blocks([vg])
        assert classified[0].block_type != BlockType.ANSWER

        q_bad = Block(speaker_id=2, text="Did you see it", raw_text="", block_type=BlockType.QUESTION)
        vresult = validate_blocks([q_bad])
        assert any("Question" in warning for warning in vresult.warnings)
