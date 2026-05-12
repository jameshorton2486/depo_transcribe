# Verification Harnesses

One-off Python scripts that exercise `clean_format/` end-to-end against a real captured case folder, to verify prompt-level behavior that unit tests cannot reach (Anthropic API output is non-deterministic and prompt instructions are natural language, not code).

These scripts hit the live Anthropic API and **cost real money**. Each end-to-end run on the Cavazos test case is ~$2 in API spend. Use them only when you've changed `clean_format/prompt.py` or `clean_format/formatter.py` in a way that could affect marker preservation, correction application, or chunk-level behavior.

## When to run

After any change to:
- `clean_format/prompt.py` (the cleanup system prompt)
- `clean_format/formatter.py` (`_case_meta_for_prompt`, `build_user_message`, the per-chunk loop, `validate_marker_round_trip` integration)
- `clean_format/low_confidence_markers.py` (marker injection, validation, threshold)

Unit tests verify the wiring; these scripts verify the *model's interpretation* of the wired data.

## Scripts

### `cleanup_prompt_diagnostic.py`

Single-run, fully instrumented. Loads the Cavazos case folder, mirrors the live `_build_clean_format_case_meta` wiring (attaches `confirmed_spellings` + `deepgram_keyterms` from `source_docs/job_config.json`), monkey-patches `validate_marker_round_trip` to dump per-chunk diagnostic files to `<case>/diag_phase2a_<timestamp>/`:

- `chunk_<N>_input.txt` — marker-wrapped text sent to the model.
- `chunk_<N>_output.txt` — cleaned text returned by the model.
- `chunk_<N>_marker_diff.txt` — marker counts, missing-body list, set diff.
- `case_meta.json` — case_meta as the prompt saw it.

Use this when the question is *"what did the model actually do to the markers?"* — i.e., distinguishing between marker strips, marker rewrites, marker substitutions, and content drops. Run once, then read the captured files side-by-side.

### `marker_drift_verification.py`

Three-run consolidated verification. Same wiring as the diagnostic, but the patched `validate_marker_round_trip` **records drift without raising**, so all three runs complete to completion regardless of pass/fail. Captures per-run, per-chunk:

- `input_count`, `output_count`, `dropped`, `drop_pct`
- `would_raise` — was drift above the operational threshold?
- `high_signal_strips` — missing marker bodies that match a `confirmed_spellings` key or capitalized keyterm token
- Missing body sample, new-in-output body sample

Writes a consolidated JSON report to `<case>/PHASE_2A1_VERIFICATION_REPORT.json` and prints a summary table plus verdict (STABLE / INVESTIGATE / INSUFFICIENT).

Use this when the question is *"is the model's behavior stable across runs?"* — i.e., the prompt is plausibly correct and you want evidence it works repeatably before shipping.

## Cost discipline

- Single-run diagnostic: ~$2, ~3 min wall time.
- Three-run verification: ~$6, ~10 min wall time.
- The `Cavazos` case is small (3,858 Deepgram words, single chunk). Larger cases will cost more per run.
- The harnesses use captured Deepgram JSON, so they **do not** re-hit Deepgram. Only Anthropic is called.

## Case-folder dependency

Both scripts are hardcoded to the Cavazos case at `C:\Users\james\Depositions\2026\May\2026CV00803\cavazos_gilberto`. To verify a different case, edit the `CASE` constant at the top of each script. The folder must contain:

- `case_meta.json` at the root.
- `source_docs/job_config.json` with `confirmed_spellings` and `deepgram_keyterms` top-level keys.
- `Deepgram/raw_deepgram.txt` and `Deepgram/raw_deepgram.json`.

These are produced by a normal Start-Transcription run. For a fresh test, transcribe a case first, then point the harness at the resulting folder.
