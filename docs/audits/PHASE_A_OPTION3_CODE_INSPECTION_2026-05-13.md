# Phase A Audit — Option 3 Code Inspection

**Date:** 2026-05-13  
**Commit audited:** `7daca1a8f8266d0fa2220ced8a5a74cb390d0eca`  
**Audit mode:** source inspection only; no synthetic paid run  
**Reason for scope:** no schema-v2 case folder is available in this workspace, so runtime-artifact checks are deferred to the next real production run.

---

## Decision

Option 3 is the correct audit mode for the current state of the repo.

Phase A makes two distinct claims:

1. The code is correctly implemented.
2. A real production run produces the expected schema-v2 artifacts.

Claim 1 is verifiable from source alone. Claim 2 requires a real schema-v2 case folder. This audit therefore closes the source-verifiable portion now and defers the artifact-verifiable portion until the next real run creates the required files naturally.

---

## Results

| Item | Status | Basis |
|---|---|---|
| 2. Save-before-mutation ordering | PASS | Verified in `core/job_runner.py` |
| 8. Length-mismatch guard in raw store | PASS | Verified in `pipeline/raw_store.py` |
| 12. Rewrite markers present across all files | PASS | Verified in `core/job_runner.py`, `pipeline/raw_store.py`, `pipeline/transcriber.py` |
| 1, 3-7, 9-11 | INCONCLUSIVE | Require a real schema-v2 case folder; defer to next production run |

---

## PASS Details

### Item 2 — Save-before-mutation ordering

PASS.

In [core/job_runner.py](/C:/Users/james/pycharmprojects/depo_transcribe/core/job_runner.py:393), `save_raw_response(...)` is called before the cross-chunk assembler runs:

- `save_raw_response(...)` at lines 393-408
- `[RAW RESPONSE SAVED]` log marker at line 410
- `[TRANSCRIPT MUTATION BEGINS]` log marker at line 423
- `reassemble_chunks(...)` at line 425

This preserves the central Phase A forensic guarantee: the immutable raw file is written before cross-chunk mutation begins.

### Item 8 — Length-mismatch guard

PASS.

In [pipeline/raw_store.py](/C:/Users/james/pycharmprojects/depo_transcribe/pipeline/raw_store.py:194), the raw-store writer refuses to silently truncate mismatched inputs:

- length check at line 194
- `ValueError` raised at line 195

This preserves the intended fix for the incomplete-record failure mode.

### Item 12 — Rewrite markers present

PASS.

The expected Phase A markers are present across the three relevant files:

- [pipeline/raw_store.py](/C:/Users/james/pycharmprojects/depo_transcribe/pipeline/raw_store.py:74)
  - `SCHEMA_VERSION = 2`
  - persisted `keyterms_sent`
- [core/job_runner.py](/C:/Users/james/pycharmprojects/depo_transcribe/core/job_runner.py:87)
  - `_extract_request_provenance`
  - `[RAW RESPONSE SAVED]`
  - `raw_store_failure`
- [pipeline/transcriber.py](/C:/Users/james/pycharmprojects/depo_transcribe/pipeline/transcriber.py:687)
  - `deepgram_request_params_snapshot`
  - `keyterms_sent`
  - provenance included in both skip-path and normal return payloads

This is sufficient to conclude the Phase A rewrite is still present in the current tree and has not partially drifted or been reverted.

---

## Deferred Items

The following items are intentionally marked `INCONCLUSIVE`, not `FAIL`, because the required runtime artifacts do not exist in this workspace:

- Item 1
- Items 3-7
- Items 9-11

Deferred reason:

`No schema-v2 case folder available yet; complete these checks against the next real production run.`

These items should be re-opened after the next real transcription run completes and produces:

- `Deepgram/raw_dg_response_<timestamp>.json`
- `Deepgram/raw_deepgram.json`
- associated schema-v2 metadata in the case folder

---

## Defensible Statement

As of commit `7daca1a8f8266d0fa2220ced8a5a74cb390d0eca`, Phase A is correctly implemented in source.

Runtime-artifact verification is deferred to the next real schema-v2 production run rather than a synthetic paid run.

---

## Follow-up

When a real schema-v2 case folder exists, re-run the remaining audit items against that folder and amend this audit rather than replacing it.

Existing artifact-level evidence from a prior real run is documented in [docs/validation/IMMUTABILITY_RESULTS.md](/C:/Users/james/pycharmprojects/depo_transcribe/docs/validation/IMMUTABILITY_RESULTS.md:1), but that evidence is separate from this Option 3 source-only audit.
