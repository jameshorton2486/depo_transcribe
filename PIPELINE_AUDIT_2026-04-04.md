> **STATUS: HISTORICAL** — dated 2026-04-04, three weeks before this
> banner was added. The file's self-claim of being the "current review
> baseline" should be ignored. Specific factual claims (test counts,
> fix status, file states) may be outdated. Treat as historical context
> only. For current-state understanding, see `CLAUDE.md` and a live
> `pytest` run. Banner added 2026-04-27 ahead of master fix Phase F.

# Depo-Pro Pipeline Audit

Date: 2026-04-04

This document is a current-state audit of the intake, transcription, keyterm, and UFM pipeline. It is intended to replace older audit notes that are now partially stale.

## Purpose

Use this document as the authoritative review summary for:
- NOD / PDF intake
- reporter notes ingestion
- keyterm persistence and Deepgram transmission
- UFM field mapping
- title page / certificate page generation

This document reflects the live codebase after the recent fixes already pushed to `main`.

## Files Reviewed

- `ui/tab_transcribe.py`
- `core/intake_parser.py`
- `core/job_config_manager.py`
- `core/job_runner.py`
- `core/ufm_field_mapper.py`
- `core/field_mapping.py`
- `core/correction_runner.py`
- `pipeline/transcriber.py`
- `pipeline/assembler.py`
- `spec_engine/corrections.py`
- `spec_engine/processor.py`
- `spec_engine/document_builder.py`
- `spec_engine/user_rule_store.py`
- `spec_engine/pages/title_page.py`
- `spec_engine/pages/certificate.py`

## Current Verified Baseline

- `python -m pytest -q` -> `671 passed, 37 skipped`

## Already Fixed

The following issues were previously real and are now fixed in the current codebase:

### Intake / Keyterms / Persistence

- `deepgram_keyterms` now persist through `job_config.json`
- keyterms are passed end-to-end:
  - `ui/tab_transcribe.py`
  - `core/job_runner.py`
  - `pipeline/transcriber.py`
- Deepgram request transmission now includes keyterms
- reporter notes are persisted and merged into the intake/transcription flow
- `court_type` mapping now lands in the correct `JobConfig` field

### Core Runtime Guards

- malformed `speaker_map` keys no longer crash correction-runner config building
- `session_id` exception cleanup in `core/correction_runner.py` is safe
- judicial district ordinal suffixes are correct
- ordering-attorney fallback now maps to `defense_counsel`

### UFM / Page Generation

- removed literal `(WITNESS NAME)` from title page output
- fixed title-page phrasing: `at the instance of {name}`
- removed duplicate reporter-name repetition on title page
- certificate waiver language is now conditional
- `JobConfig()` no longer defaults reporter identity fields to one specific reporter

### Spec Engine / Processing

- `fix_spaced_dashes()` now preserves interrupted speech correctly
- `curtory` now maps to `cursory`
- `trailer trailer -> tractor trailer` now protects `semi-`, `full-`, and `double-` trailer compounds
- processor `assert` statements were replaced with explicit runtime checks
- duplicate processor snapshots were removed
- block cache was changed from unsafe pickle loading to JSON
- user rules are loaded once per correction run instead of once per block
- hardcoded reporter-identity universal corrections were removed

## Items That Are No Longer Accurate In Older Audits

Older audit documents may still claim the following bugs are active. They are not:

- keyterms never reach Deepgram
- reporter notes are always ignored
- `court_type` is mapped to the wrong field
- `speaker_map` malformed keys still crash
- `session_id` is still unsafe in correction-runner cleanup
- title page still renders `(WITNESS NAME)`
- title page still repeats reporter name
- certificate always states signature was waived
- `JobConfig` still hardcodes reporter defaults

Do not re-apply old mega-prompts that assume those bugs are still live.

## Current Open Items

These items still deserve review, but they are not all the same kind of work.

### Likely Bugs / Policy-Sensitive Changes

These affect transcript meaning or legal-output behavior and should be handled deliberately:

- `pipeline/assembler.py`
  - overlap dedup remains heuristic and may still need fixture-based refinement
- remaining case-specific universal corrections outside the reporter-specific paths
  - these should be reviewed against the policy of using case/config-driven data instead of hardcoded universal rules

### Dormant / Low-Priority Debt

- `spec_engine/display_formatter.py`
  - still exists and mutates text
  - current review suggests it is not on the active production pipeline path
  - treat as compatibility/debt, not active pipeline-critical behavior

### Architectural Debt

- `pipeline/processor.py`
  - still imports `spec_engine` directly
- `spec_engine/tests`
  - still contains architecture-coupled tests and legacy skipped tests

These are valid cleanup targets, but they are not the same as active production defects.

## Recommended Audit Strategy Going Forward

Do not use a single giant cross-layer prompt. Use staged, independently verifiable changes.

### Rules

- Read `CLAUDE.md` before changes
- keep changes to one layer at a time
- verify whether an issue is already fixed before patching
- after each step:
  - run `python -m py_compile` on changed files
  - run focused tests
  - run `python -m pytest -q`
  - commit only that step if green

## Recommended Mega Prompt

```md
Audit and remediate the Depo-Pro intake/transcription/UFM pipeline using the current live codebase, not older stale audit assumptions.

Rules:
- Read `CLAUDE.md` first.
- Respect the single-layer rule.
- Do not make speculative cross-layer refactors.
- Before each step, verify whether the issue is already fixed in the current code.
- After each step:
  - run `python -m py_compile` on changed files
  - run the most relevant focused tests
  - run `python -m pytest -q`
  - commit only that step if green

Scope to review:
1. `ui/tab_transcribe.py`
2. `core/intake_parser.py`
3. `core/job_config_manager.py`
4. `core/job_runner.py`
5. `core/ufm_field_mapper.py`
6. `core/field_mapping.py`
7. `pipeline/transcriber.py`
8. `pipeline/assembler.py`
9. `spec_engine/pages/title_page.py`
10. `spec_engine/pages/certificate.py`

For each file:
- confirm what is already fixed
- identify only currently-live defects
- separate:
  - confirmed bug
  - policy-sensitive change
  - architecture/debt item
- patch only confirmed bugs unless explicitly approved otherwise

Execution order:
Step 1: `core/intake_parser.py`
- verify API-key handling
- verify keyterm filtering cap uses shared config constant
- verify extracted proper nouns are not polluted by generic legal boilerplate beyond intended seeds
- add/adjust focused tests

Step 2: `pipeline/assembler.py`
- review overlap dedup logic against current chunk overlap behavior
- add fixture-based tests before changing behavior
- patch only if the failure is reproducible in tests

Step 3: `spec_engine/display_formatter.py`
- determine whether it is active production code or dormant compatibility code
- if dormant, document and defer
- if active, remove content-mutating behavior from formatter path safely

Step 4: broader correction-rule cleanup
- identify any remaining case-specific universal rules
- remove only those explicitly approved by policy
- add regressions proving config-driven alternatives still cover the needed behavior

Output after the audit:
- current-status report
- exact files changed
- exact tests run and results
- remaining deferred items
```

## Bottom Line

The old pipeline audit was useful as historical context, but it should not be applied as-is. Too many of its former critical items are already fixed.

This document should be used instead as the current review baseline.
