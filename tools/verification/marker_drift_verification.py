"""Phase 2A.1 verification — three consecutive Cavazos runs with soft drift handling.

Same Phase 2A wiring as _phase2a_diagnostic.py, but the patched
validate_marker_round_trip RECORDS drift instead of RAISING — so a
run that would have triggered MarkerDriftError continues to completion
and we capture how bad it got. This is the right shape for stability
verification: we want all three runs to complete and report numbers
regardless of pass/fail.

For each run, captures per-chunk:
  - input_count, output_count, dropped, drop_pct
  - would_have_raised (was drift > 5% with input >= 5?)
  - missing marker bodies (set diff)
  - whether any missing body matches a confirmed_spellings key
    (high-signal token strip)

Writes a consolidated JSON report at the end to
PHASE_2A1_VERIFICATION_REPORT.json under the case folder, plus prints
a summary table.

Throwaway. Deleted after the protocol completes.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: F401

from clean_format import format_transcript
from clean_format.formatter import load_deepgram_words_from_json
from clean_format import low_confidence_markers as lcm
import clean_format.formatter as fmt_mod
from config import LOW_CONFIDENCE_THRESHOLD

CASE = Path(
    r"C:\Users\james\Depositions\2026\May\2026CV00803\cavazos_gilberto"
)
RAW_TXT = CASE / "Deepgram" / "raw_deepgram.txt"
RAW_JSON = CASE / "Deepgram" / "raw_deepgram.json"
CASE_META_JSON = CASE / "case_meta.json"
JOB_CONFIG_JSON = CASE / "source_docs" / "job_config.json"
REPORT_JSON = CASE / "PHASE_2A1_VERIFICATION_REPORT.json"

N_RUNS = 3
THRESHOLD_PCT = 5.0
FLOOR = 5


def main() -> int:
    for p in (RAW_TXT, RAW_JSON, CASE_META_JSON, JOB_CONFIG_JSON):
        if not p.exists():
            print(f"FATAL: missing {p}")
            return 2

    case_meta = json.loads(CASE_META_JSON.read_text(encoding="utf-8"))
    raw_text = RAW_TXT.read_text(encoding="utf-8")
    deepgram_words = load_deepgram_words_from_json(RAW_JSON)
    if deepgram_words is None:
        print("FATAL: deepgram_words load returned None")
        return 2

    job_config = json.loads(JOB_CONFIG_JSON.read_text(encoding="utf-8"))
    confirmed_spellings = job_config.get("confirmed_spellings") or {}
    deepgram_keyterms = job_config.get("deepgram_keyterms") or []
    if confirmed_spellings:
        case_meta["confirmed_spellings"] = dict(confirmed_spellings)
    if deepgram_keyterms:
        case_meta["deepgram_keyterms"] = list(deepgram_keyterms)

    cs_keys_lower = {k.lower().strip() for k in confirmed_spellings.keys()}
    cs_vals_lower = {v.lower().strip() for v in confirmed_spellings.values()}
    # High-signal tokens: anything that's a key or a value in confirmed_spellings,
    # plus single-word proper nouns from deepgram_keyterms.
    high_signal = set(cs_keys_lower) | set(cs_vals_lower)
    for kt in deepgram_keyterms:
        for tok in str(kt).split():
            if tok and tok[0].isupper():
                high_signal.add(tok.lower().strip(",.;:"))

    print("=" * 72)
    print(f"Phase 2A.1 verification — {N_RUNS} runs against Cavazos")
    print(f"Threshold: >{THRESHOLD_PCT}% drop with input >= {FLOOR}")
    print(f"confirmed_spellings: {len(confirmed_spellings)} entries")
    print(f"deepgram_keyterms:   {len(deepgram_keyterms)} entries")
    print(f"High-signal token set size: {len(high_signal)}")
    print("=" * 72)

    runs = []

    for run_idx in range(1, N_RUNS + 1):
        print(f"\n--- run {run_idx}/{N_RUNS} starting at {datetime.now().strftime('%H:%M:%S')} ---")
        chunk_stats: list[dict] = []

        # Patch: record drift, NEVER raise.
        def soft_validate(input_text, output_text, **kwargs):
            ic = lcm.count_markers(input_text)
            oc = lcm.count_markers(output_text)
            dropped = max(0, ic - oc)
            pct = (dropped / ic) * 100 if ic else 0.0
            in_bodies = set(lcm.LOW_CONF_MARKER_RE.findall(input_text))
            out_bodies = set(lcm.LOW_CONF_MARKER_RE.findall(output_text))
            missing = sorted(in_bodies - out_bodies)
            new_in_out = sorted(out_bodies - in_bodies)

            # High-signal hits: did any stripped marker body match a
            # confirmed_spellings entry or capitalized keyterm token?
            high_sig_strips = [
                b for b in missing
                if b.lower().strip(",.;:") in high_signal
            ]

            chunk_stats.append({
                "input_count": ic,
                "output_count": oc,
                "dropped": dropped,
                "drop_pct": round(pct, 2),
                "would_raise": ic >= FLOOR and pct > THRESHOLD_PCT,
                "missing_count": len(missing),
                "new_in_output_count": len(new_in_out),
                "missing_bodies_sample": missing[:20],
                "new_bodies_sample": new_in_out[:20],
                "high_signal_strips": high_sig_strips,
            })
            # Return a real stats dict like the real function would,
            # never raise.
            return {"input_count": ic, "output_count": oc, "dropped": dropped}

        lcm.validate_marker_round_trip = soft_validate
        fmt_mod.validate_marker_round_trip = soft_validate

        t0 = time.time()
        try:
            formatted_text = format_transcript(
                raw_text, case_meta, deepgram_words=deepgram_words
            )
            elapsed = time.time() - t0
            ok = True
            err = None
            out_len = len(formatted_text)
        except Exception as exc:
            elapsed = time.time() - t0
            ok = False
            err = f"{type(exc).__name__}: {exc}"
            out_len = 0
            print(f"  !! UNEXPECTED EXCEPTION: {err}")

        worst_pct = max((c["drop_pct"] for c in chunk_stats), default=0.0)
        worst_chunk = max(range(len(chunk_stats)), key=lambda i: chunk_stats[i]["drop_pct"], default=-1)
        would_raise_any = any(c["would_raise"] for c in chunk_stats)
        any_high_sig = any(c["high_signal_strips"] for c in chunk_stats)
        total_in = sum(c["input_count"] for c in chunk_stats)
        total_out = sum(c["output_count"] for c in chunk_stats)
        total_dropped = sum(c["dropped"] for c in chunk_stats)

        run_result = {
            "run": run_idx,
            "elapsed_s": round(elapsed, 1),
            "ok": ok,
            "error": err,
            "formatted_chars": out_len,
            "chunks": len(chunk_stats),
            "total_input_markers": total_in,
            "total_output_markers": total_out,
            "total_dropped": total_dropped,
            "worst_chunk_idx": worst_chunk,
            "worst_chunk_drop_pct": worst_pct,
            "any_chunk_would_raise": would_raise_any,
            "any_high_signal_strip": any_high_sig,
            "chunk_details": chunk_stats,
        }
        runs.append(run_result)
        print(
            f"  chunks={len(chunk_stats)}  total_in={total_in}  total_out={total_out}  "
            f"dropped={total_dropped}  worst_pct={worst_pct:.1f}%  "
            f"would_raise={'YES' if would_raise_any else 'no'}  "
            f"high_sig_strip={'YES' if any_high_sig else 'no'}  "
            f"elapsed={elapsed:.1f}s"
        )

    # --- consolidated report ---
    summary = {
        "case": str(CASE),
        "timestamp": datetime.now().isoformat(),
        "threshold_pct": THRESHOLD_PCT,
        "floor": FLOOR,
        "n_runs": N_RUNS,
        "phase_2a_commit": "91e8282",
        "phase_2a1_commit": "887ec98",
        "high_signal_token_set_size": len(high_signal),
        "runs": runs,
    }

    REPORT_JSON.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nReport written: {REPORT_JSON}")

    print("\n" + "=" * 72)
    print(f"{'CONSOLIDATED SUMMARY':^72}")
    print("=" * 72)
    print(f"{'run':>4} {'in':>5} {'out':>5} {'drop':>5} {'pct':>6}  {'>5%?':>5}  {'hi-sig?':>7}  {'time':>6}")
    for r in runs:
        print(
            f"{r['run']:>4} {r['total_input_markers']:>5} {r['total_output_markers']:>5} "
            f"{r['total_dropped']:>5} {r['worst_chunk_drop_pct']:>5.1f}%  "
            f"{'YES' if r['any_chunk_would_raise'] else 'no':>5}  "
            f"{'YES' if r['any_high_signal_strip'] else 'no':>7}  {r['elapsed_s']:>5.1f}s"
        )

    all_pass = all(not r["any_chunk_would_raise"] for r in runs)
    no_high_sig = all(not r["any_high_signal_strip"] for r in runs)
    print("=" * 72)
    print(f"All {N_RUNS} runs under {THRESHOLD_PCT}% threshold: {'YES' if all_pass else 'NO'}")
    print(f"No high-signal token strips in any run: {'YES' if no_high_sig else 'NO'}")
    if all_pass and no_high_sig:
        print("VERDICT: Phase 2A.1 prompt fix appears STABLE. Safe to keep.")
    elif all_pass:
        print("VERDICT: Drift threshold OK, but high-signal token(s) stripped. Investigate.")
    else:
        print("VERDICT: Drift exceeded threshold on at least one run. Prompt fix is insufficient; iterate.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
