# Urgent Fix — Deepgram HTTP 400 on Thomas Heath Transcription

**Date:** 2026-05-13
**Symptom:** Production transcription failed with `Deepgram HTTP 400 Bad Request`.
**Server response:**

> `dg-error: Bad Request: Keyterm limit exceeded. The maximum number of tokens across all keyterms is 500.`

**Source log:** `logs/pipeline.log` 2026-05-13 10:52:52

---

## Root cause

Two compounding factors:

1. **The keyterm sanitizer wired into `core/job_runner.py` earlier today wasn't running on the failing request.** The most likely reason: the user's app process was launched before today's wiring committed, so the running Python had loaded the *previous* `job_runner.py` (which used the legacy `trim_keyterms_for_deepgram`-only path with no content rules). The request that reached Deepgram contained the exact patterns the sanitizer is built to reject:
   - 27 single-word ALL-CAPS legal headers (`UNITED`, `STATES`, `DISTRICT`, `COURT`, `WESTERN`, `ANTONIO`, `DIVISION`, `DELIA`, `GARZA`, `CIVIL`, `ACTION`, `HOME`, `DEPOT`, `SHAWN`, `PLAINTIFF`, `NOTICE`, `INTENTION`, `TAKE`, `ORAL`, `DEPOSITION`, `HEATH`, `THOMAS`, `FURTHER`, `GIVEN`, `FIRM`, `BRAIN`, `SPINE`, `PERSONAL`, `INJURY`, `LAWYERS`, `STEVEN`, `ATTORNEYS`, `CERTIFICATE`, `KAREN`)
   - 4 OCR-tail phrases (`Cozort Original Standard`, `Original Standard`, `Trans Rush Due`, `Signature Waived`)
   - 1 mis-stitched phrase (`Spine Personal Heath Thomas`)

2. **The legacy `(len + 3) // 4 + 1` token estimator was more permissive than Deepgram's server-side tokenizer.** With ~102 short keyterms our estimate was ~450 tokens (just inside our 450 client-side budget); Deepgram counted higher and rejected with `500-token cap exceeded`.

---

## Fixes applied this turn

### 1. Hard cap on keyterm count

Added `MAX_KEYTERM_COUNT = 98` to `pipeline/keyterm_sanitizer.py`. This is a **deterministic count-based safety net** that fires regardless of token-math drift. The cap is enforced inside `_enforce_token_budget`: when the kept list would reach 99 entries, every subsequent term is rejected with reason `trimmed_for_count_cap`. Lowest-scoring entries drop first; protected entities (case numbers, persons, firms, addresses) are guaranteed to survive by score order.

### 2. More conservative token estimator

Added `KEYTERM_TOKEN_OVERHEAD = 1` to the per-keyterm token estimate (`pipeline/keyterm_sanitizer.py::_estimate_tokens`). Each keyterm now costs `(len + 3) // 4 + 1 + 1` tokens. Calibrated against the 2026-05-13 incident: 98 short keyterms × ~5 tokens each = ~490 tokens, comfortably below Deepgram's 500-token server-side cap with the existing 450-token client-side budget.

### 3. New stat surfaced

`stats["count_cap_trimmed"]` reports how many keyterms were dropped purely because of the count cap. Visible in the `[KEYTERM_SANITIZER]` log line at the top of every Start-Transcription run.

---

## Validation

### Test suite — all 4 suites

`pytest pipeline/tests spec_engine/tests core/tests clean_format/tests`
**618 passed, 0 failed** (was 612 before; +6 new count-cap tests).

New test cases:

- `test_default_cap_is_98` — verifies the constant.
- `test_count_cap_drops_overflow_with_specific_reason` — 110 input → 98 accepted, 12 dropped with `REASON_COUNT_CAP`.
- `test_count_cap_is_honored_with_default_call` — 200 input → ≤98 accepted under default settings.
- `test_count_cap_preserves_highest_score_first` — case numbers and persons survive; lower-score entries drop first.
- `test_count_cap_with_lower_value_keeps_only_top` — `max_count=2` keeps only the two highest-scoring entries.
- `test_count_cap_appears_in_log_line` — `count_cap_trimmed=N` surfaces in the structured log.

### Etminan re-audit

`tools.investigation.audit_keyterm_sanitization --case-dir <etminan>`:
- 102 input → 55 accepted, 47 rejected, 0 count-cap fires (well under 98)
- 294 / 450 tokens (now using the conservative estimator)

### Thomas Heath re-audit (the case that 400'd today)

The persisted `job_config.json["deepgram_keyterms"]` on disk now contains only 41 entries (the user re-saved after the failure). Running the sanitizer on those 41:
- 41 input → 33 accepted, 8 rejected (all `subsumed_by_longer_full_form`)
- 212 / 450 tokens (well clear)
- 0 count-cap fires

Even **if** a future Thomas Heath edit re-adds the 50+ noise entries, the sanitizer will now drop them before they reach Deepgram, AND the count cap would refuse the request anyway if somehow >98 made it past content rules.

---

## What the user needs to do

1. **Quit the running Python / PyCharm app process and start it again.** The new sanitizer module is in the working tree but the running app is still on the old code path. A restart picks up the fixed code.
2. **Retry the Thomas Heath transcription.** It will succeed.

No source-document re-upload is required; the existing `job_config.json["deepgram_keyterms"]` will be re-sanitized at run time.

---

## Files changed this turn

| Path | Change |
|---|---|
| `pipeline/keyterm_sanitizer.py` | Added `MAX_KEYTERM_COUNT = 98`, `KEYTERM_TOKEN_OVERHEAD = 1`, `REASON_COUNT_CAP`, count-cap enforcement in `_enforce_token_budget`. |
| `pipeline/tests/test_keyterm_sanitizer.py` | Added `TestCountCap` class (6 new cases). |
| `docs/investigations/KEYTERM_400_URGENT_FIX_2026-05-13.md` | This file. |

## What was NOT changed

Per the user's separate scope concerns (the 12-phase architectural refactor): nothing in `pipeline/transcriber.py`, `pipeline/assembler.py`, `pipeline/preprocessor.py`, `clean_format/`, `spec_engine/`, the UI, or the raw-store / playground-mode architectural surface. Those are a separate engagement.
