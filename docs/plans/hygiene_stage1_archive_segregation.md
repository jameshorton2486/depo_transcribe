# Hygiene Stage 1 — Archive Segregation

## Purpose

Reduce future AI-agent confusion by moving documents that are historical, superseded, or actively misleading into a clearly-marked `docs/_archive/` directory. No code is touched. No production behavior changes.

This is the first of 5 stages from the hygiene audit at `docs/reports/dead_module_hygiene_audit_2026-05-15.md`. Stages 2–5 are independent and can be executed in any order or not at all.

## Why Stage 1 first

- **Lowest risk.** Only `git mv` operations on documentation files.
- **Highest clarity gain.** Removes the two stale reports that actively contradict the current repo state (audit Sections 4.1 and 4.2) — the largest single source of AI-agent confusion identified.
- **Reversible.** Each move is a single git operation; full revert is one `git revert` away.
- **Independent.** Doesn't depend on any of the other stages.

## What this plan does NOT do

- Touch any `.py` file.
- Delete anything (only moves).
- Touch `CLAUDE.md`, `AGENTS.md`, or `README_AI.md`.
- Touch anything under `docs/audits/` (those are current authority, not stale).
- Touch anything under `docs/architecture/` (current authority).
- Touch `docs/reports/dead_module_hygiene_audit_2026-05-15.md` itself.
- Touch any file mentioned in `docs/audits/ACTIVE_PATH_AUDIT.md` as currently-wired.
- Make any decisions about Stages 2–5.

## Exact file list to move

Two logical groups, each becoming its own focused commit per acceptance criterion 7.

### Group A — Superseded verifications → `docs/_archive/verifications/`

Five files, all flagged in audit Section 4 with either factual conflict or "historical" status:

| # | Source | Target | Reason flagged |
|---|---|---|---|
| 1 | `docs/verifications/transcript_change_pipeline_wiring_report_2026-05-09.md` | `docs/_archive/verifications/transcript_change_pipeline_wiring_report_2026-05-09.md` | Audit §4.1: CONFLICTING. Wiring table claims `pipeline/exporter.py` is wired into `core/job_runner.py`. Confirmed-false by import-grep; `ACTIVE_PATH_AUDIT.md` is current authority. |
| 2 | `docs/verifications/transcript_change_pipeline_trace_2026-05-12.md` | `docs/_archive/verifications/transcript_change_pipeline_trace_2026-05-12.md` | Audit §4.2: CONFLICTING. End-to-end diagram lists `pipeline/exporter.py` in the production chain — same factual error as #1. |
| 3 | `docs/verifications/transcript_change_surface_report_2026-05-09.md` | `docs/_archive/verifications/transcript_change_surface_report_2026-05-09.md` | Audit §2 implicit (pre-Phase-2A surface inventory; superseded by `ACTIVE_PATH_AUDIT.md` and `CASE_MUTATION_REPORT.md`). Not directly contradicted but supersession is clear. |
| 4 | `docs/verifications/deterministic_formatting_corrections_audit_2026-04-28.md` | `docs/_archive/verifications/deterministic_formatting_corrections_audit_2026-04-28.md` | Audit §4.3: STALE/CONFLICTING. Lists three modules that no longer exist (`spec_engine/parser.py`, `spec_engine/objections.py`, `core/correction_runner.py` singular). |
| 5 | `docs/verifications/phase_h_double_spacing_2026-04-27.md` | `docs/_archive/verifications/phase_h_double_spacing_2026-04-27.md` | Audit §4.9: HISTORICAL. Contract still valid (UFM 2.13 double-spacing); the verification was a one-time check from 2026-04-27. Not misleading, but belongs with the other historical verifications for tidy segregation. |

Plus one new file:

- `docs/_archive/verifications/README.md` — one short paragraph stating: "These reports describe earlier states of the repo. For current architecture and wiring, see `docs/audits/ACTIVE_PATH_AUDIT.md`. Specific contradictions between these archived reports and the current code are identified in `docs/reports/dead_module_hygiene_audit_2026-05-15.md` Sections 4.1–4.3 and 4.9."

### Group B — Executed implementation plans → `docs/plans/_archive/`

Nine files, all dated 2026-05-12. Each was an implementation prompt whose corresponding work landed in `git log`. Per audit §4.8: HISTORICAL (correctly treated; segregation is optional polish, not correction).

| # | Source | Target | Landing commit(s) |
|---|---|---|---|
| 1 | `docs/plans/verbatim_punctuation_plan_2026-05-12.md` | `docs/plans/_archive/verbatim_punctuation_plan_2026-05-12.md` | Master plan; covers Step A–D landings below. |
| 2 | `docs/plans/step_a_corrections_cleanup_2026-05-12.md` | `docs/plans/_archive/step_a_corrections_cleanup_2026-05-12.md` | `40be155`, `e235d5e` |
| 3 | `docs/plans/step_b0_word_carry_2026-05-12.md` | `docs/plans/_archive/step_b0_word_carry_2026-05-12.md` | `3530abf` |
| 4 | `docs/plans/step_b1_word_carry_merge_split_2026-05-12.md` | `docs/plans/_archive/step_b1_word_carry_merge_split_2026-05-12.md` | `dfda8c1` |
| 5 | `docs/plans/step_c_low_confidence_markers_2026-05-12.md` | `docs/plans/_archive/step_c_low_confidence_markers_2026-05-12.md` | `d7a45f4` |
| 6 | `docs/plans/step_d_yellow_highlight_rendering_2026-05-12.md` | `docs/plans/_archive/step_d_yellow_highlight_rendering_2026-05-12.md` | `558e740` |
| 7 | `docs/plans/step_e_production_wiring_2026-05-12.md` | `docs/plans/_archive/step_e_production_wiring_2026-05-12.md` | `7b66c68`, drift policy commit `601b943` |
| 8 | `docs/plans/audit_hygiene_pass_2026-05-12.md` | `docs/plans/_archive/audit_hygiene_pass_2026-05-12.md` | `164fd18` |
| 9 | `docs/plans/post_release_cleanup_2026-05-12.md` | `docs/plans/_archive/post_release_cleanup_2026-05-12.md` | `f820eee` (Phase 1 was no-op per the plan), `a16abb2` (Phase 2), `24ebc70` (Phase 3) |

Plus one new file:

- `docs/plans/_archive/README.md` — short paragraph stating: "Each file here is an implementation prompt that has been executed. The corresponding commits are referenced in the file's metadata or are findable via `git log --grep=<step name>`. Active plans (work in progress) live at `docs/plans/` top level. Currently no active plans."

Plus one new file at the *top* level:

- `docs/plans/README.md` — short paragraph stating: "Plans are implementation prompts. Active/in-progress plans live at this top level. Executed plans are archived under `_archive/` with their landing commits documented. AI agents looking for the most recent dated plan covering an area (per `.cursorrules` line 4) should check both this directory and `_archive/`."

### NOT in this plan (deferred)

- `docs/_archive/FORMATTING_AUDIT_AND_RULES.md` and `docs/_archive/FORMATTING_AUDIT_GUIDE.md` — already correctly archived per audit §4.4–4.5. No move needed.
- `docs/MD_INSTRUCTION_GOVERNANCE_2026-04-28.md` — audit §4.6 classifies as MOSTLY ACTIVE with a minor inventory gap. Stays at `docs/` top level until Stage 4 updates its inventory.
- `docs/transcription_standards/depo_pro_style.md` — current authority for house style. Not moving.
- `ufm_engine/post_processor/README.md`, `ufm_engine/templates/MANIFEST_TODO.md` — ACTIVE per audit §4.11 and §4.10. Not moving.
- All of `docs/audits/`, `docs/architecture/`, `docs/reports/`, `tools/verification/` — current authority. Not moving.

### Deferred / needs human decision

None for Stage 1. Every file in the move list above has unambiguous audit support. If a future session's executor disagrees with any specific row, that row should be skipped and the disagreement noted in the commit message.

## Acceptance criteria for executing this plan

When a future session executes Stage 1:

1. Every file in Group A and Group B is moved via `git mv` (not copy-delete) so git history is preserved through the rename.
2. Each target subdirectory under `docs/_archive/` gets a `README.md` with the content specified above.
3. The new `docs/plans/README.md` exists with the content specified above.
4. `git grep` for each moved filename in remaining tracked files (excluding the audit report and this plan) returns zero hits, OR any remaining references are updated to point at the new archive path. The audit report and this plan correctly retain the old paths because they're describing the move.
5. No `.py` file in the working tree is modified.
6. The full pytest suite passes (it should, since no code changed; documenting this is the test that nothing important got moved by accident).
7. **Two focused commits**, not one:
   - Commit A: Group A moves + `docs/_archive/verifications/README.md`.
   - Commit B: Group B moves + `docs/plans/_archive/README.md` + `docs/plans/README.md`.
8. Push to `origin/main` after both commits land.

## Estimated effort

1–2 hours of focused work in a separate session. Should not be combined with code changes. No API spend.

## Out of scope for this plan (Stages 2–5 from the hygiene audit)

Listed for reference, not for action in this plan:

- **Stage 2** — Dead-module disposition (`pipeline/exporter.py`, `pipeline/pyannote_diarizer.py`, `spec_engine/ufm_rules_backup.py`). Requires per-CLAUDE.md §17 deliberation. Likely one focused commit per module.
- **Stage 3** — Stale-script cleanup (`zip_formatting.ps1`, `maintenance.txt`, `scripts/diagnostics/probe_qa_failures.py` wrapper).
- **Stage 4** — Documentation consolidation. Update `MD_INSTRUCTION_GOVERNANCE_2026-04-28.md` inventory; resolve `AGENTS.md` ↔ `README_AI.md` duplication; add `docs/README.md` taxonomy.
- **Stage 5** — Optional CI drift detector. Verify every file mentioned in `docs/audits/*.md` and `docs/verifications/*.md` still exists.

Each will get its own plan doc if and when it's queued for execution.
