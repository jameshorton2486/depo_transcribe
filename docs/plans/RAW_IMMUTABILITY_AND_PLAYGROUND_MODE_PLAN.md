# Raw Immutability + Playground Mode + Architectural Stabilization — Phased Plan

**Status:** read-only planning document. **No production code is modified by this document.**
**Approval gate:** the user reviews this plan and signs off before any production-code phase begins.
**Anchors:**
- `docs/architecture/CURRENT_PIPELINE_TRACE.md`
- `docs/architecture/TRANSCRIPT_MUTATION_POINTS.md`
- `docs/architecture/SPEAKER_HANDLING_AUDIT.md`
- `docs/architecture/DEEPGRAM_FLOW_AUDIT.md`
- `docs/architecture/PLAYGROUND_DIFFERENCES.md`
- `CLAUDE.md` (architectural authority)

---

## 0. Guiding principles

The mega-prompt's 12 phases are not equally risky. The principles that drive the sequencing below:

1. **Raw immutability is a prerequisite, not an outcome.** Before any high-risk refactor (Phases F-K below), there must be a forensic-quality saved record of what Deepgram returned. Today's `raw_deepgram.{txt,json}` is overwritten on every run and is post-mutation; that is not a safe baseline.
2. **Parity testing is a prerequisite for refactors that touch speaker handling.** Refactoring `smooth_speakers` / `_build_speaker_remap` / `_attach_speaker_labels` without a saved ground-truth comparison is the path to silent legal corruption.
3. **CLAUDE.md is the architectural authority.** Phases that would collapse `spec_engine` into the active path require a CLAUDE.md amendment first; that amendment is itself a discrete approval step, not bundled with implementation.
4. **Each phase has a validation gate.** A phase does not proceed to the next until its acceptance tests pass and the user explicitly signs off.
5. **Rollback is always defined.** Every production-code phase has a documented rollback procedure (typically: `git revert <commit-sha>`).

---

## 1. Phase inventory

Phases are lettered A-M (sequenced) rather than numbered to discourage "Phase 1, 2, 3 done; we're 25% finished" mental arithmetic. They are not equally sized.

| ID | Phase | Risk | Touches production code? | Approval gate per phase |
|---|---|:---:|:---:|:---:|
| A | Raw immutability layer (`pipeline/raw_store.py`) | LOW | YES (new module + 1 call site in job_runner) | YES |
| B | Word-object integrity tests | LOW | NO (tests only) | YES |
| C | True Playground Mode — bypass the remaining divergences | MEDIUM | YES (guards in assembler, transcriber, vad_trimmer, audio_quality) | YES |
| D | Transcript-integrity test suite | LOW | NO (tests only) | YES |
| E | Snapshot tooling for forensic comparison (Cavazos + Etminan + one Zoom case) | LOW | NO (tooling under `tools/`) | YES |
| F | Speaker validation layer (`pipeline/speaker_validation.py`, `output/audit/speaker_changes.json`) | MEDIUM | YES (annotate-only initially; no enforcement) | YES |
| G | Refactor assembler — stitch + dedup only, NO speaker rewriting | **HIGH** | YES (significant simplification) | YES — multi-case validation required |
| H | Structured transcript layer (`pipeline/structured_transcript.py`) bridging to spec_engine | **HIGH** | YES (active-path call into spec_engine — CLAUDE.md amendment required) | YES |
| I | Preprocessing safety review + tier defaults | MEDIUM | YES (config-only) | YES |
| J | UI exposure — Playground toggle, raw vs structured viewers, speaker audit viewer | MEDIUM | YES (UI) | YES |
| K | Documentation cleanup — AUTHORITATIVE_RULES.md, TRANSCRIPT_LAYERS.md, SPEAKER_HANDLING_RULES.md | LOW | NO (docs) | YES |
| L | Final validation — full pytest, regression suite, comparison snapshots | LOW | NO (tests + report) | YES |
| M | Migration / risk / future docs | LOW | NO (docs) | n/a (project close-out) |

---

## 2. Phase-by-phase detail

### Phase A — Raw immutability layer

**Goal.** Create a write-once persisted record of the unmutated Deepgram response that downstream stages may read but never overwrite.

**Files created.**
- `pipeline/raw_store.py` — `save_raw_response(case_dir, per_chunk_responses, audio_path) -> Path`
- `output/raw/<case_name>/raw_dg_response_<stamp>.json` — the unmutated per-chunk Deepgram bodies, plus metadata (audio source, request params used, timestamp). Naming includes the timestamp so multiple runs of the same case never collide.

**Files modified.**
- `core/job_runner.py` — one new call to `raw_store.save_raw_response(...)` immediately after the per-chunk loop and before `reassemble_chunks`. Existing `raw_deepgram.{txt,json}` continues to be written for backward compatibility.

**Rules enforced inside `raw_store.py`.**
- Refuses to write if the target path already exists (timestamp suffix prevents collision).
- Sets the saved file as read-only (`os.chmod(path, 0o444)`) on filesystems that support it.
- Logs the destination at INFO: `[RAW_STORE] saved <path>`.

**What this does NOT do.**
- It does not remove the existing `raw_deepgram.{txt,json}` writers. They remain. The "canonical" name continues to point at the post-mutation files. Phase H is what eventually makes the new raw_store the canonical source.

**Validation gate.**
- Unit tests: write succeeds, file is read-only, second write to same path raises.
- One Cavazos run end-to-end with PLAYGROUND_MODE=False, verify the new file is written and unchanged after the run completes.
- `pytest pipeline/tests core/tests spec_engine/tests clean_format/tests` → 0 failures.

**Rollback.** `git revert` the commit. The new file becomes orphaned (no downstream reader yet); harmless.

**Blast radius.** None. Pure addition.

---

### Phase B — Word-object integrity tests

**Goal.** Lock in the contract that word objects (`{word, speaker, start, end, confidence}`) survive transcription, assembly, and any later restructuring without timing corruption or loss.

**Files created.**
- `tests/transcript_integrity/test_word_object_integrity.py` — golden-file tests against a saved Cavazos `raw_dg_response_*.json` from Phase A. Loads, runs the current production assembly, asserts:
  - every word from Deepgram appears in the assembled `words` list (modulo overlap dedup) AT LEAST as a candidate (allow drops only via the documented dedup mechanism)
  - `start` / `end` monotone non-decreasing within each speaker
  - `confidence` preserved verbatim (no rounding)

**Files modified.** None.

**What this does NOT do.** It does not yet enforce zero loss; it characterizes the *current* behavior so any future refactor is held to that contract or better.

**Validation gate.**
- Tests pass on current code.
- The fixtures used are saved alongside the test (`tests/transcript_integrity/fixtures/cavazos_raw_dg_<stamp>.json`).

**Rollback.** Delete the test file. No production change.

**Blast radius.** None. Pure addition.

---

### Phase C — True Playground Mode

**Goal.** Make `PLAYGROUND_MODE=True` bypass the 10 of 12 divergences listed in `PLAYGROUND_DIFFERENCES.md::Summary`. The user can then run the same audio against the same Deepgram options through both Playground and our app and see byte-for-byte (or close to it) parity.

**Files modified.**
- `pipeline/vad_trimmer.py::trim_silence` — early return when `config.PLAYGROUND_MODE=True` (do not modify audio path).
- `pipeline/audio_quality.py::analyze_audio` — when `PLAYGROUND_MODE`, return a `CLEAN` tier and `is_stereo=False / zoom_dual_mono=False` so downstream channel-extraction does not fire.
- `pipeline/transcriber.py::_transcribe_direct` — guard `smooth_speakers` and the per-chunk `merge_utterances` behind `if not PLAYGROUND_MODE`.
- `pipeline/assembler.py::reassemble_chunks` — guard the cross-chunk `merge_utterances` (line 663), `_build_speaker_remap` (line 605), `_merge_adjacent_same_speaker_overlap` (line 654), and `_attach_speaker_labels` (line 376) behind `if not PLAYGROUND_MODE`. When PLAYGROUND_MODE, the assembled `utterances` equal the input `raw_utterances` with absolute timestamps applied.
- `core/job_runner.py` — adds a `[PLAYGROUND MODE ENABLED]` log line at job start.

**Files created.**
- `pipeline/playground_mode.py` — a tiny module that exposes `is_playground_mode_active() -> bool` and a context manager for tests. (The config flag stays in `config.py`.)
- `docs/architecture/PLAYGROUND_MODE.md` — user-facing doc on what the flag does and when to use it.

**Validation gate.**
- Test: run one short audio file (saved fixture, e.g. 3 minutes) through PLAYGROUND_MODE=True and capture the saved raw response. Run the same file through Playground via the Deepgram web UI with the same flags (this is a manual step, recorded in the test docstring with expected diff output). Assert that the saved raw response matches the Playground response in transcript text, utterance count, speaker integer pattern.
- `pytest` all four suites → 0 failures.

**Rollback.** `git revert` the commit. Existing PLAYGROUND_MODE bypass (chunking + normalize) remains; the new additional bypasses revert cleanly.

**Blast radius.** PLAYGROUND_MODE flag is OFF by default. Production paths are not affected.

---

### Phase D — Transcript-integrity test suite expansion

**Goal.** Cover the rest of the integrity contracts.

**Files created (all under `tests/transcript_integrity/`).**
- `test_raw_immutability.py` — asserts `raw_store` files are read-only and never overwritten.
- `test_speaker_preservation.py` — golden-fixture test that runs current production assembly and records the post-mutation speaker IDs; future refactors must keep or improve fidelity to the fixture.
- `test_playground_mode.py` — asserts every divergence in `PLAYGROUND_DIFFERENCES.md` is bypassed when `PLAYGROUND_MODE=True`.
- `test_chunk_reassembly.py` — asserts overlap dedup does not drop unique words.
- `test_overlap_deduplication.py` — same, more granular cases.
- `test_no_word_loss.py` — for production-mode, asserts the assembled word count equals (Σ chunk word counts) − (counted overlap drops).

**Files modified.** None.

**Validation gate.** All new tests pass. `pytest` all four suites → 0 failures.

**Rollback.** Delete the test files.

**Blast radius.** None.

---

### Phase E — Snapshot tooling

**Goal.** A reusable snapshot tool that captures: (a) the raw Deepgram response, (b) the post-assembly output, (c) the post-Anthropic output, (d) the final DOCX paragraph text — for a given case, suitable for regression comparison.

**Files created.**
- `tools/snapshots/capture_full_pipeline_snapshot.py` — runs one case (with `WALKTHROUGH_CAPTURE=1`-style instrumentation already partially in place via `tools/walkthrough/`) and writes a labeled snapshot bundle under `docs/snapshots/<case>/<stamp>/`.
- `tools/snapshots/compare_snapshots.py` — diffs two snapshot bundles.

**Files modified.** None.

**Validation gate.**
- Captures one snapshot of Cavazos and one of Etminan as fixture data the rest of the plan compares against.

**Rollback.** Delete the tool. Snapshots are independent files.

**Blast radius.** None.

---

### Phase F — Speaker validation layer (annotate-only)

**Goal.** Persist every speaker-ID change with provenance, BEFORE any refactor that changes the speaker-handling logic.

**Files created.**
- `pipeline/speaker_validation.py`:
  - `record_speaker_change(case_dir, original_speaker, replacement_speaker, time_range, rule, rationale) -> None`
  - `audit_path(case_dir) -> Path` → `<case_dir>/output/audit/speaker_changes.json`
  - Writes append-only JSONL records.

**Files modified.**
- `pipeline/transcriber.py::smooth_speakers` — log every actual rewrite via `record_speaker_change(...)`.
- `pipeline/assembler.py::_build_speaker_remap` — log every non-identity mapping.
- `pipeline/assembler.py::_attach_speaker_labels` — log every integer-to-role-string derivation.

**Rules:**
- Annotate-only. No behavior change. The functions still do what they do today; they just produce an audit trail.
- File location is under the case folder so it travels with the case.

**Validation gate.**
- Run on Cavazos with PLAYGROUND_MODE=False. Inspect the resulting `speaker_changes.json`. It should enumerate every rewrite the auditor in `SPEAKER_HANDLING_AUDIT.md` predicts. If a rewrite is happening that the audit document does not predict, STOP and amend the audit before proceeding.

**Rollback.** `git revert` the commit. The audit file becomes orphaned; harmless.

**Blast radius.** Adds a small per-rewrite filesystem write. Acceptable.

---

### Phase G — Refactor assembler (HIGH RISK — multi-case validation required)

**Goal.** Strip `pipeline/assembler.py` down to its CLAUDE.md-mandated responsibility: stitch chunks, dedup exact overlap, preserve timestamps and utterance ordering. Remove `smooth_speakers`-like behavior, `_build_speaker_remap` if its job moves to a separate layer, `_attach_speaker_labels` role derivation, and the cross-chunk `merge_utterances`.

**Pre-conditions (MUST be true before this phase starts):**
- Phase A (raw immutability) shipped and validated on Cavazos.
- Phase B (word-object tests) shipped and green.
- Phase D (integrity suite) shipped and green.
- Phase E (snapshot tooling) shipped, and Cavazos + Etminan + 1 Zoom case snapshots saved.
- Phase F (speaker_validation) shipped and Cavazos audit file inspected; every existing rewrite documented.

**Files modified.**
- `pipeline/assembler.py` — substantial simplification.
- Possibly `core/job_runner.py` — if the new assembler returns a different shape (e.g. no `speaker_label`), downstream code that read `speaker_label` (specifically `core/job_runner.py::_build_transcript_from_utterances`) must be updated.

**What moves where.**
- `smooth_speakers` per-chunk logic and `_build_speaker_remap` cross-chunk logic — move to a new `pipeline/structured_transcript.py` layer (Phase H), where they are explicitly opt-in and audited.
- `_attach_speaker_labels` role-derivation — moves to `pipeline/structured_transcript.py` (Phase H). Until Phase H, the active path's downstream code uses bare integer speaker IDs.

**Validation gates (sequential):**
1. Unit tests pass.
2. Snapshot comparison Cavazos → Phase-G output ≥ Phase-A snapshot (word identity, no drops).
3. Snapshot comparison Etminan → same.
4. Snapshot comparison Zoom case → same.
5. Speaker_changes audit shows zero unexplained changes.
6. End-to-end run on each of the three cases — DOCX produced without errors.
7. **User signs off after reading the comparison report.**

**Rollback.** `git revert`. The three-case snapshots provide a regression check.

**Blast radius.** **HIGH.** This is the most consequential single phase in the plan. It is sequenced last among the medium-risk phases for that reason.

---

### Phase H — Structured transcript layer

**Goal.** Implement the deterministic restructuring stage from CLAUDE.md's "structured transcript" concept, with a clean import boundary to `spec_engine`.

**CLAUDE.md prerequisite.** The current Rule 3 (`spec_engine` is offline-only) must be amended. The amendment is a separate user-approval step before this phase starts. Proposed wording: *"Rule 3 (amended): `spec_engine` may be invoked from the active path EXCLUSIVELY by `pipeline/structured_transcript.py`. No other active-path module is permitted to import `spec_engine`."*

**Files created.**
- `pipeline/structured_transcript.py` — owns:
  - Cross-chunk speaker remap (moved from assembler).
  - Speaker smoothing (moved from `pipeline/transcriber.py`).
  - Role-label derivation (moved from assembler).
  - Q/A repair (currently in `clean_format/speaker_turn_repair.py` — either left there, since it operates on text; or moved here if it operates on blocks. Decision TBD in Phase-H prep.)
  - Block classification, corrections, qa_fixer integration via `spec_engine`.

**Files modified.**
- `pipeline/transcriber.py` — `smooth_speakers` removed.
- `pipeline/assembler.py` — already stripped in Phase G.
- `core/job_runner.py` — new call site: `structured = structured_transcript.build(assembled_raw, case_meta)` after `reassemble_chunks` and before clean_format.
- `clean_format/formatter.py` — input becomes the structured transcript rather than the raw transcript.

**Validation gates.**
- Same three-case snapshot regression check as Phase G.
- Anthropic cleanup downstream still produces valid DOCX.
- CLAUDE.md amendment is in place (separate approval).

**Rollback.** `git revert`.

**Blast radius.** **HIGH.** Adds a new layer to the active path and changes data shape between layers.

---

### Phase I — Preprocessing safety review

**Goal.** Document and decide safe defaults for each tier (CLEAN / ENHANCED / RESCUE), including whether VAD should run by default.

**Files created.**
- `docs/architecture/PREPROCESSING_SAFETY_REVIEW.md`.

**Files modified.**
- Possibly `config.py` — defaults for the auto-detect tier strategy. No FFmpeg filter logic changes in this phase.

**Validation gate.** Snapshot comparison on the three cases with and without VAD; user reads the diff and signs off on which default to ship.

**Rollback.** `git revert`.

**Blast radius.** MEDIUM (changes user-visible audio handling).

---

### Phase J — UI improvements

**Goal.** Surface the new layers in the Transcribe tab.

**Files modified.**
- `ui/tab_transcribe.py` — add Playground Mode toggle, raw/structured viewer buttons, speaker-audit viewer button.

**Validation gate.** Manual UI smoke test on Windows. Type-check + the existing UI tests pass.

**Rollback.** `git revert`.

**Blast radius.** MEDIUM (UI changes; user-visible).

---

### Phase K — Documentation cleanup

**Goal.** Update CLAUDE.md and the architecture docs to reflect the new layered model.

**Files created.**
- `docs/architecture/AUTHORITATIVE_RULES.md` — the rules in force after the refactor.
- `docs/architecture/TRANSCRIPT_LAYERS.md` — what each layer owns.
- `docs/architecture/SPEAKER_HANDLING_RULES.md` — the new contract.

**Files modified.**
- `CLAUDE.md` — Rule 3 amendment (already happened in Phase H); add cross-references to the new layered model.

**Rollback.** `git revert`. Docs only.

**Blast radius.** None operationally.

---

### Phase L — Final validation

**Goal.** Full test suite + regression run + report.

**Files created.**
- `docs/final/REFACTOR_SUMMARY.md`.

**Files modified.** None.

**Rollback.** n/a.

**Blast radius.** None.

---

### Phase M — Migration / risks / future

**Files created.**
- `docs/final/MIGRATION_NOTES.md` — what to do with existing case folders that have post-mutation `raw_deepgram.{txt,json}`.
- `docs/final/REMAINING_RISKS.md` — items not addressed.
- `docs/final/FUTURE_RECOMMENDATIONS.md` — review-layer scoping, audio-sync, etc.

---

## 3. Dependency graph

```
A (raw immutability)
   ├─► B (word object integrity tests, depends on A snapshots)
   │
   ├─► C (true playground mode)
   │
   ├─► D (transcript integrity suite, depends on A + B)
   │
   ├─► E (snapshot tooling, depends on A)
   │
   ├─► F (speaker validation annotate-only)
   │     │
   │     └─► G (assembler refactor) — REQUIRES A, B, D, E, F
   │           │
   │           └─► H (structured transcript) — REQUIRES G + CLAUDE.md amendment
   │
   ├─► I (preprocessing safety) — independent of A-H
   │
   ├─► J (UI) — depends on C and H
   │
   ├─► K (documentation cleanup) — depends on G and H
   │
   ├─► L (final validation) — terminal
   │
   └─► M (migration notes) — terminal
```

**Critical path:** A → B/D/E/F → G → H → J → K → L → M.

**Parallelizable:** C, I.

---

## 4. Estimated sizing per phase

Estimates are wall-clock per phase assuming focused work and the validation gates being honored. Each phase ends with a user-approval gate.

| Phase | Estimated session count | Why |
|---|:---:|---|
| A | 1 | Tight scope; new module + 1 call site. |
| B | 1 | Tests + saved fixture. |
| C | 1-2 | Six guard sites; one parity test cycle with Playground. |
| D | 1 | Tests only. |
| E | 1 | Tooling + capture three case snapshots. |
| F | 1 | Annotate-only; small. |
| G | **2-3** | High risk; mandatory three-case snapshot validation. |
| H | **2-3** | CLAUDE.md amendment + active-path call into spec_engine + downstream wiring. |
| I | 1 | Doc + small config decisions. |
| J | 1-2 | UI work; CustomTkinter widget additions. |
| K | 1 | Docs. |
| L | 1 | Validation report. |
| M | 1 | Migration / risk docs. |

**Total:** roughly 14-18 focused sessions. Not deliverable in a single autonomous session.

---

## 5. Validation gates — what "the gate is open" means

Before any phase passes its gate, ALL of the following must hold:

1. **Tests pass** (`pytest pipeline/tests core/tests spec_engine/tests clean_format/tests`) — 0 failures.
2. **No new TODO / FIXME comments** introduced in production code that are unaddressed by the time of the gate.
3. **Snapshot comparison** (Phase E tools) shows expected diffs only.
4. **Speaker audit** (`speaker_changes.json`) shows zero unexplained entries.
5. **User reviews the diff** (or summary thereof) and explicitly signs off.

A phase that fails its gate **does not progress to the next phase**. The team either fixes the failures or rolls the phase back.

---

## 6. Rollback strategy

Every production-code phase is delivered as a single git commit (or a small named series). Rollback is:

1. `git revert <sha>` (or the series).
2. Re-run `pytest` to confirm green.
3. Re-run the snapshot tool on the saved fixtures to confirm production behavior is restored.

The new artifacts created on disk (under `output/raw/`, `output/audit/`, `docs/snapshots/`) are orphaned but harmless after rollback. They can be deleted manually.

---

## 7. What this plan deliberately does NOT do

- **It does not modify `clean_format/prompt.py`.** The strict-verbatim Anthropic prompt is the load-bearing legal-fidelity contract. Changing it is out of scope.
- **It does not modify `clean_format/docx_writer.py`.** DOCX layout is settled.
- **It does not introduce an "AI splitter" or any new model call** into the active path beyond the existing Anthropic cleanup.
- **It does not collapse `spec_engine` and `clean_format`.** CLAUDE.md Rule 2 (clean_format owns active-path cleanup + DOCX) remains in force. The Phase H amendment is narrow: it permits `pipeline/structured_transcript.py` to call into spec_engine; no other active-path module is allowed to.
- **It does not remove the existing speaker-turn-repair (`clean_format/speaker_turn_repair.py`)** or the keyterm-sanitizer (`pipeline/keyterm_sanitizer.py`). Both are working and conservative. They will be reviewed for relocation during Phase H but not removed.
- **It does not rewrite the merge-threshold investigation tooling.** That tooling is paid-for evidence; it stays untouched.

---

## 8. Approval requested before any Phase A code is written

Before any production-code phase begins, the user reviews this plan and approves:

1. The phase order and validation-gate model.
2. The Phase H prerequisite (CLAUDE.md Rule 3 amendment).
3. The sessions-per-phase estimates.
4. The "no production change without user sign-off after the gate" discipline.

Once approved, Phase A begins. Each subsequent phase begins only after the prior phase's gate is open and the user has explicitly approved progression.
