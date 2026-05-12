# Transcript Change Pipeline Wiring Report (2026-05-09)

## Goal

Show where transcript-changing files are wired into runtime flow and what events trigger their execution.

## 1) Primary runtime chain (Transcribe tab)

1. **UI trigger** — user clicks **Start Transcription** in `ui/tab_transcribe.py` (`start_transcription`).
2. `start_transcription` runs background job orchestration via `core/job_runner.py`.
3. `core/job_runner.py` calls `pipeline.transcriber.transcribe_chunk(...)` per chunk.
4. `core/job_runner.py` reassembles chunk output through `pipeline.assembler.reassemble_chunks(...)`.
5. After pipeline completion, `ui/tab_transcribe.py` calls `_start_clean_format(...)`.
6. `_run_clean_format_job(...)` imports `clean_format.format_transcript` + `clean_format.write_deposition_docx`.
7. `clean_format/formatter.py` executes Anthropic cleanup using `CLEAN_FORMAT_SYSTEM_PROMPT` from `clean_format/prompt.py`.
8. `clean_format/docx_writer.py` writes final deposition DOCX from the cleaned text.

## 2) Transcript-changing files: wiring + execution prompt

| File | Wired from | Immediate execution prompt | What triggers it |
|---|---|---|---|
| `pipeline/transcriber.py` | `core/job_runner.py` | `transcribe_chunk(...)` | Start Transcription run enters chunk transcription stage. |
| `pipeline/assembler.py` | `core/job_runner.py` | `reassemble_chunks(...)` | Chunk transcription completes and results are merged. |
| `pipeline/exporter.py` | `core/job_runner.py` path that writes transcript artifacts | export/write function call | End-of-run artifact save step. |
| `clean_format/prompt.py` | `clean_format/formatter.py` import | `CLEAN_FORMAT_SYSTEM_PROMPT` constant use | Clean-format phase starts after successful transcription flow. |
| `clean_format/formatter.py` | `ui/tab_transcribe.py` (`_run_clean_format_job`) | `format_transcript(raw_text, case_meta)` | `_start_clean_format(...)` launches background clean-format worker. |
| `clean_format/docx_writer.py` | `ui/tab_transcribe.py` (`_run_clean_format_job`) | `write_deposition_docx(...)` | `format_transcript(...)` returns formatted text. |
| `core/corrections_runner.py` | `ui/tab_transcribe.py` (`_run_corrections`) | `run_corrections(target_path)` | User clicks **Run Corrections** utility button (manual path). |
| `spec_engine/corrections.py` | `core/corrections_runner.py` via `spec_engine.processor.process_blocks(...)` | correction pass in processor chain | `run_corrections(...)` invoked. |
| `spec_engine/qa_fixer.py` | `spec_engine.processor.process_blocks(...)` chain | Q/A enforcement pass | `run_corrections(...)` invoked. |
| `pipeline/pyannote_diarizer.py` | Not wired in active path | N/A (inactive) | No active runtime trigger; module documents dead-code status. |

## 3) Runtime trigger map by user action

### A. Start Transcription (primary path)
- UI event: `start_transcription()` in `ui/tab_transcribe.py`.
- Downstream trigger sequence:
  - `core/job_runner.py` transcription orchestration.
  - `pipeline/transcriber.py` text/speaker shaping during Deepgram processing.
  - `pipeline/assembler.py` deterministic chunk merge + speaker normalization.
  - clean-format kickoff via `_start_clean_format()`.
  - `clean_format/formatter.py` model cleanup pass using prompt in `clean_format/prompt.py`.
  - `clean_format/docx_writer.py` final DOCX formatting output.

### B. Run Corrections (manual utility path)
- UI event: `_run_corrections()` button handler in `ui/tab_transcribe.py`.
- Downstream trigger sequence:
  - `core/corrections_runner.run_corrections(...)` on selected `_raw.json`.
  - `spec_engine` processing pipeline, including deterministic text corrections and Q/A structure enforcement.
- Output: writes `{base}_corrected.txt` sidecar; does not replace raw source JSON.

## 4) Prompt/execution conditions per stage

- **Transcriber stage** executes only when audio preprocessing/chunking returns work items for job runner.
- **Assembler stage** executes when one or more chunk results are available.
- **Clean-format stage** executes only after upstream transcription result is marked complete and `_start_clean_format(...)` is invoked.
- **Deterministic corrections stage** executes only on explicit user action (**Run Corrections** button), not automatically in the primary path.
- **Pyannote relabel stage** has no active execution path in current wiring.

## 5) Verification of the specific corrections listed in chat logs

The following checks compare the listed corrections to what is actually implemented in repository code.

### Implemented in code (generic/rule-based)

- Speaker-label normalization from `COURT REPORTER` / `VIDEOGRAPHER` to `THE REPORTER` / `THE VIDEOGRAPHER` is implemented in clean-format prompt/rules.
- Defense-attorney intro spoken under videographer label ("Billy Dunnell ...") has explicit relabel handling in `clean_format/formatter.py`.
- Q/A line formatting (`Q.\t...`, `A.\t...`) is implemented in clean-format prompt/output rules and DOCX parsing logic.
- Cause-number normalization support exists in intake/parsing expectations and tests (hyphenated `2024-CI-...` pattern examples).

### Not implemented as explicit case-specific deterministic rules

- Case-specific speaker corrections for named utterances in the pasted transcripts (e.g., "Brett Gamblin ...", "So that was kind of cool.", "Yes, sir." as witness, "peer reviewed" question reassignment) are **not** present as explicit hardcoded rules in repository files.
- Case-specific spelling correction for "Dixie Arriaga" variants is **not** present as an explicit deterministic rule.
- A deterministic global rule forcing "Texas Rule of Civil Procedure" -> "Texas Rules of Civil Procedure" is **not** present.

### Not implemented in current DOCX writer as stated in those chat logs

- The current `clean_format/docx_writer.py` does not implement the full set of claimed UFM-layout mechanics from those logs (e.g., explicit 25-line-per-page enforcement logic, line-number XML controls, page border/header page-number orchestration described in the narrative).

Conclusion: the repository includes **general** cleanup and normalization mechanisms, but most of the long pasted narrative reflects **case-by-case output decisions**, not fully codified deterministic rules in these files.

## 6) Requested pipeline file review (2026-05-11)

Review result for the nine files explicitly requested:

- **Keep as transcript-changing in reports:**
  - `pipeline/transcriber.py` (Deepgram flags + utterance/speaker shaping)
  - `pipeline/assembler.py` (utterance normalization/merge/remap)
  - `pipeline/exporter.py` (selects corrected-vs-raw transcript text output)
- **Keep as pipeline dependencies but not transcript-text correction files:**
  - `pipeline/audio_combiner.py` (audio-file combine only)
  - `pipeline/preprocessor.py` (audio normalization only)
  - `pipeline/chunker.py` (audio splitting only)
  - `pipeline/audio_quality.py` (audio diagnostics only)
  - `pipeline/vad_trimmer.py` (silence trimming only)
- **Keep marked inactive/dead path:**
  - `pipeline/pyannote_diarizer.py` (explicitly documented dead code)

Recommendation: no code changes needed in these files based on this review. For documentation clarity, retain current transcript-change scope and ensure these six audio-only files are explicitly called out as excluded from text-correction logic.

## 7) Scripts folder review for requested probe/repro files (2026-05-11)

Requested paths reviewed:
- `scripts/probe_merged_utterances.py`
- `scripts/probe_qa_failures.py`
- `scripts/probe_residual_qa_failures.py`
- `scripts/repro_minimize_bug.py`

Findings:
- Only `scripts/probe_residual_qa_failures.py` exists in the repository.
- The other three requested script files are currently missing.

Improvement recommendations:
1. If those three scripts were intentionally removed, add a short `scripts/README.md` changelog note with replacements (or explicit "removed/no replacement") to avoid confusion.
2. If they are still expected operational tools, restore them (or add thin wrapper aliases) so historical runbooks/notes continue to work.
3. For `probe_residual_qa_failures.py`, avoid importing underscored internals from `core.corrections_runner` (`_adapt_saved_utterances`, `_select_utterance_source`) by promoting stable public helpers; this reduces break risk on refactors.
4. Optionally add `argparse` flags for max samples/context so operators do not edit constants in file.

Current-state recommendation: no urgent runtime pipeline changes needed. The primary gap is script discoverability/continuity, not production transcript flow.

## 8) Follow-up implementation (2026-05-12)

To address script continuity concerns, the previously missing script entry points were added:
- `scripts/probe_qa_failures.py` (compatibility wrapper to residual QA probe)
- `scripts/probe_merged_utterances.py` (counts/samples merged-utterance candidates)
- `scripts/repro_minimize_bug.py` (builds minimized raw fixture around consecutive-Q failure contexts)

Result: historical script names are now resolvable again, and reproducibility tooling coverage is improved without touching production runtime paths.

## 9) Spec-engine file review (2026-05-12)

Requested files reviewed:
- `spec_engine/block_builder.py`
- `spec_engine/classifier.py`
- `spec_engine/corrections.py`
- `spec_engine/emitter.py`
- `spec_engine/models.py`
- `spec_engine/processor.py`
- `spec_engine/qa_fixer.py`
- `spec_engine/speaker_mapper.py`
- `spec_engine/ufm_rules.py`
- `spec_engine/ufm_rules_backup.py`
- `spec_engine/utterance_splitter.py`

### Keep as-is (no urgent production change)
- `models.py`, `processor.py`, `qa_fixer.py`, `corrections.py`, `emitter.py` are coherent with the deterministic enforcement chain and appear actively used.
- `block_builder.py` fallback behavior remains compatible with current `core/corrections_runner` adapters.

### Improvements recommended (targeted, low-risk)
1. **Deprecate or remove duplicate backup rule file**
   - `ufm_rules_backup.py` duplicates `ufm_rules.py` behavior and risks drift/confusion.
2. **Harden script-facing API boundaries**
   - New diagnostic scripts currently import underscored helpers from `core.corrections_runner`; consider public helpers in `spec_engine` or `core` for stable probing interfaces.
3. **Reduce duplicated question-word constants coupling**
   - `utterance_splitter.py` imports `QUESTION_WORDS` and `STANDALONE_ANSWER_WORDS` from `qa_fixer.py`; consider a shared constants module to avoid cross-module coupling.
4. **Add regression tests for speaker smoothing edge-cases**
   - `speaker_mapper.smooth_speaker_sequence` reassigns short middle turns (<6 words); add explicit tests to guard witness short-answer integrity.
5. **Classify `utterance_splitter` AI path status in docs**
   - Top docstring says detection-only foundation, but file includes AI-splitting implementation; clarify active/inactive status to reduce operator ambiguity.

### Current recommendation
No immediate refactor is required for production stability. Prioritize documentation cleanup (`ufm_rules_backup.py` status, splitter status) and boundary hardening for probe tooling.
