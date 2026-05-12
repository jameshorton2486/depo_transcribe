"""Phase 2A failure diagnostic — instrumented harness.

Same shape as _phase2a_verify.py but monkey-patches
clean_format.low_confidence_markers.validate_marker_round_trip to
write per-chunk diagnostic files to disk BEFORE running the real
validation. The MarkerDriftError still fires as designed; the
diagnostic data is captured for every chunk leading up to (and
including) the failing chunk.

Files written under {case}/diag_phase2a_<timestamp>/:
  chunk_<N>_input.txt        — marker-wrapped text sent to the model
  chunk_<N>_output.txt       — cleaned text returned by the model
  chunk_<N>_marker_diff.txt  — counts + set-diff of marker bodies
  case_meta.json             — case_meta as the prompt saw it
                               (one copy at the diag root; same for
                                every chunk in this run)

Deleted after the run.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: F401

from clean_format import format_transcript, write_deposition_docx
from clean_format.formatter import load_deepgram_words_from_json
from clean_format import low_confidence_markers as lcm
from config import LOW_CONFIDENCE_THRESHOLD

CASE = Path(
    r"C:\Users\james\Depositions\2026\May\2026CV00803\cavazos_gilberto"
)
RAW_TXT = CASE / "Deepgram" / "raw_deepgram.txt"
RAW_JSON = CASE / "Deepgram" / "raw_deepgram.json"
CASE_META_JSON = CASE / "case_meta.json"
JOB_CONFIG_JSON = CASE / "source_docs" / "job_config.json"
OUTPUT_DOCX = CASE / "Cavazos_Deposition_phase2a_diag.docx"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
DIAG_DIR = CASE / f"diag_phase2a_{TIMESTAMP}"


def main() -> int:
    for p in (RAW_TXT, RAW_JSON, CASE_META_JSON, JOB_CONFIG_JSON):
        if not p.exists():
            print(f"FATAL: missing {p}")
            return 2

    DIAG_DIR.mkdir(parents=True, exist_ok=True)

    case_meta = json.loads(CASE_META_JSON.read_text(encoding="utf-8"))
    raw_text = RAW_TXT.read_text(encoding="utf-8")
    deepgram_words = load_deepgram_words_from_json(RAW_JSON)
    if deepgram_words is None:
        print("FATAL: load_deepgram_words_from_json returned None")
        return 2

    job_config = json.loads(JOB_CONFIG_JSON.read_text(encoding="utf-8"))
    confirmed_spellings = job_config.get("confirmed_spellings") or {}
    deepgram_keyterms = job_config.get("deepgram_keyterms") or []
    if confirmed_spellings:
        case_meta["confirmed_spellings"] = dict(confirmed_spellings)
    if deepgram_keyterms:
        case_meta["deepgram_keyterms"] = list(deepgram_keyterms)

    # Dump case_meta once — same for every chunk in this run.
    (DIAG_DIR / "case_meta.json").write_text(
        json.dumps(case_meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Diagnostic dir: {DIAG_DIR}")
    print(f"confirmed_spellings: {len(confirmed_spellings)} entries")
    print(f"deepgram_keyterms:   {len(deepgram_keyterms)} entries")

    # --- monkey-patch validate_marker_round_trip ---
    real_validate = lcm.validate_marker_round_trip
    chunk_counter = {"n": 0}

    def instrumented_validate(input_text, output_text, **kwargs):
        chunk_counter["n"] += 1
        n = chunk_counter["n"]
        in_path = DIAG_DIR / f"chunk_{n}_input.txt"
        out_path = DIAG_DIR / f"chunk_{n}_output.txt"
        diff_path = DIAG_DIR / f"chunk_{n}_marker_diff.txt"
        in_path.write_text(input_text, encoding="utf-8")
        out_path.write_text(output_text, encoding="utf-8")

        # Marker-body set diff
        input_markers = lcm.LOW_CONF_MARKER_RE.findall(input_text)
        output_markers = lcm.LOW_CONF_MARKER_RE.findall(output_text)
        in_set = set(input_markers)
        out_set = set(output_markers)
        missing = sorted(in_set - out_set)
        new_in_output = sorted(out_set - in_set)
        ic = len(input_markers)
        oc = len(output_markers)
        dropped = max(0, ic - oc)
        pct = 100 * dropped / max(ic, 1)

        diff_lines = [
            f"chunk_index: {n}",
            f"input_count: {ic}",
            f"output_count: {oc}",
            f"dropped: {dropped}",
            f"drop_pct: {pct:.1f}%",
            f"input_chars: {len(input_text):,}",
            f"output_chars: {len(output_text):,}",
            f"unique_input_marker_bodies: {len(in_set)}",
            f"unique_output_marker_bodies: {len(out_set)}",
            f"missing_from_output (bodies that vanished): {len(missing)}",
            f"new_in_output (bodies that appeared in output but not in input): {len(new_in_output)}",
            "",
            "MISSING bodies (first 50):",
            *[f"  {b!r}" for b in missing[:50]],
            "",
            "NEW bodies in output (first 50):",
            *[f"  {b!r}" for b in new_in_output[:50]],
        ]
        diff_path.write_text("\n".join(diff_lines), encoding="utf-8")
        print(
            f"  chunk {n}: in={ic} out={oc} dropped={dropped} ({pct:.1f}%) "
            f"missing={len(missing)} new={len(new_in_output)}"
        )

        # Now call the real validator. If it raises MarkerDriftError,
        # the diag files for this chunk are already on disk.
        return real_validate(input_text, output_text, **kwargs)

    lcm.validate_marker_round_trip = instrumented_validate
    # Also re-patch the binding inside clean_format.formatter, which
    # imported the symbol at module load.
    import clean_format.formatter as fmt_mod
    fmt_mod.validate_marker_round_trip = instrumented_validate

    print("=" * 70)
    print("Phase 2A diagnostic — instrumented Cavazos run")
    print("=" * 70)

    t0 = time.time()
    drift_raised = False
    try:
        formatted_text = format_transcript(
            raw_text, case_meta, deepgram_words=deepgram_words
        )
    except lcm.MarkerDriftError as exc:
        elapsed = time.time() - t0
        drift_raised = True
        print(f"\n!! MarkerDriftError raised as expected after {elapsed:.1f}s")
        print(f"   stats: {exc.stats}")
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\n!! UNEXPECTED exception type after {elapsed:.1f}s")
        print(f"   {type(exc).__name__}: {exc}")
        return 4
    else:
        elapsed = time.time() - t0
        print(f"\nFormat completed in {elapsed:.1f}s without MarkerDriftError.")
        print(f"  formatted_text len: {len(formatted_text):,} chars")
        saved = write_deposition_docx(formatted_text, case_meta, OUTPUT_DOCX)
        print(f"  DOCX written: {saved}")

    print(f"\nDiagnostic chunks captured: {chunk_counter['n']}")
    print(f"Files in {DIAG_DIR}:")
    for f in sorted(DIAG_DIR.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
    return 0 if drift_raised else 0


if __name__ == "__main__":
    raise SystemExit(main())
