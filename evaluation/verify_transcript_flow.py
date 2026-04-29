"""
Verify the three transcript artifacts for a single case:

1. raw app transcript        -> raw_deepgram.txt
2. manually labeled transcript -> *_transcript.txt after Apply Speaker Labels
3. post-correction transcript  -> *_corrected.txt

This is an artifact-verification tool, not a production pipeline step.

Important design note:
Run Corrections does not transform the manually labeled .txt in place.
It rebuilds transcript blocks from Deepgram JSON and applies the saved
speaker_map from job_config.json. That means:

- raw -> labeled should be prefix-only
- labeled -> corrected is not a pure text rewrite stage
- corrected must be interpreted as JSON + job_config output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.diff_engine import format_unified_diff, summary

RAW_SPEAKER_RE = re.compile(r"^(Speaker\s+\d+):\s*(.*)$")
ANY_LABEL_RE = re.compile(r"^([^:]+):\s*(.*)$")
RAW_LABEL_TOKEN_RE = re.compile(r"\bSpeaker\s+\d+:\s*")


@dataclass
class StagePaths:
    case_root: Path
    raw_path: Path
    labeled_path: Path
    corrected_path: Path | None
    corrections_json_path: Path | None
    job_config_path: Path | None


def _discover_stage_paths(case_root: Path) -> StagePaths:
    if case_root.name.lower() == "deepgram":
        deepgram_dir = case_root
        case_root = case_root.parent
    else:
        deepgram_dir = case_root / "Deepgram"
        if not deepgram_dir.is_dir():
            alt = case_root / "deepgram"
            if alt.is_dir():
                deepgram_dir = alt
            else:
                raise FileNotFoundError(f"Deepgram folder not found under case root: {case_root}")

    raw_path = deepgram_dir / "raw_deepgram.txt"
    if not raw_path.is_file():
        raise FileNotFoundError(f"raw_deepgram.txt not found: {raw_path}")

    transcript_candidates = sorted(
        [
            p for p in deepgram_dir.glob("*_transcript.txt")
            if not p.name.endswith("_corrected.txt")
            and not p.name.endswith("_ai_corrected.txt")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not transcript_candidates:
        raise FileNotFoundError("No labeled/source *_transcript.txt file found.")
    labeled_path = transcript_candidates[0]

    corrected_candidates = sorted(
        deepgram_dir.glob("*_corrected.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    corrected_path = corrected_candidates[0] if corrected_candidates else None

    corrections_json_path = None
    if corrected_path is not None:
        candidate = corrected_path.with_name(
            corrected_path.name.replace("_corrected.txt", "_corrections.json")
        )
        if candidate.is_file():
            corrections_json_path = candidate

    job_config_path = case_root / "source_docs" / "job_config.json"
    if not job_config_path.is_file():
        job_config_path = None

    return StagePaths(
        case_root=case_root,
        raw_path=raw_path,
        labeled_path=labeled_path,
        corrected_path=corrected_path,
        corrections_json_path=corrections_json_path,
        job_config_path=job_config_path,
    )


def _split_label_and_body(line: str, raw_only: bool = False) -> tuple[str | None, str | None]:
    pattern = RAW_SPEAKER_RE if raw_only else ANY_LABEL_RE
    match = pattern.match(line)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _analyze_raw_to_labeled(raw_text: str, labeled_text: str) -> dict:
    raw_lines = raw_text.splitlines()
    labeled_lines = labeled_text.splitlines()
    matcher = SequenceMatcher(None, raw_lines, labeled_lines, autojunk=False)

    prefix_only_changes = 0
    body_changes = 0
    structural_changes = 0
    samples: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        raw_chunk = raw_lines[i1:i2]
        labeled_chunk = labeled_lines[j1:j2]

        if tag == "replace" and len(raw_chunk) == len(labeled_chunk):
            for before, after in zip(raw_chunk, labeled_chunk):
                raw_label, raw_body = _split_label_and_body(before, raw_only=True)
                new_label, new_body = _split_label_and_body(after, raw_only=False)
                if raw_label is not None and new_label is not None and raw_body == new_body:
                    prefix_only_changes += 1
                else:
                    body_changes += 1
                    if len(samples) < 8:
                        samples.append(f"BODY CHANGE\n  RAW: {before}\n  LAB: {after}")
            continue

        structural_changes += 1
        if len(samples) < 8:
            samples.append(
                "STRUCTURAL CHANGE\n"
                f"  RAW LINES: {raw_chunk!r}\n"
                f"  LAB LINES: {labeled_chunk!r}"
            )

    return {
        "prefix_only_changes": prefix_only_changes,
        "body_changes": body_changes,
        "structural_changes": structural_changes,
        "is_prefix_only": body_changes == 0 and structural_changes == 0,
        "samples": samples,
        "diff_summary": summary(raw_text, labeled_text),
    }


def _load_job_context(job_config_path: Path | None) -> dict:
    if job_config_path is None:
        return {"speaker_map_verified": None, "speaker_map": {}, "deepgram_keyterms": []}

    data = json.loads(job_config_path.read_text(encoding="utf-8"))
    ufm = data.get("ufm_fields", {}) if isinstance(data, dict) else {}
    speaker_map = ufm.get("speaker_map", {}) if isinstance(ufm, dict) else {}
    return {
        "speaker_map_verified": ufm.get("speaker_map_verified"),
        "speaker_map": speaker_map,
        "deepgram_keyterms": data.get("deepgram_keyterms", []),
    }


def _load_corrections_summary(corrections_json_path: Path | None) -> dict:
    if corrections_json_path is None:
        return {"correction_count": None, "flag_count": None, "patterns": {}}

    data = json.loads(corrections_json_path.read_text(encoding="utf-8"))
    patterns: dict[str, int] = {}
    for item in data.get("corrections", []):
        pattern = str(item.get("pattern") or "").strip()
        if pattern:
            patterns[pattern] = patterns.get(pattern, 0) + 1
    return {
        "correction_count": data.get("correction_count"),
        "flag_count": data.get("flag_count"),
        "patterns": dict(sorted(patterns.items(), key=lambda kv: (-kv[1], kv[0]))[:10]),
    }


def _render_report(paths: StagePaths) -> str:
    raw_text = paths.raw_path.read_text(encoding="utf-8")
    labeled_text = paths.labeled_path.read_text(encoding="utf-8")
    corrected_text = (
        paths.corrected_path.read_text(encoding="utf-8")
        if paths.corrected_path and paths.corrected_path.is_file()
        else None
    )

    raw_to_labeled = _analyze_raw_to_labeled(raw_text, labeled_text)
    labeled_to_corrected = summary(labeled_text, corrected_text or "") if corrected_text is not None else None
    raw_to_corrected = summary(raw_text, corrected_text or "") if corrected_text is not None else None
    job = _load_job_context(paths.job_config_path)
    corr = _load_corrections_summary(paths.corrections_json_path)

    lines: list[str] = []
    lines.append("# Transcript Flow Verification")
    lines.append("")
    lines.append("## Artifact Paths")
    lines.append("")
    lines.append(f"- Case root: `{paths.case_root}`")
    lines.append(f"- Raw transcript: `{paths.raw_path.name}`")
    lines.append(f"- Manually labeled transcript: `{paths.labeled_path.name}`")
    lines.append(f"- Corrected transcript: `{paths.corrected_path.name if paths.corrected_path else '[missing]'}`")
    lines.append(f"- Corrections JSON: `{paths.corrections_json_path.name if paths.corrections_json_path else '[missing]'}`")
    lines.append("")
    lines.append("## Design Truth")
    lines.append("")
    lines.append("- `Apply Speaker Labels` mutates the transcript `.txt` by replacing only `Speaker N:` prefixes.")
    lines.append("- `Run Corrections` does not parse that `.txt` body; it rebuilds from Deepgram JSON and applies `speaker_map` from `job_config.json`.")
    lines.append("- Therefore raw -> labeled is a strict prefix-only stage, while labeled -> corrected is an artifact comparison, not a direct in-place rewrite stage.")
    lines.append("")
    lines.append("## Job Config State")
    lines.append("")
    lines.append(f"- `speaker_map_verified`: `{job['speaker_map_verified']}`")
    lines.append(f"- `speaker_map` entries: `{len(job['speaker_map'])}`")
    lines.append(f"- `deepgram_keyterms`: `{len(job['deepgram_keyterms'])}`")
    lines.append("")
    lines.append("## Stage 1: Raw -> Manually Labeled")
    lines.append("")
    lines.append(f"- Prefix-only changes: `{raw_to_labeled['prefix_only_changes']}`")
    lines.append(f"- Body changes: `{raw_to_labeled['body_changes']}`")
    lines.append(f"- Structural changes: `{raw_to_labeled['structural_changes']}`")
    lines.append(f"- Invariant status: `{'PASS' if raw_to_labeled['is_prefix_only'] else 'FAIL'}`")
    lines.append("")
    if raw_to_labeled["samples"]:
        lines.append("### Stage 1 Violations")
        lines.append("")
        lines.extend(f"- {sample}" for sample in raw_to_labeled["samples"])
        lines.append("")

    if corrected_text is None:
        lines.append("## Stage 2: Manually Labeled -> Corrected")
        lines.append("")
        lines.append("- Corrected transcript missing; stage cannot be evaluated.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Stage 2: Manually Labeled -> Corrected")
    lines.append("")
    lines.append(f"- Line replacements: `{labeled_to_corrected['replaces']}`")
    lines.append(f"- Line inserts: `{labeled_to_corrected['inserts']}`")
    lines.append(f"- Line deletes: `{labeled_to_corrected['deletes']}`")
    lines.append(f"- Total line changes: `{labeled_to_corrected['total_changes']}`")
    lines.append(f"- Raw `Speaker N:` labels remaining in corrected output: `{len(RAW_LABEL_TOKEN_RE.findall(corrected_text))}`")
    lines.append("")
    lines.append("Expected for this stage:")
    lines.append("- body corrections may occur")
    lines.append("- Q/A restructuring may occur")
    lines.append("- objection extraction may occur")
    lines.append("- formatting changes may occur")
    lines.append("- raw `Speaker N:` labels should not remain once speaker mapping is verified")
    lines.append("")
    lines.append("## Corrections Audit")
    lines.append("")
    lines.append(f"- Correction records: `{corr['correction_count']}`")
    lines.append(f"- Scopist flags: `{corr['flag_count']}`")
    if corr["patterns"]:
        lines.append("- Top correction patterns:")
        for name, count in corr["patterns"].items():
            lines.append(f"  - `{name}`: {count}")
    lines.append("")
    lines.append("## Stage 3: Raw -> Corrected")
    lines.append("")
    lines.append(f"- Line replacements: `{raw_to_corrected['replaces']}`")
    lines.append(f"- Line inserts: `{raw_to_corrected['inserts']}`")
    lines.append(f"- Line deletes: `{raw_to_corrected['deletes']}`")
    lines.append(f"- Total line changes: `{raw_to_corrected['total_changes']}`")
    lines.append("")
    lines.append("## Unified Diff Snapshots")
    lines.append("")
    lines.append("### Raw -> Labeled")
    lines.append("")
    diff_1 = format_unified_diff(raw_text, labeled_text, "raw_deepgram", "labeled_transcript")
    lines.append("```diff")
    lines.append((diff_1 or "[no changes]")[:12000])
    lines.append("```")
    lines.append("")
    lines.append("### Labeled -> Corrected")
    lines.append("")
    diff_2 = format_unified_diff(labeled_text, corrected_text, "labeled_transcript", "corrected_transcript")
    lines.append("```diff")
    lines.append((diff_2 or "[no changes]")[:12000])
    lines.append("```")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify raw -> labeled -> corrected transcript artifacts.")
    parser.add_argument(
        "--case-root",
        required=True,
        help="Case root directory containing Deepgram/ and source_docs/.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output report path. Default: <case-root>/transcript_flow_verification.md",
    )
    args = parser.parse_args(argv)

    case_root = Path(args.case_root).resolve()
    paths = _discover_stage_paths(case_root)
    report = _render_report(paths)

    output_path = (
        Path(args.output).resolve()
        if args.output
        else case_root / "transcript_flow_verification.md"
    )
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
