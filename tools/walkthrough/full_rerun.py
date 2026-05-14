"""End-to-end pipeline rerun on an existing case folder.

Drives the same pipeline the Start-Transcription button drives, but
from a CLI:

1. Pulls metadata from ``<case_dir>/case_meta.json`` and
   ``<case_dir>/source_docs/job_config.json``.
2. Discovers the original audio file from
   ``<case_dir>/Deepgram/raw_deepgram.json["audio_file"]``.
3. Invokes ``core.job_runner.run_transcription_job`` to re-run
   Deepgram on the original audio (real API call; writes
   ``Deepgram/raw_deepgram.{txt,json}`` plus a timestamped pair).
4. Invokes ``clean_format.formatter.format_transcript`` on the new
   raw transcript (the speaker_turn_repair stage runs automatically
   inside that function), then writes a new DOCX via
   ``clean_format.docx_writer.write_deposition_docx``.
5. Prints a summary including the ``[SPEAKER_REPAIR]`` /
   ``[MERGE]`` log lines emitted along the way.

Real API spend: one Deepgram prerecorded call (~$0.36 for an 83-min
deposition on Nova-3) plus one Anthropic cleanup pass (~$2 for 1-2
chunks). Do NOT run casually.

Usage::

    python -m tools.walkthrough.full_rerun --case-dir "<case_dir>"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


def _resolve_base_dir(case_dir: Path) -> Path:
    """Return the depositions root for ``case_dir``.

    Case-folder layout produced by ``core.file_manager``::

        <base>/<year>/<month>/<cause_number>/<last_first>/

    So the base dir is the great-grandparent of the case folder.
    """
    # case_dir / last_first → cause_number → month → year → base
    return case_dir.parent.parent.parent.parent


def _load_metadata(case_dir: Path) -> dict[str, Any]:
    case_meta_path = case_dir / "case_meta.json"
    job_config_path = case_dir / "source_docs" / "job_config.json"
    raw_json_path = case_dir / "Deepgram" / "raw_deepgram.json"

    for required in (case_meta_path, job_config_path, raw_json_path):
        if not required.exists():
            raise FileNotFoundError(f"Required file missing: {required}")

    case_meta = json.loads(case_meta_path.read_text(encoding="utf-8"))
    job_config = json.loads(job_config_path.read_text(encoding="utf-8"))
    raw_json = json.loads(raw_json_path.read_text(encoding="utf-8"))

    audio_path = raw_json.get("audio_file")
    if not audio_path or not Path(audio_path).exists():
        raise FileNotFoundError(
            f"Original audio file not found: {audio_path!r}"
        )

    witness_name = (case_meta.get("witness_name") or "").strip()
    if not witness_name:
        raise RuntimeError(
            "case_meta.json has no witness_name; cannot resolve case folder."
        )
    parts = witness_name.split()
    first_name = parts[0]
    last_name = parts[-1] if len(parts) > 1 else parts[0]

    return {
        "audio_path": audio_path,
        "model": job_config.get("model") or "nova-3",
        "quality": job_config.get("audio_quality") or "ENHANCED (fair audio)",
        "cause_number": case_meta.get("cause_number", ""),
        "first_name": first_name,
        "last_name": last_name,
        "date_str": case_meta.get("deposition_date", ""),
        "keyterms": case_meta.get("deepgram_keyterms")
        or job_config.get("deepgram_keyterms")
        or [],
        "confirmed_spellings": case_meta.get("confirmed_spellings")
        or job_config.get("confirmed_spellings")
        or {},
        "ufm_fields": job_config.get("ufm_fields"),
        "case_meta": case_meta,
    }


def _run_deepgram(meta: dict[str, Any], base_dir: Path) -> dict[str, Any] | None:
    """Run the production transcription job. Returns the done_callback result."""
    from core.job_runner import run_transcription_job

    captured: dict[str, Any] = {}

    def on_progress(pct: float, msg: str) -> None:
        print(f"[PROGRESS {pct:>5.1f}%] {msg}")

    def on_log(msg: str) -> None:
        print(f"[LOG] {msg}")

    def on_done(result: dict[str, Any]) -> None:
        captured.update(result)

    print(f"[DEEPGRAM] starting — audio={meta['audio_path']}")
    print(
        f"[DEEPGRAM] model={meta['model']} quality={meta['quality']} "
        f"keyterms={len(meta['keyterms'])} spellings={len(meta['confirmed_spellings'])}"
    )
    t0 = time.time()
    run_transcription_job(
        audio_path=meta["audio_path"],
        model=meta["model"],
        quality=meta["quality"],
        base_dir=str(base_dir),
        cause_number=meta["cause_number"],
        last_name=meta["last_name"],
        first_name=meta["first_name"],
        date_str=meta["date_str"],
        keyterms=meta["keyterms"] or None,
        confirmed_spellings=meta["confirmed_spellings"],
        ufm_fields=meta["ufm_fields"],
        progress_callback=on_progress,
        log_callback=on_log,
        done_callback=on_done,
    )
    elapsed = time.time() - t0
    print(f"[DEEPGRAM] complete in {elapsed:.1f}s — result keys: {list(captured.keys())}")
    return captured


def _run_clean_format(
    case_dir: Path,
    case_meta: dict[str, Any],
) -> dict[str, Any]:
    """Run Anthropic cleanup (with speaker_turn_repair active) + DOCX."""
    from clean_format import format_transcript, write_deposition_docx
    from clean_format.formatter import load_deepgram_words_from_json

    raw_txt_path = case_dir / "Deepgram" / "raw_deepgram.txt"
    raw_json_path = case_dir / "Deepgram" / "raw_deepgram.json"

    if not raw_txt_path.exists():
        raise FileNotFoundError(f"Missing raw transcript: {raw_txt_path}")

    raw_text = raw_txt_path.read_text(encoding="utf-8")
    deepgram_words = load_deepgram_words_from_json(raw_json_path)

    # case_meta.json was written by _run_clean_format_job in the UI;
    # we re-use the existing one rather than re-extracting from
    # job_config so the cleanup prompt sees the same metadata the UI
    # would have sent.
    print(f"[CLEAN_FORMAT] raw_text chars={len(raw_text)} words={len(deepgram_words) if deepgram_words else 0}")
    t0 = time.time()
    formatted_text = format_transcript(
        raw_text, case_meta, deepgram_words=deepgram_words
    )
    elapsed = time.time() - t0
    print(
        f"[CLEAN_FORMAT] Anthropic done in {elapsed:.1f}s "
        f"— formatted chars={len(formatted_text)}"
    )

    witness_last = (
        case_meta.get("witness_name", "Witness").split() or ["Witness"]
    )[-1]
    date_part = (
        str(case_meta.get("deposition_date", ""))
        .replace("/", "-")
        .replace(",", "")
    )
    docx_path = case_dir / f"{witness_last}_Deposition_{date_part}.docx"
    saved = write_deposition_docx(formatted_text, case_meta, docx_path)
    print(f"[CLEAN_FORMAT] DOCX written: {saved}")

    return {"formatted_chars": len(formatted_text), "docx_path": str(saved)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-run Deepgram + clean_format end-to-end on an existing "
            "case folder. Real API spend."
        )
    )
    parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to the case folder.",
    )
    args = parser.parse_args()

    case_dir = Path(args.case_dir).resolve()
    if not case_dir.exists():
        print(f"ERROR: case folder not found: {case_dir}")
        return 1

    try:
        meta = _load_metadata(case_dir)
        base_dir = _resolve_base_dir(case_dir)
        print(f"[CONFIG] base_dir={base_dir}  case_dir={case_dir}")

        deepgram_result = _run_deepgram(meta, base_dir)
        if not deepgram_result or not deepgram_result.get("output_dir"):
            print("ERROR: Deepgram run did not produce a valid result.")
            return 1

        # Re-load case_meta in case the new run overwrote it.
        case_meta_path = case_dir / "case_meta.json"
        if case_meta_path.exists():
            case_meta_for_anthropic = json.loads(
                case_meta_path.read_text(encoding="utf-8")
            )
        else:
            # Fall back to the meta we loaded at the start so the
            # Anthropic prompt still sees real case info.
            case_meta_for_anthropic = meta["case_meta"]

        clean_format_result = _run_clean_format(case_dir, case_meta_for_anthropic)

        print("\n=== SUMMARY ===")
        print(f"Case dir: {case_dir}")
        print(
            f"Deepgram raw transcript: {case_dir / 'Deepgram' / 'raw_deepgram.txt'}"
        )
        print(f"DOCX: {clean_format_result['docx_path']}")
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
