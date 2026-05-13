# Dead-Module & Repository Hygiene Audit — 2026-05-15

**Status:** Read-only observational pass. No edits, no commits, no moves performed by this audit.

**Scope of this audit:** repository hygiene at the markdown / scripts / config / root layer, plus secondary modules not deeply traced in prior work. The active production import graph is **not re-derived here** — it is owned by `docs/audits/ACTIVE_PATH_AUDIT.md` (dated 2026-05-12), which this audit cites and extends.

---

## SECTION 0 — Audit Scope

**Inspected for this audit:**
- All `docs/**/*.md` files (24 markdown files across 6 subdirectories).
- Root-level config: `CLAUDE.md`, `AGENTS.md`, `README.md`, `README_AI.md`, `.cursorrules`, `.github/copilot-instructions.md`.
- Root-level transient artifacts (probe output, audio fixtures, dead-end docs).
- `scripts/` (probe + repro tooling).
- `tools/verification/` (Phase 2A diagnostic harnesses, just landed).
- Secondary modules with known dead-code suspicion: `pipeline/exporter.py`, `pipeline/pyannote_diarizer.py`, `spec_engine/ufm_rules_backup.py`.
- `_archive/` directory contents.

**Defers to existing audits:**
- The active-path import-graph trace (Q1–Q7, module-by-module table) is owned by `docs/audits/ACTIVE_PATH_AUDIT.md`. This audit cites that work rather than re-deriving it.
- Per-token correction-application analysis is owned by `docs/audits/PHASE_2A_CORRECTION_APPLICATION.md`.
- Pipeline-stage verification per case is owned by `docs/audits/CASE_PIPELINE_VERIFICATION_REPORT.md`.

**Not in scope:**
- `.venv/` (third-party packages).
- Test files (each test is owned by its corresponding production module; tests are not separately catalogued here).
- Case folders under `C:\Users\james\Depositions\` (user data, not repository).

---

## SECTION 1 — Executive Summary

**Repository health: stable. Hygiene risk: medium.** The active production path is well-understood, tested, and recently audited. Production behavior is not at risk from any of the issues this audit identifies — all findings are observation-layer concerns about *clarity for future readers* and *AI-agent confusion potential*, not about correctness or shipping behavior.

**The four highest-leverage hygiene items, in priority order:**
1. **One older verification report directly contradicts the current state.** `docs/verifications/transcript_change_pipeline_wiring_report_2026-05-09.md` says `pipeline/exporter.py` is wired into `core/job_runner.py`. It isn't (confirmed by import-grep and by `ACTIVE_PATH_AUDIT.md`). Any AI agent reading the 5-09 report would believe a dead module is active.
2. **One older audit references modules that no longer exist.** `docs/verifications/deterministic_formatting_corrections_audit_2026-04-28.md` lists `spec_engine/parser.py`, `spec_engine/objections.py`, and `core/correction_runner.py` (singular). None of those files exist in the current repo. The audit's contents read as if those modules are part of the deterministic correction pipeline.
3. **Three confirmed-dead modules sit in the active package tree.** `pipeline/exporter.py`, `pipeline/pyannote_diarizer.py`, `spec_engine/ufm_rules_backup.py` — all unimported by production code. Two are explicitly self-labeled dead in their own docstrings. They were flagged in `ACTIVE_PATH_AUDIT.md` but no action has been taken yet (correctly — the audit is observation-only).
4. **One repo-root PowerShell script references files that no longer exist.** `zip_formatting.ps1` packages `spec_engine/document_builder.py` and `core/docx_formatter.py`, neither of which is in the repo today.

**No production behavior at risk** from any of these. The active path executes correctly; the safety net catches catastrophic regressions; the verification harnesses are durable in `tools/verification/`.

---

## SECTION 2 — Verified Active Production Paths

This section cites and lightly extends `docs/audits/ACTIVE_PATH_AUDIT.md` (2026-05-12), which has the authoritative module-by-module table. The key labels in that audit:

| Status | Meaning | Examples |
|---|---|---|
| **WIRED** | called in the live Start-Transcription path | `pipeline/{preprocessor,chunker,transcriber,assembler,audio_quality,vad_trimmer}.py`, `clean_format/{formatter,prompt,docx_writer,low_confidence_markers}.py`, `core/{job_runner,job_config_manager,file_manager,intake_parser,case_vocab,keyterm_extractor,pdf_extractor,source_docs_extractor,ufm_field_mapper}.py`, all of `ui/` |
| **OFFLINE** | only reachable from `core/*_runner.py` CLI/button paths, never from Start Transcription | all of `spec_engine/`, `core/corrections_runner.py`, `core/utterance_splitter_runner.py` |
| **TEMPLATES TAB** | active for the Templates tab only, not for Transcribe | all of `ufm_engine/` |
| **DEAD** | no production importers | `pipeline/exporter.py`, `pipeline/pyannote_diarizer.py`, `spec_engine/ufm_rules_backup.py` |

**Verification harness path (new since the active-path audit):**
- `tools/verification/cleanup_prompt_diagnostic.py` — single-run diagnostic for prompt changes. WIRED to nothing in production; invoked manually. Owned by Phase 2A operational tooling.
- `tools/verification/marker_drift_verification.py` — three-run drift verification. Same status.
- `tools/verification/README.md` — usage guide.

**Active prompt files:** exactly one — `clean_format/prompt.py`. No alternate prompts exist in the repo. This is a strength; older repos commonly accumulate alternate prompt versions.

**Active DOCX writer:** exactly one — `clean_format/docx_writer.py`. The `ufm_engine/post_processor/format_box.py` is a separate writer for the Templates tab (post-populate formatting), not a duplicate of clean_format's writer.

**Active review tooling:** `core/word_review.py` + the Word Review panel in `ui/tab_transcribe.py`. Loads per-word data from `raw_deepgram.json`.

---

## SECTION 3 — Dead / Unused Modules

All three flagged here were already identified in `ACTIVE_PATH_AUDIT.md`. This audit confirms via fresh import-grep that nothing has changed since.

### 3.1 `pipeline/exporter.py` — DEAD (HIGH confidence)

- **Evidence:** the only inbound import is from `pipeline/tests/test_exporter.py:6`. No production module references `pipeline.exporter` (`grep "from pipeline.exporter\|from pipeline import exporter"` returns one hit, in the test file).
- **What the file claims to do:** writes `{prefix}_transcript.txt`, `{prefix}_deepgram.json`, `{prefix}_flagged_words.txt`, and `raw_deepgram.txt`.
- **What actually writes those files in production:** `core/job_runner.py:338` writes `raw_deepgram.txt` inline. The other outputs in exporter.py have no corresponding production code path.
- **Tested-but-unused.** `pipeline/tests/test_exporter.py` covers an unimported module. The tests pass; they verify a module no one calls.
- **Conflict surface:** `docs/verifications/transcript_change_pipeline_wiring_report_2026-05-09.md` table claims this module IS wired — see Section 4.

### 3.2 `pipeline/pyannote_diarizer.py` — DEAD (HIGH confidence)

- **Evidence:** zero non-self imports. The module's own docstring (lines 1–25) explicitly labels itself "DEAD CODE — as of 2026-04-25, neither diarize() nor align_speakers() is called from anywhere in the active pipeline." Speaker labels come from Deepgram's `diarize=true` parameter, not from this module.
- **Author intent documented:** the docstring records that the file should NOT be deleted without explicit deliberation per CLAUDE.md §17 (testimony-altering surface) and that the original wiring intent was lost.
- This is the cleanest kind of dead code: self-documented, decision deferred, no risk of accidental wiring.

### 3.3 `spec_engine/ufm_rules_backup.py` — DEAD (HIGH confidence)

- **Evidence:** zero inbound imports of `ufm_rules_backup`. Three files import `ufm_rules` (the non-backup file): `clean_format/docx_writer.py`, `spec_engine/classifier.py`, `clean_format/tests/test_docx_writer.py`. None import the backup.
- **Differs from `ufm_rules.py`:** `diff -q` confirms the files are not identical. The backup is a stale copy of an earlier version of the rules module.
- This is a literal `_backup` suffix convention. Either the contents should be reviewed and merged into `ufm_rules.py` (if the backup has rules the current file is missing) or the backup should be deleted (if it's purely a stale snapshot).

### 3.4 No other dead modules detected

Every other module in `pipeline/`, `clean_format/`, `core/`, `ui/`, `spec_engine/`, `ufm_engine/` has at least one production-side importer per the `ACTIVE_PATH_AUDIT.md` table.

---

## SECTION 4 — Stale or Conflicting Markdown Files

This is the section with the most concrete hygiene impact. Several markdown files actively mislead readers about the current state.

### 4.1 `docs/verifications/transcript_change_pipeline_wiring_report_2026-05-09.md` — **CONFLICTING**

- **Conflict:** the wiring table (line 24) says `pipeline/exporter.py` is "Wired from `core/job_runner.py`" and triggered by "End-of-run artifact save step."
- **Current truth:** `pipeline/exporter.py` is DEAD; the only inbound import is from its own test file. `core/job_runner.py` writes `raw_deepgram.txt` inline (line 338) and does not import from `pipeline.exporter` at all.
- **Risk:** an AI agent or new developer reading this report would believe exporter.py is on the live path. They might modify exporter.py expecting their changes to take effect on the next run. They wouldn't.
- **Classification:** CONFLICTING (factual error in a presented-as-current report).

### 4.2 `docs/verifications/transcript_change_pipeline_trace_2026-05-12.md` — **PARTIALLY CONFLICTING**

- **Conflict:** the end-to-end diagram lists `pipeline/exporter.py` as `(writes raw/assembled transcript outputs)` in the production chain. Same factual error as 4.1.
- **Date is interesting:** this report is dated 2026-05-12, same date as the corrective `ACTIVE_PATH_AUDIT.md`. The two reports disagree on the same file.
- **Risk:** same as 4.1 — same shape, more recent file makes it harder to dismiss.
- **Classification:** CONFLICTING.

### 4.3 `docs/verifications/deterministic_formatting_corrections_audit_2026-04-28.md` — **STALE / CONFLICTING**

- **Conflict:** the "Files Audited" list (lines 7–16) references three files that no longer exist:
  - `spec_engine/parser.py` (no such file in `spec_engine/`)
  - `spec_engine/objections.py` (no such file)
  - `core/correction_runner.py` (singular; the actual file is `core/corrections_runner.py`, plural)
- **Risk:** an AI agent looking up "where the deterministic correction logic lives" would search for these non-existent files. The actual logic is now in `spec_engine/corrections.py`, `spec_engine/qa_fixer.py`, etc.
- **Classification:** STALE (refers to a pre-clean-format-migration architecture that no longer exists).

### 4.4 `docs/_archive/FORMATTING_AUDIT_AND_RULES.md` — **CORRECTLY ARCHIVED**

- Self-labeled SUPERSEDED in the first 10 lines. Points readers to current authority (CLAUDE.md §18, `depo_pro_style.md`).
- **Classification:** HISTORICAL. The archival treatment is exactly right.

### 4.5 `docs/_archive/FORMATTING_AUDIT_GUIDE.md` — **CORRECTLY ARCHIVED, NEAR-DUPLICATE**

- Self-labeled SUPERSEDED + "near-duplicate of FORMATTING_AUDIT_AND_RULES.md."
- **Classification:** HISTORICAL. Both archived files could be combined into one with no information loss, but the current treatment is acceptable.

### 4.6 `docs/MD_INSTRUCTION_GOVERNANCE_2026-04-28.md` — **MOSTLY ACTIVE, SLIGHTLY STALE**

- States the precedence chain: CLAUDE.md > AGENTS.md > README_AI.md > README.md.
- Current-state note (lines 14–22) is accurate as of 2026-04-29 and remains accurate today.
- **Slight staleness:** doesn't mention the newer `docs/audits/`, `docs/architecture/`, `docs/reports/` (this file) directories, or the verification harnesses at `tools/verification/`. The governance precedence chain is still right; the inventory of where authoritative docs live is incomplete.
- **Classification:** ACTIVE (with a minor inventory gap).

### 4.7 `AGENTS.md` and `README_AI.md` — **DUPLICATE**

- AGENTS.md (10 lines): "Before making changes ... read CLAUDE.md ... AGENTS.md wins on conflict ... see MD_INSTRUCTION_GOVERNANCE_2026-04-28.md."
- README_AI.md (10 lines): nearly identical content, slightly different wording, same intent.
- Each exists for a different agent-discovery convention (some tools look for AGENTS.md, others for README_AI.md). The duplication is *intentional but unmaintained* — if one is updated, the other will drift.
- **Classification:** ACTIVE-BUT-DUPLICATIVE.

### 4.8 `docs/plans/*_2026-05-12.md` (eight plan files) — **HISTORICAL, BUT MARKED**

- Eight dated plan files from 2026-05-12 covering Step A through Step E of the verbatim-punctuation work, plus `audit_hygiene_pass_2026-05-12.md`, `post_release_cleanup_2026-05-12.md`, `verbatim_punctuation_plan_2026-05-12.md`.
- These were *implementation prompts* that have been executed. The corresponding commits are in `git log` (commits `40be155` through `c6735fe`).
- **Not misleading**: each is dated, the work is in `git log`, and `.cursorrules` directs readers to the *most recent* dated plan for the area being touched — which is the right policy.
- **Classification:** HISTORICAL (correctly treated; no action needed beyond optional segregation into `docs/plans/_archive/` later).

### 4.9 `docs/verifications/phase_h_double_spacing_2026-04-27.md` — **HISTORICAL**

- Phase H verification from 2026-04-27. Subject is verifying `WD_LINE_SPACING.DOUBLE` reaches body emitters in `spec_engine/emitter.py`. Verdict was "No code patch required."
- The contract being verified is still valid; the verification was a one-time check.
- **Classification:** HISTORICAL (correctly dated; no conflict).

### 4.10 `ufm_engine/templates/MANIFEST_TODO.md` — **ACTIVE TODO**

- Records a specific unfinished item: `block_interpreted` wiring on the TX state title page. Steps 1–4 to re-add it are documented.
- **Classification:** ACTIVE (it's a real TODO with a specific implementation path).

### 4.11 `ufm_engine/post_processor/README.md` — **ACTIVE**

- Describes the post-processor contract for the Templates tab. Accurate.
- **Classification:** ACTIVE.

---

## SECTION 5 — Duplicated Logic

This audit identifies *parallel implementations* of similar functionality. None of these are bugs; some are intentional separation of concerns. Listing them so future work doesn't inadvertently collapse them.

### 5.1 Two correction subsystems — INTENTIONAL DUPLICATION

- `clean_format/` (primary, AI-driven, used by Start Transcription button) and `spec_engine/` (offline, deterministic, used by Run Corrections button) both modify transcript text. Per `CLAUDE.md` Change Rules 2–3 (post Phase-1 refresh) the two are designed to coexist; the rule is "do not introduce a third."
- **Risk:** if a developer doesn't read CLAUDE.md first, they may try to consolidate these and break the offline path. Mitigation is the explicit rule in CLAUDE.md.
- **Classification:** INTENTIONAL.

### 5.2 Two writers of `raw_deepgram.txt` — ACCIDENTAL

- `core/job_runner.py:338` writes the file in production (the live path).
- `pipeline/exporter.py:120–122` (`export_results` function) also writes a file with the same name — but this function has no production caller.
- **Risk:** if someone wires up `export_results` for any reason, two writers would race on the same path. Currently safe because only one is wired.
- **Classification:** ACCIDENTAL (resolved by deletion of exporter.py, deferred per Section 3.1).

### 5.3 Two AI-agent pointer files — INTENTIONAL DUPLICATION

- `AGENTS.md` and `README_AI.md` both redirect agents to CLAUDE.md. See 4.7.
- **Risk:** drift if one is updated and the other isn't.
- **Classification:** INTENTIONAL (different tools look for different filenames) BUT MAINTENANCE-PRONE.

### 5.4 Two `validate_marker_round_trip` call sites — INTENTIONAL (verification harnesses patch it)

- `clean_format/formatter.py` calls the real function during the active cleanup pass.
- `tools/verification/cleanup_prompt_diagnostic.py` and `tools/verification/marker_drift_verification.py` monkey-patch it for instrumentation.
- This is fine and explicit; the harnesses' purpose is to instrument.
- **Classification:** INTENTIONAL.

### 5.5 Two `probe_qa_failures.py` entry points — REDUNDANT

- `scripts/probe_residual_qa_failures.py` (lives at scripts/ root) — the actual probe.
- `scripts/diagnostics/probe_qa_failures.py` — a compatibility wrapper whose entire content is `from scripts.probe_residual_qa_failures import probe`.
- The wrapper exists to preserve historical runbook references to the old name. The probe lives at the new name.
- **Risk:** low — both files are clearly labeled.
- **Classification:** INTENTIONAL but ARCHIVE-READY (whenever the historical runbooks are also archived).

---

## SECTION 6 — Experimental / Legacy Scripts

### 6.1 `scripts/probe_residual_qa_failures.py` — STILL USEFUL

- Read-only diagnostic. Walks the corrections pipeline and counts/categorizes Q/A structure failures.
- Likely to be re-used if Q/A classification improvement work (running list item 2) starts.
- **Classification:** STILL USEFUL.

### 6.2 `scripts/diagnostics/probe_merged_utterances.py` — STILL USEFUL

- Read-only diagnostic. Counts merged-utterance candidates.
- Pairs with `core/utterance_splitter_runner.py`.
- **Classification:** STILL USEFUL.

### 6.3 `scripts/diagnostics/probe_qa_failures.py` — REDUNDANT WRAPPER

- See 5.5. Pure passthrough to `probe_residual_qa_failures`.
- **Classification:** SAFE TO ARCHIVE LATER (only if historical runbook references are also updated).

### 6.4 `scripts/repro/repro_minimize_bug.py` — STILL USEFUL

- Creates minimized JSON fixtures around Q/A failure context windows. The kind of thing that's needed when iterating on Q/A classification.
- **Classification:** STILL USEFUL.

### 6.5 `zip_formatting.ps1` (repo root) — STALE

- PowerShell script that zips three files: `spec_engine/emitter.py`, `spec_engine/document_builder.py`, `core/docx_formatter.py`.
- **Of the three referenced files, only `spec_engine/emitter.py` exists.** `spec_engine/document_builder.py` and `core/docx_formatter.py` are not in the repo.
- The script appears to be from a pre-clean-format-migration architecture and has not been updated since.
- **Risk:** running it would fail. Probably no one runs it.
- **Classification:** SAFE TO ARCHIVE LATER.

### 6.6 Root-level probe and corrections-run `.txt` files (22 files) — TRANSIENT DEBUG OUTPUT

- `probe_caram*.txt`, `probe_cavazos*.txt`, `probe_merged_*.txt`, `probe_residual_*.txt`, `corrections_run_*.txt`, `splitter_run_*.txt`.
- Gitignored (see `.gitignore` lines 15–17 + 23). Not tracked in git.
- These are diagnostic captures from earlier debug sessions. Already correctly handled by gitignore; only relevant to mention because they pollute `ls`.
- **Classification:** TRANSIENT (correctly gitignored; no action needed).

### 6.7 Root-level large binary artifacts — TRANSIENT, GITIGNORED

- `4-6-2026-Samuel Kulbeth.MP3` (52 MB) — gitignored via `*.MP3` pattern.
- `CONSOLIDATION_PROMPT.md.pdf` (440 KB) — gitignored by explicit name.
- `PROMPT_2_AI_RULES (2).docx` (43 KB) — gitignored via `**(2).docx` pattern.
- `app_output.txt`, `deepgram_output.txt` — gitignored.
- All correctly handled; mentioned only because they're visible at repo root.
- **Classification:** TRANSIENT (correctly gitignored).

### 6.8 `maintenance.txt` — UNCLEAR PURPOSE

- Empty or near-empty file at repo root.
- Not gitignored, but also not tracked (per `git status`). Likely a one-off scratch file.
- **Classification:** ABANDONED.

### 6.9 `tools/verification/*` — STILL USEFUL (just landed)

- `cleanup_prompt_diagnostic.py`, `marker_drift_verification.py`, `README.md`. Active Phase 2A operational tooling.
- **Classification:** STILL USEFUL (regression-sensitive for future prompt work).

---

## SECTION 7 — Files That Must Not Be Touched

The following files are operationally important, regression-sensitive, architecture-defining, or verification-critical. Any change to them requires deliberation and tests; some require user confirmation per CLAUDE.md.

### Architecture-defining

- `CLAUDE.md` — authoritative AI-context document; precedence #1 per `MD_INSTRUCTION_GOVERNANCE_2026-04-28.md`.
- `AGENTS.md`, `README_AI.md`, `.cursorrules`, `.github/copilot-instructions.md` — pointer files; any change must remain consistent with CLAUDE.md.
- `docs/architecture/PHASE_2A_KNOWN_LIMITATIONS.md` — records the operational compromises; informs Phase 2B design.

### Active production path

- `core/job_runner.py` — Start Transcription orchestrator.
- `pipeline/transcriber.py` — Deepgram integration.
- `pipeline/preprocessor.py`, `pipeline/chunker.py`, `pipeline/assembler.py`, `pipeline/vad_trimmer.py`, `pipeline/audio_quality.py`.
- `clean_format/formatter.py`, `clean_format/prompt.py`, `clean_format/docx_writer.py`, `clean_format/low_confidence_markers.py`.
- `ui/tab_transcribe.py` (specifically `start_transcription`, `_build_clean_format_case_meta`, `_run_clean_format_job`, `_on_clean_format_done`).
- All of `core/intake_parser.py`, `core/keyterm_extractor.py`, `core/case_vocab.py`, `core/ufm_field_mapper.py`, `core/pdf_extractor.py`, `core/source_docs_extractor.py`, `core/file_manager.py`, `core/job_config_manager.py`, `core/word_review.py`.

### Offline correction subsystem (separate from primary path)

- `spec_engine/` modules — corrections, qa_fixer, classifier, speaker_mapper, emitter, block_builder, models, processor, utterance_splitter.
- `core/corrections_runner.py`, `core/utterance_splitter_runner.py`.

### Verification-critical

- `tools/verification/cleanup_prompt_diagnostic.py`, `tools/verification/marker_drift_verification.py` — needed for prompt-change verification.
- `docs/audits/ACTIVE_PATH_AUDIT.md`, `docs/audits/CASE_MUTATION_REPORT.md`, `docs/audits/PHASE_2A_CORRECTION_APPLICATION.md` — operational audit history.

### Configuration

- `config.py`, `app_logging.py`, `requirements.txt`, `pytest.ini`, `.env` (not tracked).

---

## SECTION 8 — AI Confusion Risks

This is the section with the highest direct bearing on future AI-agent reliability.

### 8.1 HIGH — Two 2026-05-09 / 2026-05-12 verification reports state `pipeline/exporter.py` is wired

- See Section 4.1 and 4.2. Both reports predate the import-grep work in `ACTIVE_PATH_AUDIT.md`.
- An AI agent doing "what's in the active path?" research will encounter `transcript_change_pipeline_wiring_report_2026-05-09.md` early because it has clear authoritative-sounding language. The agent may not also read `ACTIVE_PATH_AUDIT.md`.
- **Mitigation idea:** prepend a status note to the older reports pointing at `ACTIVE_PATH_AUDIT.md` as the current authority. Or move them to `docs/_archive/`.

### 8.2 HIGH — 2026-04-28 deterministic-corrections audit lists non-existent modules

- See Section 4.3. An agent looking for "the deterministic correction code" will follow the audit's file list to dead links.
- **Mitigation idea:** prepend a status note, or move to `docs/_archive/`.

### 8.3 MEDIUM — `zip_formatting.ps1` references nonexistent files

- See Section 6.5. An agent invoking it would fail; an agent reading it would believe `core/docx_formatter.py` exists.

### 8.4 MEDIUM — Eight 2026-05-12 plan files reference completed work as if active

- Each is dated and the work is in `git log`, so the staleness is recoverable by reading git history. But the `docs/plans/` directory has no `_archive/` subdirectory and no top-level README explaining "these are implementation prompts; check git log for what landed."
- **Mitigation idea:** add a `docs/plans/README.md` that points to git history for completed work and lists currently-active plans (none right now).

### 8.5 MEDIUM — `pipeline/exporter.py` and `pipeline/pyannote_diarizer.py` look active by virtue of living in `pipeline/`

- An agent doing "what's in pipeline/?" will list both. Only `pyannote_diarizer.py` self-documents its dead status; `exporter.py` reads like an active module.
- **Mitigation idea:** add a `pipeline/exporter.py` docstring header matching the `pyannote_diarizer.py` style.

### 8.6 LOW — `spec_engine/ufm_rules_backup.py` is a literal `_backup` filename

- The `_backup` suffix is a clear "don't use me" signal to humans. AI agents may or may not pick that up. Cost of confusion is low because the file isn't imported anywhere.

### 8.7 LOW — `scripts/diagnostics/probe_qa_failures.py` is a passthrough wrapper

- An agent might think there are two implementations when there's only one. The wrapper's docstring is explicit about its compatibility purpose, which mitigates.

### 8.8 LOW — `AGENTS.md` and `README_AI.md` are duplicates that could drift

- Low impact today. Becomes higher impact if one is updated and the other isn't.

---

## SECTION 9 — Recommended Future Hygiene Plan

**Staged, future actions. Not for this audit.** Each is a small, separable commit that future work can pick up when convenient.

### Stage 1 — Archive segregation (low risk, high signal for AI agents)

1. Create `docs/_archive/verifications/` and move:
   - `transcript_change_pipeline_wiring_report_2026-05-09.md`
   - `transcript_change_surface_report_2026-05-09.md`
   - `transcript_change_pipeline_trace_2026-05-12.md` (contains the same exporter-is-wired error)
   - `deterministic_formatting_corrections_audit_2026-04-28.md`
   - `phase_h_double_spacing_2026-04-27.md`
   Add a `_archive/verifications/README.md` stating: "These reports describe earlier states of the repo. For current architecture, see `docs/audits/ACTIVE_PATH_AUDIT.md`. Specific contradictions identified in `docs/reports/dead_module_hygiene_audit_2026-05-15.md`."

2. Create `docs/plans/_archive/` and move the eight 2026-05-12 plan files. Add a brief README explaining that plans are implementation prompts and the actual work landed via the commits listed in `git log`.

3. **Estimated effort:** one commit per directory move. ~30 minutes total. No code changes.

### Stage 2 — Dead-module disposition (medium risk; per CLAUDE.md §17 deliberation required)

1. **`pipeline/exporter.py`** — already documented as having no production caller. Decision: delete the module and its test, or add a "DEAD CODE — see PHASE_2A_KNOWN_LIMITATIONS.md" header to match `pyannote_diarizer.py` style. Recommend the header approach until a Phase 2B-or-later cleanup commit; the module is harmless where it is.

2. **`spec_engine/ufm_rules_backup.py`** — first, diff it against `ufm_rules.py` to see if the backup has any rules the current file is missing. If not, delete. If yes, merge then delete. Either way, one focused commit.

3. **`pipeline/pyannote_diarizer.py`** — already self-documented. Leave as-is unless an explicit "do we want diarization?" decision is made. The cost of keeping it is approximately zero; the cost of deleting is irreversible.

4. **Estimated effort:** one commit for exporter status, one for ufm_rules_backup. ~1 hour each.

### Stage 3 — Stale-script cleanup

1. `zip_formatting.ps1` — either update file list to current architecture, or delete. The script appears unused.
2. `maintenance.txt` — appears empty/abandoned. Delete or repurpose.
3. `scripts/diagnostics/probe_qa_failures.py` — wrapper kept for historical runbook compat. Search for runbook references; if none remain, delete the wrapper.
4. **Estimated effort:** one cleanup commit. ~30 minutes.

### Stage 4 — Documentation consolidation

1. Update `MD_INSTRUCTION_GOVERNANCE_2026-04-28.md` to mention the newer directories (`docs/audits/`, `docs/architecture/`, `docs/reports/`, `tools/verification/`).
2. Consider whether `AGENTS.md` and `README_AI.md` can be reduced to one canonical file with a symlink or with explicit "tool conventions" notes.
3. Add a `docs/README.md` mapping the directory taxonomy (audits vs reports vs verifications vs plans vs architecture).
4. **Estimated effort:** one commit. ~45 minutes.

### Stage 5 — Optional: AI-context drift detection

1. Add a CI check (or pre-commit hook) that verifies every file mentioned in `docs/verifications/*.md` and `docs/audits/*.md` still exists.
2. Catches the "audit references nonexistent file" failure mode (Section 4.3) proactively.
3. **Estimated effort:** one half-day for the script plus a CI configuration commit.

---

## Closing Notes

- **No edits performed by this audit.** Working tree is clean for everything except this new file at `docs/reports/dead_module_hygiene_audit_2026-05-15.md`.
- **No commits made by this audit.** The user will decide whether and when to commit the report.
- **No production behavior changed.** The audit is observational.
- The five highest-leverage Stage 1 + Stage 2 items can each ship as one commit and together would significantly reduce AI-agent confusion risk without altering any runtime behavior.

Future readers can pick up any single stage above without dependencies on the others.
