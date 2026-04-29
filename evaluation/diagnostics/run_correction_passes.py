"""
run_correction_passes.py

Diagnostic. Runs every public function exposed in spec_engine.corrections.__all__
against a single input transcript and reports which functions modified the text
and which did not.

This script is intentionally narrow:
  - It exercises only functions in spec_engine.corrections.__all__.
  - It calls each function with the transcript text as the sole positional
    argument. Functions whose signatures require additional arguments are
    skipped with a recorded reason.
  - It does not invoke core/correction_runner.py or any pipeline orchestration.
  - It writes a single Markdown report next to the input file. It does not
    modify any source files or fixtures.

Usage:
    python evaluation/diagnostics/run_correction_passes.py \
        --input evaluation/fixtures/caram_raw_2026-04-09.txt
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class PassResult:
    name: str
    fired: bool
    runnable: bool
    delta_chars: int
    sample_before: Optional[str]
    sample_after: Optional[str]
    skip_reason: Optional[str]
    log_output: str


def _first_diff_window(before: str, after: str, ctx: int = 60) -> tuple[str, str]:
    """Return a small window around the first character that differs between
    before and after, with newlines escaped for table rendering."""
    if before == after:
        return "", ""
    n = min(len(before), len(after))
    i = 0
    while i < n and before[i] == after[i]:
        i += 1
    start = max(0, i - ctx)
    end_b = min(len(before), i + ctx)
    end_a = min(len(after), i + ctx)

    def _esc(s: str) -> str:
        return s.replace("\n", "\\n").replace("|", "\\|").replace("`", "'")

    return _esc(before[start:end_b]), _esc(after[start:end_a])


def run_diagnostic(input_path: Path) -> List[PassResult]:
    text = input_path.read_text(encoding="utf-8")

    module = importlib.import_module("spec_engine.corrections")
    public_names = list(getattr(module, "__all__", []) or [])

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)
    spec_logger = logging.getLogger("spec_engine")
    spec_logger.addHandler(handler)
    prior_level = spec_logger.level
    spec_logger.setLevel(logging.DEBUG)

    results: List[PassResult] = []
    try:
        for name in public_names:
            fn = getattr(module, name, None)
            if fn is None or not callable(fn):
                results.append(PassResult(name, False, False, 0, None, None,
                                          "not callable or missing", ""))
                continue

            log_capture.seek(0)
            log_capture.truncate()

            try:
                out = fn(text)
            except TypeError as exc:
                results.append(PassResult(name, False, False, 0, None, None,
                                          f"signature mismatch: {exc}",
                                          log_capture.getvalue()))
                continue
            except Exception as exc:
                results.append(PassResult(name, False, True, 0, None, None,
                                          f"{type(exc).__name__}: {exc}",
                                          log_capture.getvalue()))
                continue

            if not isinstance(out, str):
                results.append(PassResult(name, False, False, 0, None, None,
                                          f"return type is {type(out).__name__}, not str",
                                          log_capture.getvalue()))
                continue

            fired = out != text
            delta = len(out) - len(text)
            sb, sa = (_first_diff_window(text, out) if fired else (None, None))
            results.append(PassResult(name, fired, True, delta, sb, sa, None,
                                      log_capture.getvalue()))
    finally:
        spec_logger.removeHandler(handler)
        spec_logger.setLevel(prior_level)

    return results


def render_report(results: List[PassResult], input_path: Path) -> str:
    fired = [r for r in results if r.fired]
    no_match = [r for r in results if r.runnable and not r.fired and r.skip_reason is None]
    skipped = [r for r in results if not r.runnable]
    errored = [r for r in results if r.runnable and not r.fired and r.skip_reason is not None]

    size = input_path.stat().st_size
    lines: List[str] = []
    lines.append("# Correction Pass Diagnostic")
    lines.append("")
    lines.append(f"Input: `{input_path}` ({size} bytes)")
    lines.append("")
    lines.append(f"- Functions discovered: {len(results)}")
    lines.append(f"- Fired (text changed): {len(fired)}")
    lines.append(f"- No match (ran, no change): {len(no_match)}")
    lines.append(f"- Skipped (signature/type): {len(skipped)}")
    lines.append(f"- Errored (raised exception): {len(errored)}")
    lines.append("")

    lines.append("## Fired")
    lines.append("")
    if not fired:
        lines.append("_None._")
    else:
        lines.append("| Function | delta chars | Before | After |")
        lines.append("|---|---:|---|---|")
        for r in fired:
            sb = (r.sample_before or "")[:120]
            sa = (r.sample_after or "")[:120]
            lines.append(f"| `{r.name}` | {r.delta_chars:+d} | `{sb}` | `{sa}` |")
    lines.append("")

    lines.append("## No match (ran cleanly, did not change text)")
    lines.append("")
    if not no_match:
        lines.append("_None._")
    else:
        for r in no_match:
            lines.append(f"- `{r.name}`")
    lines.append("")

    lines.append("## Skipped (signature or type)")
    lines.append("")
    if not skipped:
        lines.append("_None._")
    else:
        lines.append("| Function | Reason |")
        lines.append("|---|---|")
        for r in skipped:
            lines.append(f"| `{r.name}` | {r.skip_reason or 'unknown'} |")
    lines.append("")

    lines.append("## Errored")
    lines.append("")
    if not errored:
        lines.append("_None._")
    else:
        lines.append("| Function | Exception |")
        lines.append("|---|---|")
        for r in errored:
            lines.append(f"| `{r.name}` | {r.skip_reason or 'unknown'} |")
    lines.append("")

    lines.append("## Logger output (spec_engine, DEBUG and up)")
    lines.append("")
    has_logs = any(r.log_output for r in results)
    if not has_logs:
        lines.append("_No log output captured during any pass._")
    else:
        lines.append("```")
        for r in results:
            if r.log_output:
                lines.append(f"--- {r.name} ---")
                lines.append(r.log_output.rstrip())
        lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run spec_engine.corrections functions against a transcript and report hit/miss."
    )
    parser.add_argument("--input", required=True,
                        help="Path to raw transcript text file (UTF-8).")
    parser.add_argument("--output", default=None,
                        help="Output Markdown report path. Default: <input>.diagnostic.md")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 2
    if input_path.stat().st_size == 0:
        print(f"ERROR: input file is empty: {input_path}", file=sys.stderr)
        return 2

    output_path = (Path(args.output).resolve()
                   if args.output
                   else input_path.with_suffix(input_path.suffix + ".diagnostic.md"))

    results = run_diagnostic(input_path)
    report = render_report(results, input_path)
    output_path.write_text(report, encoding="utf-8")

    fired_count = sum(1 for r in results if r.fired)
    no_match_count = sum(1 for r in results if r.runnable and not r.fired and r.skip_reason is None)
    skipped_count = sum(1 for r in results if not r.runnable)
    errored_count = sum(1 for r in results if r.runnable and not r.fired and r.skip_reason is not None)

    print("Diagnostic complete.")
    print(f"  Discovered: {len(results)}")
    print(f"  Fired:      {fired_count}")
    print(f"  No match:   {no_match_count}")
    print(f"  Skipped:    {skipped_count}")
    print(f"  Errored:    {errored_count}")
    print(f"Report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
