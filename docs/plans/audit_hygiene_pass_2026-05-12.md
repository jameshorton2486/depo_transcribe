# Audit Hygiene Pass — 2026-05-12

Single-commit cleanup of audit items called out after Step E landed.
Three concrete fixes; three items deliberately left untouched after
investigation.

## Fixed

### 1. `.cursorrules` referenced a missing `STABILIZATION_PLAN.md`

The cursor rules pointed at a phased-plan document that no longer
exists. Replaced with current guidance: read `CLAUDE.md`, check
`docs/plans/<topic>_<YYYY-MM-DD>.md` for the active dated plan,
single-layer changes, run tests, ask the user before committing.

### 2. `core/field_mapping.py` was an orphan

Self-confirmed tombstone — the file's own docstring said it served
"legacy correction-path builders" that have been replaced. A repo-wide
grep confirmed no live reference outside the file itself. Deleted.

### 3. QA diagnostic outputs polluted `git status`

The diagnostic scripts organized in commit 6db4a6f wrote 22+ probe /
corrections_run / splitter_run `.txt` files to the repo root. They
were never committed but kept appearing in `git status --porcelain`
on every session, drowning the actual working changes.

Added three glob entries to `.gitignore`:

  probe_*.txt
  corrections_run_*.txt
  splitter_run_*.txt

The existing files on disk are left in place — they may still be
useful as diagnostic snapshots. Future runs will be gitignored
automatically.

## Left untouched (investigated, deliberate)

### `ufm_template/`

20 PDF reporting/court forms (alphabetical witness index, certification
pages, exhibit index, style title pages, witness examination setup,
etc.). These are reference materials, likely third-party originals.
Triage decision belongs to the user — not a hygiene-pass call.

### `CLAUDE.md` drift

No specific drift items were called out for me to verify. CLAUDE.md
describes the current architecture (`pipeline/` for audio + Deepgram,
`clean_format/` for cleanup + DOCX) and matches the code as-shipped
through Step E. Skipped without specific drift to fix.

### `pipeline/exporter.py` "documented as wired but isn't"

Reads cleanly, has live tests
(`pipeline/tests/test_exporter.py::test_export_results_writes_raw_deepgram_baseline`),
and is referenced. No specific wiring gap I can verify without more
context.

### `smart_format=True` + `filler_words=True` runtime verification

Already covered by
`pipeline/tests/test_transcriber.py::test_transcribe_chunk_uses_requested_defaults`
which asserts `params["smart_format"] == ["true"]` and
`params["filler_words"] == ["true"]` are sent to Deepgram. Done at
the test level; no additional action.

## Test impact

557 passing before, 557 passing after. Deleting `core/field_mapping.py`
broke nothing, confirming the orphan status.
