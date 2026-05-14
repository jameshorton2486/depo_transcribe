# Architectural Deferments

Intentionally postponed architectural issues, known semantic mismatches,
and compatibility compromises. **This file is not a bug tracker.** Random
bugs, UI issues, and formatting tweaks belong elsewhere.

## What goes here

- Intentionally deferred architectural issues
- Known semantic mismatches between code and reality
- Postponed refactors with cross-layer impact
- Compatibility compromises (we know it's wrong; rewriting it now is more dangerous than leaving it)
- Temporary pipeline-layer violations awaiting sequencing

## Operating principle

> A defect's correctness does not determine its urgency. A defect that
> survives a phase is still a defect; bundling it for convenience is how
> scope dies.

Every entry must explain *why* it is deferred and which phase will address
it. An entry without a deferral rationale and a target phase is a bug,
not a deferment, and does not belong here.

---

## `raw_utterances` Naming Mismatch

**File:** `pipeline/transcriber.py` — return dict at the end of `_transcribe_direct`.

**Issue.** The key `"raw_utterances"` in the per-chunk result dict
contains utterances that have already passed through
`_annotate_confidence()` and `smooth_speakers()`. They are therefore
**not** truly raw. The name implies a forensic untouched snapshot; the
contents are post-mutation.

**Why this is not fixed now.** Renaming or separating this contract
would ripple into:

- `pipeline/assembler.py` (consumes `raw_utterances` as input to cross-chunk merge)
- `core/corrections_runner.py` (offline correction CLI)
- The saved `<base>_<stamp>_raw.json` debug-snapshot schema written by `_write_debug_snapshots`
- Downstream tooling that reads those snapshots
- The transcript-integrity test fixtures
- Future review-layer assumptions

**The forensic guarantee already exists elsewhere.** The unmutated
Deepgram response body is preserved verbatim in:

- `result["raw"]` (in-memory, per chunk)
- `<case>/Deepgram/raw_dg_response_<stamp>.json` (on-disk, immutable, read-only) — the Phase A artifact

So the legal-record forensic problem is already solved. The remaining
issue is naming clarity, developer expectations, and future-contributor
safety — fundamentally a governance issue right now.

**Mitigation in place.** An inline `NOTE:` comment at the return site
in `pipeline/transcriber.py` documents the misnomer so any reader
encounters the warning before relying on the name.

**Target phase.** Phase C (Playground Mode) or Phase G (assembler
refactor), per
`docs/plans/RAW_IMMUTABILITY_AND_PLAYGROUND_MODE_PLAN.md`. The rename
naturally rides along with the assembler simplification that removes
`smooth_speakers` from the per-chunk path.

**Status.** Intentional compatibility compromise. Tracked since
2026-05-13.

**Do not fix inside a Phase A commit.**
