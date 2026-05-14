"""One-shot walkthrough driver for a specific case folder.

Given a case directory that already contains raw Deepgram output at
``Deepgram/raw_deepgram.txt`` + ``Deepgram/raw_deepgram.json``, this
script walks the transcript through every transformation the
application performs and saves a numbered snapshot per stage into
``<case_dir>/_walkthrough/``.

It is intentionally NOT a production component — it is a debugging /
inspection utility. Adds one real Anthropic API call (1-2 chunks
typically), no Deepgram call.

Stages captured:

  Active path (Start Transcription):
    01_deepgram_raw.txt              raw Deepgram chunk-merged text (existing)
    02a_low_conf_marked.txt          after inject_markers (input to Anthropic)
    02b_anthropic_raw_response.txt   raw Anthropic chunks concatenated
    02_after_ai_cleanup.txt          after _postprocess_formatted_text
    03_docx_text.txt                 paragraph text from produced DOCX

  Offline spec_engine path (Run Corrections button):
    10_spec_engine_blocks.txt        after block_builder.build_blocks
    11_spec_engine_classified.txt    after classifier.classify_blocks
    12_spec_engine_corrected.txt     after corrections.apply_corrections
    13_spec_engine_qa_fixed.txt      after qa_fixer.enforce_structure
    14_spec_engine_speaker_mapped.txt after speaker_mapper.normalize_speakers
    15_spec_engine_emitted.txt       after emitter.emit_blocks

  Summary:
    00_walkthrough_summary.md        table + observations

Usage::

    python -m tools.walkthrough.run_all_stages "<case_dir>"
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from pathlib import Path
from typing import Any

from clean_format.formatter import (
    CHUNK_CHAR_LIMIT,
    MAX_TOKENS,
    _build_client,
    _postprocess_formatted_text,
    _response_text,
    build_user_message,
    load_deepgram_words_from_json,
    split_transcript,
)
from clean_format.docx_writer import write_deposition_docx
from clean_format.low_confidence_markers import (
    inject_markers,
    count_markers,
)
from clean_format.prompt import CLEAN_FORMAT_SYSTEM_PROMPT
from config import LOW_CONFIDENCE_THRESHOLD
from core.config import AI_MODEL

from spec_engine.block_builder import build_blocks
from spec_engine.classifier import classify_blocks
from spec_engine.corrections import apply_corrections
from spec_engine.qa_fixer import enforce_structure
from spec_engine.speaker_mapper import normalize_speakers
from spec_engine.emitter import emit_blocks


HEADER_SEPARATOR = "=" * 50


def _count_changed_lines(before: str, after: str) -> int:
    """Approximate line-diff count between two text blobs.

    Counts every '+' / '-' line in a unified diff (excluding hunk
    headers). Returns 0 if either input is empty.
    """
    if not before or not after:
        return 0
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        n=0,
        lineterm="",
    )
    return sum(
        1
        for line in diff
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )


def _build_header(
    stage: str,
    module: str,
    function: str,
    input_file: str,
    changed_lines: int,
    active_path: bool,
    extra: str = "",
) -> str:
    body = (
        f"{HEADER_SEPARATOR}\n"
        f"Stage: {stage}\n"
        f"Module: {module}\n"
        f"Function called: {function}\n"
        f"Input: {input_file}\n"
        f"Lines changed vs input: {changed_lines}\n"
        f"Active path? {'Yes' if active_path else 'No'}\n"
        f"{HEADER_SEPARATOR}\n"
    )
    if extra:
        body += f"{extra}\n{HEADER_SEPARATOR}\n"
    return body


def _serialize_blocks_classifier(blocks: list[Any]) -> str:
    """Serialize TranscriptBlock objects (or block dicts) as one line each.

    Format: ``[TYPE] [SPEAKER] text``
    Block dicts (from build_blocks) lack a classified type, so they
    serialize as ``[paragraph|utterance] [SPEAKER] text``.
    """
    lines = []
    for block in blocks:
        if isinstance(block, dict):
            btype = block.get("type", "")
            speaker = str(block.get("speaker", "")).strip()
            text = (block.get("text") or "").strip()
        else:
            btype = getattr(block, "type", "")
            speaker = str(getattr(block, "speaker", "") or "").strip()
            text = (getattr(block, "text", "") or "").strip()
        lines.append(f"[{btype}] [{speaker}] {text}")
    return "\n".join(lines)


def _adapt_saved_utterances(utterances: list[dict]) -> list[dict]:
    """Same adapter as core/corrections_runner._adapt_saved_utterances.

    Local copy so the walkthrough driver does not import a private
    helper from another module.
    """
    out: list[dict] = []
    for u in utterances or []:
        if not isinstance(u, dict):
            continue
        text = (u.get("transcript") or u.get("text") or "").strip()
        if not text:
            continue
        speaker = u.get("speaker_label")
        if not speaker:
            raw_speaker = u.get("speaker")
            speaker = (
                f"Speaker {raw_speaker}"
                if raw_speaker is not None
                else "UNKNOWN"
            )
        out.append({"speaker": str(speaker), "text": text, "type": "utterance"})
    return out


def _docx_paragraph_text(path: Path) -> str:
    """Extract paragraph text from a DOCX file."""
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def _format_transcript_with_capture(
    raw_text: str,
    case_meta: dict[str, Any],
    deepgram_words: list[dict[str, Any]] | None,
    walkthrough_dir: Path,
) -> tuple[str, dict[str, Any]]:
    """Mirror format_transcript but capture each intermediate stage.

    Returns (final_formatted_text, stats). Stats includes per-chunk
    marker drift counts and elapsed seconds.
    """
    marked_text = (
        inject_markers(
            raw_text, deepgram_words, threshold=LOW_CONFIDENCE_THRESHOLD
        )
        if deepgram_words
        else raw_text
    )

    chunks = split_transcript(marked_text, max_chunk_chars=CHUNK_CHAR_LIMIT)
    api_client = _build_client(None)
    selected_model = AI_MODEL

    raw_responses: list[str] = []
    postprocessed: list[str] = []
    drift_stats: list[dict[str, int]] = []

    start = time.time()
    for index, chunk in enumerate(chunks, start=1):
        response = api_client.messages.create(
            model=selected_model,
            max_tokens=MAX_TOKENS,
            system=CLEAN_FORMAT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_user_message(
                        chunk, case_meta, index, len(chunks)
                    ),
                }
            ],
        )
        response_text = _response_text(response)
        raw_responses.append(response_text)
        postprocessed.append(_postprocess_formatted_text(response_text))
        drift_stats.append({
            "chunk_index": index,
            "input_markers": count_markers(chunk),
            "output_markers": count_markers(response_text),
        })
    elapsed = time.time() - start

    raw_response_text = "\n\n".join(raw_responses)
    final_text = "\n\n".join(
        part for part in postprocessed if part.strip()
    ).strip()

    stats = {
        "chunks": len(chunks),
        "elapsed_seconds": round(elapsed, 1),
        "drift": drift_stats,
        "model": selected_model,
    }

    return marked_text, raw_response_text, final_text, stats


def run(case_dir: Path) -> dict[str, Any]:
    case_dir = case_dir.resolve()
    walkthrough_dir = case_dir / "_walkthrough"
    walkthrough_dir.mkdir(parents=True, exist_ok=True)

    raw_txt_path = case_dir / "Deepgram" / "raw_deepgram.txt"
    raw_json_path = case_dir / "Deepgram" / "raw_deepgram.json"
    case_meta_path = case_dir / "case_meta.json"

    for required in (raw_txt_path, raw_json_path, case_meta_path):
        if not required.exists():
            raise FileNotFoundError(f"Required file missing: {required}")

    raw_text = raw_txt_path.read_text(encoding="utf-8")
    case_meta = json.loads(case_meta_path.read_text(encoding="utf-8"))
    deepgram_words = load_deepgram_words_from_json(raw_json_path)

    summary: dict[str, Any] = {"files": [], "stages": []}

    def write_stage(
        name: str,
        header: str,
        body: str,
        *,
        active_path: bool,
        module: str,
        function: str,
        input_file: str,
        changed: int,
        description: str,
    ) -> Path:
        target = walkthrough_dir / f"{name}.txt"
        target.write_text(header + body, encoding="utf-8")
        summary["stages"].append({
            "name": name,
            "module": module,
            "function": function,
            "input_file": input_file,
            "changed_lines": changed,
            "active_path": active_path,
            "description": description,
        })
        summary["files"].append(target.name)
        return target

    # -------------------------------------------------------------------
    # ACTIVE PATH — 02a / 02b / 02 / 03
    # -------------------------------------------------------------------
    raw_json_data = json.loads(raw_json_path.read_text(encoding="utf-8"))

    marked_text, raw_response, final_text, ai_stats = (
        _format_transcript_with_capture(
            raw_text=raw_text,
            case_meta=case_meta,
            deepgram_words=deepgram_words,
            walkthrough_dir=walkthrough_dir,
        )
    )

    marked_markers = count_markers(marked_text)
    raw_resp_markers = count_markers(raw_response)
    final_markers = count_markers(final_text)

    # 02a — after inject_markers
    changed = _count_changed_lines(raw_text, marked_text)
    extra = f"Low-confidence markers injected: {marked_markers}"
    write_stage(
        "02a_low_conf_marked",
        _build_header(
            "02a",
            "clean_format/low_confidence_markers.py",
            "inject_markers",
            "01_deepgram_raw.txt",
            changed,
            active_path=True,
            extra=extra,
        ),
        marked_text,
        active_path=True,
        module="clean_format/low_confidence_markers.py",
        function="inject_markers",
        input_file="01_deepgram_raw.txt",
        changed=changed,
        description=(
            "Wraps Deepgram tokens with confidence < threshold in "
            "‹LC:...› markers so the cleanup model preserves them and "
            "the DOCX writer renders them as yellow highlights."
        ),
    )

    # 02b — raw Anthropic response (pre-postprocess)
    changed = _count_changed_lines(marked_text, raw_response)
    drift_summary = "; ".join(
        f"chunk {d['chunk_index']}: in={d['input_markers']} out={d['output_markers']}"
        for d in ai_stats["drift"]
    )
    extra = (
        f"Model: {ai_stats['model']}\n"
        f"Chunks: {ai_stats['chunks']}\n"
        f"Elapsed: {ai_stats['elapsed_seconds']}s\n"
        f"Marker counts per chunk: {drift_summary}\n"
        f"Total markers preserved (raw): {raw_resp_markers} of {marked_markers}"
    )
    write_stage(
        "02b_anthropic_raw_response",
        _build_header(
            "02b",
            "clean_format/formatter.py",
            "Anthropic messages.create (per chunk)",
            "02a_low_conf_marked.txt",
            changed,
            active_path=True,
            extra=extra,
        ),
        raw_response,
        active_path=True,
        module="clean_format/formatter.py",
        function="messages.create",
        input_file="02a_low_conf_marked.txt",
        changed=changed,
        description=(
            "Single Anthropic Claude cleanup pass per chunk using the "
            "strict-verbatim prompt. This is the model's raw output "
            "before any deterministic post-processing."
        ),
    )

    # 02 — after _postprocess_formatted_text (final clean_format output)
    changed = _count_changed_lines(raw_response, final_text)
    extra = (
        f"Markers preserved after postprocess: {final_markers} of {marked_markers}"
    )
    write_stage(
        "02_after_ai_cleanup",
        _build_header(
            "02",
            "clean_format/formatter.py",
            "_postprocess_formatted_text",
            "02b_anthropic_raw_response.txt",
            changed,
            active_path=True,
            extra=extra,
        ),
        final_text,
        active_path=True,
        module="clean_format/formatter.py",
        function="_postprocess_formatted_text",
        input_file="02b_anthropic_raw_response.txt",
        changed=changed,
        description=(
            "Deterministic touch-ups after Anthropic: speaker-label "
            "normalization (COURT REPORTER -> THE REPORTER, etc.), "
            "title spacing (Dr. / Mr. / Ms.), em-dash normalization, "
            "and double-space-after-sentence."
        ),
    )

    # 03 — DOCX text
    witness_last = (
        case_meta.get("witness_name", "Witness").split() or ["Witness"]
    )[-1]
    date_part = (
        str(case_meta.get("deposition_date", ""))
        .replace("/", "-")
        .replace(",", "")
    )
    docx_path = case_dir / f"{witness_last}_Deposition_{date_part}.docx"
    saved_path = write_deposition_docx(final_text, case_meta, docx_path)
    docx_text = _docx_paragraph_text(Path(saved_path))
    changed = _count_changed_lines(final_text, docx_text)
    extra = f"DOCX written to: {saved_path}"
    write_stage(
        "03_docx_text",
        _build_header(
            "03",
            "clean_format/docx_writer.py",
            "write_deposition_docx",
            "02_after_ai_cleanup.txt",
            changed,
            active_path=True,
            extra=extra,
        ),
        docx_text,
        active_path=True,
        module="clean_format/docx_writer.py",
        function="write_deposition_docx",
        input_file="02_after_ai_cleanup.txt",
        changed=changed,
        description=(
            "Renders the cleaned text into the final deposition Word "
            "document with caption table, appearances, examination "
            "header, and Q/A tab stops. Low-confidence markers are "
            "stripped at render time and the bracketed text becomes "
            "yellow-highlighted runs."
        ),
    )

    summary["ai"] = {
        "model": ai_stats["model"],
        "chunks": ai_stats["chunks"],
        "elapsed_seconds": ai_stats["elapsed_seconds"],
        "input_markers": marked_markers,
        "raw_response_markers": raw_resp_markers,
        "final_markers": final_markers,
        "markers_dropped": max(0, marked_markers - final_markers),
        "drop_pct": (
            round((marked_markers - final_markers) / marked_markers * 100, 1)
            if marked_markers
            else 0.0
        ),
    }
    summary["docx_path"] = str(saved_path)

    # -------------------------------------------------------------------
    # OFFLINE SPEC_ENGINE PATH — 10 through 15
    # -------------------------------------------------------------------
    utterances = raw_json_data.get("utterances") or []
    adapted = _adapt_saved_utterances(utterances)
    alt = {"utterances": adapted}

    # 10 — block_builder.build_blocks
    blocks_raw = build_blocks(alt)
    blocks_text = _serialize_blocks_classifier(blocks_raw)
    # Compare blocks rendering against raw transcript (just for a
    # rough "how different is this from the input" feel — not exact)
    changed = _count_changed_lines(raw_text, blocks_text)
    extra = f"Blocks built: {len(blocks_raw)}  (utterance branch — no paragraphs in raw_deepgram.json)"
    write_stage(
        "10_spec_engine_blocks",
        _build_header(
            "10",
            "spec_engine/block_builder.py",
            "build_blocks",
            "Deepgram/raw_deepgram.json (utterances)",
            changed,
            active_path=False,
            extra=extra,
        ),
        blocks_text,
        active_path=False,
        module="spec_engine/block_builder.py",
        function="build_blocks",
        input_file="raw_deepgram.json/utterances",
        changed=changed,
        description=(
            "Parses raw Deepgram utterances into {speaker, text, type, "
            "words} dicts. Priority is paragraph-based; falls back to "
            "utterance-based when paragraphs are absent (our case)."
        ),
    )

    # 11 — classifier.classify_blocks
    classified = classify_blocks(blocks_raw)
    classified_text = _serialize_blocks_classifier(classified)
    changed = _count_changed_lines(blocks_text, classified_text)
    type_counts: dict[str, int] = {}
    for b in classified:
        type_counts[b.type] = type_counts.get(b.type, 0) + 1
    extra = "Type counts: " + ", ".join(
        f"{k}={v}" for k, v in sorted(type_counts.items())
    )
    write_stage(
        "11_spec_engine_classified",
        _build_header(
            "11",
            "spec_engine/classifier.py",
            "classify_blocks",
            "10_spec_engine_blocks.txt",
            changed,
            active_path=False,
            extra=extra,
        ),
        classified_text,
        active_path=False,
        module="spec_engine/classifier.py",
        function="classify_blocks",
        input_file="10_spec_engine_blocks.txt",
        changed=changed,
        description=(
            "Tags each block with a structural type: question, answer, "
            "directive ('BY MR/MS X:'), oath, or colloquy. Detection "
            "is regex- and keyword-based."
        ),
    )

    # 12 — corrections.apply_corrections
    confirmed_spellings = case_meta.get("confirmed_spellings") or {}
    keyterms = case_meta.get("deepgram_keyterms") or []
    corrected = apply_corrections(
        classified,
        confirmed_spellings=confirmed_spellings,
        keyterms=keyterms,
    )
    corrected_text = _serialize_blocks_classifier(corrected)
    changed = _count_changed_lines(classified_text, corrected_text)
    extra = (
        f"Confirmed spellings applied: {len(confirmed_spellings)}\n"
        f"Keyterms supplied: {len(keyterms)}"
    )
    write_stage(
        "12_spec_engine_corrected",
        _build_header(
            "12",
            "spec_engine/corrections.py",
            "apply_corrections",
            "11_spec_engine_classified.txt",
            changed,
            active_path=False,
            extra=extra,
        ),
        corrected_text,
        active_path=False,
        module="spec_engine/corrections.py",
        function="apply_corrections",
        input_file="11_spec_engine_classified.txt",
        changed=changed,
        description=(
            "Applies proper-noun corrections (confirmed_spellings + "
            "legal dictionary + keyterms), then Morson's rules: "
            "whitespace cleanup, em-dash normalization, sentence-start "
            "capitalization, small-number spelling, stutter spacing, "
            "short-answer commas, default-period terminal punctuation."
        ),
    )

    # 13 — qa_fixer.enforce_structure
    try:
        qa_fixed = enforce_structure(corrected)
        qa_fixed_text = _serialize_blocks_classifier(qa_fixed)
        qa_extra = ""
    except Exception as exc:
        qa_fixed = corrected  # keep pipeline going for downstream snapshots
        qa_fixed_text = (
            f"### enforce_structure raised: {type(exc).__name__}: {exc}\n"
            "### Falling back to unfixed corrected blocks for downstream stages.\n\n"
            + _serialize_blocks_classifier(corrected)
        )
        qa_extra = f"NOTE: enforce_structure raised {type(exc).__name__}; downstream stages use unfixed input."
    changed = _count_changed_lines(corrected_text, qa_fixed_text)
    write_stage(
        "13_spec_engine_qa_fixed",
        _build_header(
            "13",
            "spec_engine/qa_fixer.py",
            "enforce_structure",
            "12_spec_engine_corrected.txt",
            changed,
            active_path=False,
            extra=qa_extra,
        ),
        qa_fixed_text,
        active_path=False,
        module="spec_engine/qa_fixer.py",
        function="enforce_structure",
        input_file="12_spec_engine_corrected.txt",
        changed=changed,
        description=(
            "Enforces strict Q/A sequence: re-types ambiguous blocks "
            "after a question, merges same-speaker question "
            "continuations, attaches examiner attribution from "
            "directive ('BY ...') lines. Raises if it detects a "
            "structural violation (e.g. consecutive questions from "
            "different speakers)."
        ),
    )

    # 14 — speaker_mapper.normalize_speakers
    speaker_mapped = normalize_speakers(qa_fixed)
    speaker_mapped_text = _serialize_blocks_classifier(speaker_mapped)
    changed = _count_changed_lines(qa_fixed_text, speaker_mapped_text)
    write_stage(
        "14_spec_engine_speaker_mapped",
        _build_header(
            "14",
            "spec_engine/speaker_mapper.py",
            "normalize_speakers",
            "13_spec_engine_qa_fixed.txt",
            changed,
            active_path=False,
        ),
        speaker_mapped_text,
        active_path=False,
        module="spec_engine/speaker_mapper.py",
        function="normalize_speakers",
        input_file="13_spec_engine_qa_fixed.txt",
        changed=changed,
        description=(
            "Normalizes speaker labels to uppercase + trailing colon "
            "('SPEAKER 1:'), normalizes 'BY ...:' directive text, "
            "smooths short cross-speaker fragments, and propagates "
            "the final speaker label down into per-word metadata."
        ),
    )

    # 15 — emitter.emit_blocks
    emitted_text = emit_blocks(speaker_mapped)
    changed = _count_changed_lines(speaker_mapped_text, emitted_text)
    write_stage(
        "15_spec_engine_emitted",
        _build_header(
            "15",
            "spec_engine/emitter.py",
            "emit_blocks",
            "14_spec_engine_speaker_mapped.txt",
            changed,
            active_path=False,
        ),
        emitted_text,
        active_path=False,
        module="spec_engine/emitter.py",
        function="emit_blocks",
        input_file="14_spec_engine_speaker_mapped.txt",
        changed=changed,
        description=(
            "Renders the classified+corrected blocks into the final "
            "plain-text transcript: 'Q.\\t...' / 'A.\\t...' for Q/A, "
            "three-tab prefix for colloquy/directive, sentence "
            "double-spacing, time-of-day normalization."
        ),
    )

    return summary


def write_summary(case_dir: Path, summary: dict[str, Any]) -> Path:
    walkthrough_dir = case_dir / "_walkthrough"
    summary_path = walkthrough_dir / "00_walkthrough_summary.md"

    lines: list[str] = []
    lines.append("# Walkthrough Summary")
    lines.append("")
    lines.append(f"Case: `{case_dir}`")
    lines.append("")
    lines.append("## Stage table")
    lines.append("")
    lines.append(
        "| Stage | Module | Function | Input | Lines changed | Active path? | What it does |"
    )
    lines.append("|---|---|---|---|---:|:---:|---|")
    for s in summary["stages"]:
        lines.append(
            f"| {s['name'].split('_')[0]} | `{s['module']}` | `{s['function']}` | "
            f"{s['input_file']} | {s['changed_lines']} | "
            f"{'Yes' if s['active_path'] else 'No'} | {s['description']} |"
        )
    lines.append("")

    # AI / drift report
    ai = summary.get("ai", {})
    if ai:
        lines.append("## Anthropic cleanup stats")
        lines.append("")
        lines.append(f"- Model: `{ai['model']}`")
        lines.append(f"- Chunks: {ai['chunks']}")
        lines.append(f"- Elapsed: {ai['elapsed_seconds']}s")
        lines.append(f"- Low-confidence markers injected (input): {ai['input_markers']}")
        lines.append(
            f"- Markers preserved in raw response: {ai['raw_response_markers']}"
        )
        lines.append(
            f"- Markers preserved after post-process: {ai['final_markers']}"
        )
        lines.append(
            f"- Markers dropped vs input: {ai['markers_dropped']} ({ai['drop_pct']}%)"
        )
        lines.append("")
        lines.append(f"DOCX written: `{summary.get('docx_path', '?')}`")
        lines.append("")

    # Top / bottom by line-diff
    ranked = sorted(
        summary["stages"], key=lambda s: s["changed_lines"], reverse=True
    )
    top3 = ranked[:3]
    bottom3 = [s for s in ranked if s["changed_lines"] > 0][-3:]

    lines.append("## Modules that changed the transcript the most")
    lines.append("")
    for s in top3:
        lines.append(
            f"- **{s['name']}** — {s['changed_lines']} lines changed. "
            f"{s['description']}"
        )
    lines.append("")
    lines.append("## Modules that barely changed anything")
    lines.append("")
    for s in bottom3:
        lines.append(
            f"- **{s['name']}** — {s['changed_lines']} lines changed. "
            f"{s['description']}"
        )
    lines.append("")

    lines.append("## Active path vs offline path")
    lines.append("")
    lines.append(
        "Files 01 / 02a / 02b / 02 / 03 are the **active path** — the "
        "pipeline that runs when you press Start Transcription. The "
        "DOCX `03_docx_text.txt` is the artifact the user actually "
        "sees."
    )
    lines.append("")
    lines.append(
        "Files 10 through 15 are the **offline spec_engine path** — "
        "deterministic correction stages reachable only via the Run "
        "Corrections button (`core/corrections_runner.py`). They are "
        "not invoked by Start Transcription. Compare 15's emitted "
        "text against 02's AI cleanup output to see whether the "
        "deterministic path is doing work the active path doesn't."
    )
    lines.append("")

    lines.append("## What to read first")
    lines.append("")
    lines.append(
        "1. `02_after_ai_cleanup.txt` — what the Anthropic model does to "
        "the raw transcript. Biggest single transformation in the "
        "active path."
    )
    lines.append(
        "2. `03_docx_text.txt` — the final user-visible artifact. "
        "Compare against 02 to see what the DOCX layout adds."
    )
    lines.append(
        "3. `15_spec_engine_emitted.txt` — the offline-path final text. "
        "Compare against 02 to evaluate whether spec_engine is doing "
        "useful work the active path is missing."
    )
    lines.append("")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run every transcript-transformation stage and snapshot "
            "the output for inspection."
        )
    )
    parser.add_argument(
        "case_dir",
        help="Path to the case folder (must contain Deepgram/raw_deepgram.txt and .json plus case_meta.json).",
    )
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    try:
        summary = run(case_dir)
        summary_path = write_summary(case_dir, summary)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print(f"Summary: {summary_path}")
    for fname in summary["files"]:
        print(f"  {fname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
