"""Run ``pipeline.keyterm_sanitizer`` against a case's saved keyterm
list and emit before / after artifacts for review.

Reads ``<case_dir>/source_docs/job_config.json["deepgram_keyterms"]``
plus ``config.DEFAULT_KEYTERMS`` (matching what the active path
actually sends), runs the sanitizer, and writes under
``output/investigation/keyterm_sanitization/<case_name>/``:

- ``summary.json``           — counts, rule breakdown, token budget
- ``summary.md``             — same data in human-readable form
- ``accepted.md``            — accepted keyterms grouped by category
- ``rejected.md``            — rejected keyterms grouped by reason
- ``final_request_preview.txt`` — the exact list that would be sent

Investigation-only; no production code is touched by this tool.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from config import DEFAULT_KEYTERMS, DEEPGRAM_MAX_KEYTERM_TOKENS
from pipeline.keyterm_sanitizer import (
    SanitizationResult,
    SanitizedKeyterm,
    sanitize_for_deepgram,
)


def _load_keyterms(case_dir: Path) -> list[str]:
    """Pull the keyterm list the same way the UI would have."""
    job_config_path = case_dir / "source_docs" / "job_config.json"
    if not job_config_path.exists():
        raise FileNotFoundError(f"Missing: {job_config_path}")
    data = json.loads(job_config_path.read_text(encoding="utf-8"))
    persisted = list(data.get("deepgram_keyterms") or [])
    # Mirror core/job_runner.py:143 — dedup persisted ∪ DEFAULT_KEYTERMS.
    return list(dict.fromkeys(persisted + DEFAULT_KEYTERMS))


def _by_category(items: list[SanitizedKeyterm]) -> dict[str, list[SanitizedKeyterm]]:
    out: dict[str, list[SanitizedKeyterm]] = defaultdict(list)
    for k in items:
        out[k.category].append(k)
    return out


def _by_reason(items: list[SanitizedKeyterm]) -> dict[str, list[SanitizedKeyterm]]:
    out: dict[str, list[SanitizedKeyterm]] = defaultdict(list)
    for k in items:
        out[k.rejection_reason or "unknown"].append(k)
    return out


def write_outputs(case_dir: Path, out_root: Path) -> Path:
    case_out = out_root / case_dir.name
    case_out.mkdir(parents=True, exist_ok=True)

    raw = _load_keyterms(case_dir)
    result: SanitizationResult = sanitize_for_deepgram(raw)

    # summary.json
    summary_payload: dict[str, Any] = {
        "case_dir": str(case_dir),
        "input_count": len(raw),
        "token_budget": DEEPGRAM_MAX_KEYTERM_TOKENS,
        "stats": result.stats,
        "accepted_count": len(result.accepted),
        "rejected_count": len(result.rejected),
    }
    (case_out / "summary.json").write_text(
        json.dumps(summary_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # summary.md
    md: list[str] = []
    md.append(f"# Keyterm sanitization audit — `{case_dir.name}`")
    md.append("")
    md.append(f"- Input keyterms (post-dedup with DEFAULT_KEYTERMS): **{len(raw)}**")
    md.append(f"- Token budget: **{DEEPGRAM_MAX_KEYTERM_TOKENS}**")
    md.append(f"- Accepted: **{len(result.accepted)}**")
    md.append(f"- Rejected: **{len(result.rejected)}**")
    md.append(f"- Final tokens used: **{result.stats.get('final_tokens', 0)}**")
    md.append("")
    md.append("## Rule breakdown")
    md.append("")
    for k, v in sorted(result.stats.items()):
        if k.startswith("category_"):
            continue
        md.append(f"- `{k}`: **{v}**")
    md.append("")
    md.append("## Accepted by category")
    md.append("")
    for cat, items in sorted(_by_category(result.accepted).items()):
        md.append(f"- `{cat}`: **{len(items)}**")
    md.append("")
    md.append("## Rejected by reason")
    md.append("")
    for reason, items in sorted(_by_reason(result.rejected).items()):
        md.append(f"- `{reason}`: **{len(items)}**")
    md.append("")
    (case_out / "summary.md").write_text("\n".join(md), encoding="utf-8")

    # accepted.md
    am: list[str] = [f"# Accepted keyterms — `{case_dir.name}`", ""]
    for cat, items in sorted(_by_category(result.accepted).items()):
        am.append(f"## `{cat}` — {len(items)} entries")
        am.append("")
        # Sort by score desc within category.
        for k in sorted(items, key=lambda x: (-x.score, x.sanitized.lower())):
            am.append(
                f"- **{k.sanitized}** "
                f"(score={k.score}, tokens={k.token_count})"
            )
        am.append("")
    (case_out / "accepted.md").write_text("\n".join(am), encoding="utf-8")

    # rejected.md
    rm: list[str] = [f"# Rejected keyterms — `{case_dir.name}`", ""]
    for reason, items in sorted(_by_reason(result.rejected).items()):
        rm.append(f"## `{reason}` — {len(items)} entries")
        rm.append("")
        for k in sorted(items, key=lambda x: x.sanitized.lower()):
            rm.append(f"- {k.sanitized}")
        rm.append("")
    (case_out / "rejected.md").write_text("\n".join(rm), encoding="utf-8")

    # final_request_preview.txt — one accepted keyterm per line
    (case_out / "final_request_preview.txt").write_text(
        "\n".join(result.accepted_terms) + "\n",
        encoding="utf-8",
    )

    return case_out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the Deepgram keyterm sanitizer against a case's "
            "persisted keyterm list. No API calls; no production "
            "code changes."
        )
    )
    parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to the case folder.",
    )
    parser.add_argument(
        "--out-root",
        default="output/investigation/keyterm_sanitization",
        help=(
            "Root directory for audit outputs (default: "
            "output/investigation/keyterm_sanitization)."
        ),
    )
    args = parser.parse_args()

    try:
        out = write_outputs(Path(args.case_dir), Path(args.out_root))
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Outputs: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
