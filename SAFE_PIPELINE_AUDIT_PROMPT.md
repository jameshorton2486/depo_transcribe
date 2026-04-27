> **STATUS: REFERENCE ONLY** — baseline figures (e.g., test counts) in
> this file are stale. Architectural guidance is still broadly correct.
> Do not use the test-count assertions as truthful current-state claims.
> Verify against a live `pytest` run before relying on any specific
> number. Banner added 2026-04-27 ahead of master fix Phase F.

# Safe Pipeline Audit Prompt

Use this prompt inside Claude Code / Cursor / VS Code agent when working on Depo-Pro.

## Purpose

This prompt is adapted to the **current live codebase**. It is designed to
drive a safe audit and surgical improvements without rewriting working
architecture or re-implementing already-fixed phases.

Depo-Pro is a production-bound legal transcript system governed by:

- Texas Uniform Format Manual (UFM)
- Morson's English Guide for Court Reporters

The system is already stable and heavily verified. The goal is to **finish and
verify** remaining work safely, not redesign the application.

---

## Global Rules

1. Read `AGENTS.md` and `CLAUDE.md` before making changes.
2. Do not refactor architecture.
3. Do not move logic across layers.
4. Do not rewrite `classifier.py` or `qa_fixer.py` wholesale.
5. Preserve verbatim speech:
   - keep `uh`, `um`, `uh-huh`, `yeah`, `nope`
   - preserve interruptions and ` -- `
6. Do not rewrite objections into normalized legal phrasing.
7. `spec_engine` is the authority for:
   - corrections
   - Q/A structure
   - transcript structure
8. `ui/` is display and workflow only.
9. `pipeline/` is audio / Deepgram / chunking only.
10. Make only deterministic, testable, reversible changes.
11. Do not commit unless verification passes.

---

## Current Project Reality

- Architecture is already correct and should remain intact.
- `spec_engine/block_builder.py` already converts utterances to blocks.
- `spec_engine/classifier.py` already contains the primary stateful
  classification logic.
- `spec_engine/qa_fixer.py` is the secondary structural repair layer.
- Speaker roles are driven by verified `speaker_map` data.
- `spec_engine/emitter.py` already uses the live tab-stop contract:
  `720 / 1440 / 2160`.
- Older prompts that ask for `format_transcript()` or `formatter.py` work are
  stale for this repo.

Ignore generic guidance that assumes the architecture is missing.

---

## Objectives

Perform a safe audit and targeted completion of the live pipeline:

1. Git branch state
2. Deepgram -> block -> Q/A flow
3. Transcript-accuracy gaps
4. Verification coverage and stale skipped tests

---

## Phase 0 - Git Safety Check (Read Only)

Run:

- `git branch -a`
- `git log --oneline --graph --all --decorate`

If a branch named
`origin/codex/audit-and-improve-document-intake-pipeline` exists, also run:

- `git log origin/main..origin/codex/audit-and-improve-document-intake-pipeline --oneline`

Determine:

- Is the branch fully merged?
- Are there unmerged commits?

Output:

- `SAFE TO DELETE`
- `NEED REVIEW`
- `NEED MERGE`

Do not delete or merge automatically.

---

## Phase 1 - Deepgram Pipeline Audit

Trace the live path:

- `ui/tab_transcribe.py`
- `core/job_runner.py`
- `pipeline/preprocessor.py`
- `pipeline/chunker.py`
- `pipeline/transcriber.py`
- `pipeline/assembler.py`
- `pipeline/processor.py`
- `spec_engine/block_builder.py`
- `spec_engine/processor.py`

Verify:

- `utterances=True` is used
- `paragraphs=False` is used
- `smart_format` matches the live repo expectation
- no transcript-structure logic bypasses `spec_engine`

Identify:

- where utterances are first transformed into blocks
- where transcript merging occurs
- where Q/A classification happens
- where Q/A repair happens

Flag:

- any place where structure is inferred too late
- any place where merged speaker text is fed forward without sentence-aware repair
- any place where low-confidence or pause fragmentation creates bad block boundaries

---

## Phase 2 - Structure Validation

Compare actual order against the expected live design:

1. Deepgram utterances fetched
2. utterance merging / chunk assembly
3. block construction
4. deterministic corrections
5. speaker mapping
6. primary Q/A classification
7. Q/A structural repair
8. objection extraction / reclassification as needed
9. validation
10. emission

If different:

- identify exact file + function
- explain whether it is intentional, stale docs, or a real defect

---

## Phase 3 - Safe Improvements

Only after audit, implement truly missing improvements.

Allowed:

- sentence-aware block repair
- deterministic merged `Q? A. Q?` reconstruction
- deterministic `A. Q?` split repair
- bounded same-speaker continuation merging
- guards against reporter admin text being converted into witness answers
- guards against low-confidence/pause fragments causing bad splits

Not allowed:

- broad rewrites
- AI-based structural decisions
- moving core logic out of `spec_engine`
- introducing a new architecture or "v2" pipeline

Prefer minimal edits in the smallest responsible file.

---

## Phase 4 - Verification Cleanup

Audit skipped tests and separate them into:

1. stale/deletable
2. rewrite-to-current-contract
3. intentional future-feature skips

Do **not** add runtime code to satisfy dead tests that target:

- removed formatter APIs
- inactive `ufm_engine`
- nonexistent `main` UI contracts

Only keep intentional skips for live future features such as:

- golden fixtures that are not yet committed
- explicitly planned modules not present in the repo

---

## Phase 5 - Verification

Run:

- `python -m py_compile` on changed files
- focused pytest files for touched areas
- `python -m pytest -q`

Run `spec_engine/tests/test_golden.py` only if required golden fixture files
exist. If they do not exist, report that clearly instead of treating it as a
failure.

Success criteria:

- 0 failing tests
- no regression in active transcript tests
- no UFM formatting regressions in touched areas

If any test fails:

- stop
- explain the failure
- fix only if the fix is local and safe
- do not commit until green

---

## Phase 6 - Output Report

Provide:

1. Git Audit Result
2. Pipeline Issues Found
3. Changes Made
4. Tests Run
5. Risk Assessment
6. Remaining Deferred Items

---

## Phase 7 - Commit Only If Safe

Commit only if:

- all active tests pass
- no structural regression is introduced
- changes are minimal and verified

Example commit message:

`feat(spec_engine): strengthen deterministic merged qa reconstruction`

If not safe:

- do not commit
- explain blockers clearly

---

## Notes On Incorrect Older Prompts

Do not blindly implement prompts that require:

- `format_transcript()` kwargs that no longer exist
- a new `app.py` review/diff UI path that is not part of the live design
- tab-stop fixes in `spec_engine/emitter.py` that are already present
- rewriting the classifier into a simpler state machine

Those instructions are stale relative to the current repository.
