"""
core/diff_engine.py

Line-level diff utilities for comparing transcript versions.

Used by:
  - spec_engine/tests/test_golden.py  — failure diagnostics
  - ui/tab_corrections.py             — corrections diff panel
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass
class DiffLine:
    """One line of a computed diff."""
    tag: str     # "equal" | "insert" | "delete" | "replace"
    before: str  # original line  (empty for pure inserts)
    after: str   # corrected line (empty for pure deletes)


def compute_diff(before: str, after: str) -> list[DiffLine]:
    """
    Compare two transcript strings line by line.

    Returns a list of DiffLine objects — one per changed or equal line.
    Only changed lines are included (tag != "equal") unless you need
    context; callers filter as needed.
    """
    before_lines = (before or "").splitlines()
    after_lines  = (after  or "").splitlines()

    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    result: list[DiffLine] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in before_lines[i1:i2]:
                result.append(DiffLine("equal", line, line))
        elif tag == "replace":
            for b, a in zip(before_lines[i1:i2], after_lines[j1:j2]):
                result.append(DiffLine("replace", b, a))
            # Handle length mismatch
            for b in before_lines[i1 + (j2 - j1):i2]:
                result.append(DiffLine("delete", b, ""))
            for a in after_lines[j1 + (i2 - i1):j2]:
                result.append(DiffLine("insert", "", a))
        elif tag == "delete":
            for b in before_lines[i1:i2]:
                result.append(DiffLine("delete", b, ""))
        elif tag == "insert":
            for a in after_lines[j1:j2]:
                result.append(DiffLine("insert", "", a))

    return result


def format_unified_diff(
    before: str,
    after: str,
    fromfile: str = "original",
    tofile: str = "corrected",
) -> str:
    """
    Return a unified diff string (like `diff -u`) for display in logs or tests.

    Empty string means no differences.
    """
    before_lines = (before or "").splitlines(keepends=True)
    after_lines  = (after  or "").splitlines(keepends=True)

    lines = list(difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    ))
    return "\n".join(lines)


def summary(before: str, after: str) -> dict:
    """
    Return a summary dict with counts of inserted, deleted, and replaced lines.

    Used by the corrections tab status bar.
    """
    diff = compute_diff(before, after)
    counts = {"inserts": 0, "deletes": 0, "replaces": 0, "total_changes": 0}
    for d in diff:
        if d.tag == "insert":
            counts["inserts"] += 1
        elif d.tag == "delete":
            counts["deletes"] += 1
        elif d.tag == "replace":
            counts["replaces"] += 1
    counts["total_changes"] = counts["inserts"] + counts["deletes"] + counts["replaces"]
    return counts
