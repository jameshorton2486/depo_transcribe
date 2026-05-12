# ACTIVE_PATH_AUDIT

**Case folder referenced for routing checks:** `C:\Users\james\Depositions\2026\May\2026CV00803\cavazos_gilberto`

This audit traces the active code path from "user clicks **Start Transcription**" through to "DOCX is written" and labels every module that participates. Coverage is derived from `git grep` of import sites across `pipeline/`, `clean_format/`, `core/`, `ui/`, `spec_engine/`, and `ufm_engine/`.

Status legend:

- **WIRED** — called in the live Start-Transcription path.
- **OFFLINE** — exists, called only by `core/*_runner.py` CLI tools or by the separate "Run Corrections" button.
- **DEAD** — defined but not imported by any non-test file.
- **PARTIAL** — referenced but only along an error/fallback branch.
- **DUPLICATED** — overlaps another module's responsibility.
- **BYPASSED** — wired but a flag/condition disables it at runtime.

## Key Questions

**Q1. Is `spec_engine` reachable from the Start Transcription button at all?**
No. `core/job_runner.py` (the function `run_transcription_job` invoked by the Start-Transcription path) imports only from `pipeline.*` and `core.*` (`core/job_runner.py:10-141`). No `from spec_engine` or `import spec_engine` appears in the imports of `core/job_runner.py`, `ui/tab_transcribe.py::start_transcription` (line 3329), or `clean_format/formatter.py`. `spec_engine` is reachable from the UI only via the separate **Run Corrections** button (`ui/tab_transcribe.py:4297` → `from core.corrections_runner import run_corrections`).

**Q2. Where does `confirmed_spellings` reach during a Start Transcription run, and where does it stop reaching?**
It reaches: `core/intake_parser.py` (built at lines 463 and 811), `core/case_vocab.py:456-464` (extracted to keyterm-and-spelling pair), `ui/tab_transcribe.py:3162, 3180, 3484` (held on the tab as `self._confirmed_spellings` and passed into `run_transcription_job`), and `core/job_runner.py:83, 411` (received as a parameter and **persisted to `job_config.json`** via `merge_and_save`).

It stops reaching at `merge_and_save`. The dict is **never read back** by the Start-Transcription branch after that. Specifically, `clean_format/formatter.py` does not import or reference `confirmed_spellings`; the function `_case_meta_for_prompt` at `clean_format/formatter.py:95-117` whitelists 15 keys to send to Anthropic, and `confirmed_spellings` is not among them.

The dict IS read back by the offline `core/corrections_runner.py:71-97` and applied via `spec_engine/corrections.py::apply_proper_noun_corrections` — but only when the Run-Corrections button is pressed, not in the Start-Transcription flow.

**Q3. Is `apply_proper_noun_corrections` called in the live transcribe path? (yes/no with evidence)**
No. Grep for `apply_proper_noun_corrections` returns five files: `spec_engine/corrections.py:135` (the definition), `spec_engine/corrections.py:249` (the only call site — inside `apply_corrections`, which is itself part of `spec_engine`), and three test files. No call site in `pipeline/`, `clean_format/`, `core/job_runner.py`, or `ui/tab_transcribe.py::_run_clean_format_job`. The live path bypasses it entirely.

**Q4. Does `pipeline/exporter.py` participate in the live path or is it a separate utility?**
Neither. `pipeline/exporter.py` is **DEAD** in the production sense. The only inbound import is from its own test file (`pipeline/tests/test_exporter.py:6`); no production module imports `from pipeline.exporter` or `from pipeline import exporter`. Its public functions `save_raw_deepgram_output` and `export_results` (`pipeline/exporter.py:27, 36`) are not called from `core/job_runner.py`, `pipeline/assembler.py`, or anywhere else outside of tests. Note: `pipeline/assembler.py` (which `exporter.py` itself imports) IS wired into the live path via `core/job_runner.py:122`; `pipeline/assembler` lives, `pipeline/exporter` does not.

**Q5. Does `pipeline/pyannote_diarizer.py` have any active call site?**
No. Grep returns zero non-self imports across the codebase. The module is explicitly documented as dead code by an inline comment at `pipeline/preprocessor.py:44`: *"active path despite the dead module at pipeline/pyannote_diarizer.py."* DEAD.

**Q6. Does `ufm_engine` produce output for the Transcribe tab, the Templates tab, both, or neither?**
Templates tab only. Production imports of `ufm_engine.populator.populate` and `ufm_engine.post_processor.format_box` appear at `ui/tab_templates.py:666, 721`. No production imports appear in `ui/tab_transcribe.py`, `core/job_runner.py`, or `clean_format/`. The Transcribe tab's DOCX is produced exclusively by `clean_format/docx_writer.py::write_deposition_docx`.

**Q7. Which `spec_engine` modules have any reachable call from the UI?**
All of `spec_engine`'s public modules are reachable via one of two button-driven routes:

- **Run Corrections** button (`ui/tab_transcribe.py:1830` → method `_run_corrections` at line 4244 → `from core.corrections_runner import run_corrections` at line 4297) calls `core/corrections_runner.py::_run_corrections`, which imports `spec_engine.block_builder.build_blocks` (line 19) and `spec_engine.processor.process_blocks` (line 20). `process_blocks` in turn pulls in `spec_engine.classifier`, `spec_engine.qa_fixer`, `spec_engine.corrections`, `spec_engine.speaker_mapper`, `spec_engine.emitter`.
- **Resolve Merged Utterances** button (handled in `core/utterance_splitter_runner.py:21` → `spec_engine.utterance_splitter`).

`spec_engine/models.py` is shared dataclass infrastructure. `spec_engine/ufm_rules.py` and `spec_engine/ufm_rules_backup.py`: see the table below.

---

## Module-by-Module Table

| Module / File | Active path role | Test coverage | Status |
|---|---|---|---|
| **pipeline/** | | | |
| `pipeline/__init__.py` | Package marker | n/a | WIRED |
| `pipeline/preprocessor.py` | Normalize/decode audio | `pipeline/tests/test_preprocessor.py` | WIRED (`core/job_runner.py:113`) |
| `pipeline/chunker.py` | Split long audio into chunks | `pipeline/tests/test_chunker.py` | WIRED (`core/job_runner.py:120, 256, 447`) |
| `pipeline/transcriber.py` | Call Deepgram per chunk; trim keyterms | `pipeline/tests/test_transcriber.py` | WIRED (`core/job_runner.py:121, 141`) |
| `pipeline/assembler.py` | Reassemble chunked output | `pipeline/tests/test_assembler.py` | WIRED (`core/job_runner.py:122`) |
| `pipeline/audio_quality.py` | Detect audio tier | (no direct test) | WIRED (`core/job_runner.py:123`) |
| `pipeline/vad_trimmer.py` | Voice-activity silence trim | (no direct test) | WIRED (`core/job_runner.py:124`) |
| `pipeline/audio_combiner.py` | Merge multiple source files | `pipeline/tests/test_audio_combiner.py` | WIRED via `ui/dialog_combine_audio.py:36` (Combine Audio dialog) |
| `pipeline/exporter.py` | (intent: write Deepgram outputs) | `pipeline/tests/test_exporter.py` | **DEAD** — only its own test imports it; production writes happen inline in `core/job_runner.py` |
| `pipeline/pyannote_diarizer.py` | (intent: pyannote diarization) | (none) | **DEAD** — documented dead by `pipeline/preprocessor.py:44` |
| **clean_format/** | | | |
| `clean_format/__init__.py` | Re-exports `format_transcript`, `write_deposition_docx`, `build_case_meta_from_ufm` | n/a | WIRED |
| `clean_format/formatter.py` | Anthropic cleanup orchestrator | `clean_format/tests/test_formatter.py`, `test_speaker_identification.py`, `test_production_wiring.py`, `test_low_confidence_markers.py` | WIRED (`ui/tab_transcribe.py:3615, 3616, 3617`) |
| `clean_format/prompt.py` | The strict-verbatim system prompt | (covered indirectly by formatter tests) | WIRED via `clean_format/formatter.py:12` |
| `clean_format/low_confidence_markers.py` | Inject `‹LC:...›` markers + `MarkerDriftError` | `clean_format/tests/test_low_confidence_markers.py`, `ui/tests/test_clean_format_error_handling.py` | WIRED via `clean_format/formatter.py:13` and `clean_format/docx_writer.py:17` |
| `clean_format/docx_writer.py` | Render DOCX with yellow-highlight runs | `clean_format/tests/test_docx_writer.py`, `test_docx_low_confidence_highlight.py`, `test_filename_helpers.py` | WIRED (`ui/tab_transcribe.py:3615`) |
| `clean_format/__main__.py` | CLI entry: `python -m clean_format <case_dir>` | (no direct test) | OFFLINE — alternate entry not used by the Start-Transcription button |
| **core/** | | | |
| `core/__init__.py` | Package marker | n/a | WIRED |
| `core/config.py` | Shadow / passthrough to top-level `config.py` | (none) | WIRED (used by `app_logging`) |
| `core/file_manager.py` | Create `{year}/{month}/{cause}/{name}/` folders | `core/tests/test_file_manager.py` | WIRED (`core/job_runner.py:17`) |
| `core/job_runner.py` | Background transcription orchestration | `core/tests/test_job_runner.py` | WIRED — invoked by `ui/tab_transcribe.py::start_transcription` |
| `core/job_config_manager.py` | Read/write `job_config.json` (merge semantics) | `core/tests/test_job_config_manager.py` | WIRED via `core/job_runner.py` (uses `merge_and_save`) |
| `core/pdf_extractor.py` | PDF→text for NOD intake | `core/tests/test_pdf_extractor.py` | WIRED (intake side, before Start Transcription) |
| `core/intake_parser.py` | AI-assisted intake parsing → `confirmed_spellings`, `keyterms`, `ufm_fields` | `core/tests/test_intake_parser.py` | WIRED (intake side) |
| `core/source_docs_extractor.py` | Source-docs collection | `core/tests/test_source_docs_extractor.py` | WIRED (intake side) |
| `core/case_vocab.py` | Reduce intake structures to spelling/keyterm pairs | (no direct test) | WIRED (`ui/tab_transcribe.py` intake handoff) |
| `core/keyterm_extractor.py` | Build Deepgram keyterm list | `core/tests/test_keyterm_extractor.py` | WIRED (intake side; result flows into `deepgram_keyterms`) |
| `core/ufm_field_mapper.py` | Map intake → saved `ufm_fields` | `core/tests/test_ufm_field_mapper.py` | WIRED (intake side) |
| `core/vlc_player.py` | VLC playback wrapper for review surface | (none) | WIRED via `ui/tab_transcribe.py` (Word Review panel) |
| `core/word_review.py` | `WordReviewItem` dataclass | `core/tests/test_word_review.py` | WIRED (`ui/tab_transcribe.py:1285`) |
| `core/corrections_runner.py` | Run-Corrections CLI/UI entry | `core/tests/test_corrections_runner.py` | OFFLINE — Run-Corrections button only (`ui/tab_transcribe.py:4297`) |
| `core/utterance_splitter_runner.py` | Resolve-Merged-Utterances entry | `core/tests/test_utterance_splitter_runner.py` | OFFLINE — Resolve Merged Utterances button only |
| `core/app_logging.py` | Logger factory | `core/tests/test_app_logging.py` | WIRED everywhere |
| **ui/** | | | |
| `ui/__init__.py` | Package marker | n/a | WIRED |
| `ui/app_window.py` | App shell with Transcribe + Templates tabs | (smoke covered by `ui/tests/test_txt_format.py` indirectly) | WIRED (`app.py`) |
| `ui/tab_transcribe.py` | Transcribe tab (Start Transcription, Run Corrections, Word Review, View Document) | `ui/tests/test_txt_format.py`, `test_speaker_id_sort.py`, `test_clean_format_error_handling.py` | WIRED |
| `ui/tab_templates.py` | Templates tab (UFM-template fill) | (covered by `tests/ufm_engine/`) | WIRED (separate tab) |
| `ui/dialog_combine_audio.py` | Multi-file combine dialog | (none direct) | WIRED via Combine Audio button |
| `ui/_components.py` | Shared UI constants | (none) | WIRED |
| **spec_engine/** | | | |
| `spec_engine/__init__.py` | Package marker | n/a | OFFLINE (only via Run-Corrections button) |
| `spec_engine/models.py` | `TranscriptBlock`, `TranscriptWord` | `spec_engine/tests/test_word_carry.py`, `test_word_carry_b1.py` | OFFLINE |
| `spec_engine/block_builder.py` | Speaker-block builder | (covered by classifier/qa_fixer/corrections tests) | OFFLINE (`core/corrections_runner.py:19`) |
| `spec_engine/classifier.py` | Block-type classification | `spec_engine/tests/test_classifier.py` | OFFLINE |
| `spec_engine/qa_fixer.py` | Q/A sequence enforcement | `spec_engine/tests/test_qa_fixer.py`, `test_qa_fixer_tightened.py` | OFFLINE |
| `spec_engine/corrections.py` | Apply Morson's rules + proper-noun corrections | `spec_engine/tests/test_corrections.py`, `test_corrections_step_a.py`, `test_morsons_rules.py`, `test_proper_nouns.py`, `test_word_carry.py` | OFFLINE — **the only consumer of `confirmed_spellings` in the codebase**, but not on the Start-Transcription path |
| `spec_engine/speaker_mapper.py` | Speaker label normalization | `spec_engine/tests/test_speaker_smoothing.py` | OFFLINE |
| `spec_engine/emitter.py` | Output text emission | `spec_engine/tests/test_emitter.py` | OFFLINE |
| `spec_engine/utterance_splitter.py` | Merged-utterance splitting | `spec_engine/tests/test_utterance_splitter.py`, `test_utterance_splitter_ai.py` | OFFLINE (`core/utterance_splitter_runner.py:21`) |
| `spec_engine/processor.py` | Top-level orchestrator for the corrections pipeline | (covered indirectly) | OFFLINE (`core/corrections_runner.py:20`) |
| `spec_engine/ufm_rules.py` | UFM rule definitions | (none direct) | OFFLINE |
| `spec_engine/ufm_rules_backup.py` | Backup copy of UFM rules | (none) | **DUPLICATED** with `spec_engine/ufm_rules.py` — backup-file convention, no inbound imports |
| **ufm_engine/** | | | |
| `ufm_engine/__init__.py` | Package marker | n/a | WIRED (Templates tab) |
| `ufm_engine/templates/__init__.py` | Templates package | n/a | WIRED |
| `ufm_engine/generator/build_templates.py` | Build/index templates | (none direct) | WIRED |
| `ufm_engine/populator/populate.py` | Populate templates with case data | `tests/ufm_engine/test_populator.py`, `test_end_to_end.py` | WIRED (`ui/tab_templates.py:666`) |
| `ufm_engine/post_processor/format_box.py` | Final formatting pass | `tests/ufm_engine/test_post_processor.py`, etc. | WIRED (`ui/tab_templates.py:721`) |

## Call Graph for the Start-Transcription Path (live, this case)

```
ui/tab_transcribe.py::start_transcription   (line 3329)
   │
   ▼  spawns a background thread
core/job_runner.py::run_transcription_job   (called inside that thread)
   │  imports: pipeline.preprocessor, pipeline.chunker, pipeline.transcriber,
   │           pipeline.assembler, pipeline.audio_quality, pipeline.vad_trimmer
   │
   ├─► pipeline.preprocessor.preprocess_audio   (line 113-119)
   ├─► pipeline.chunker.chunk_audio              (line 120)
   ├─► pipeline.transcriber.transcribe_chunk     (line 121, per chunk; keyterms sent here)
   ├─► pipeline.assembler.reassemble_chunks      (line 122)
   ├─► pipeline.transcriber.trim_keyterms_for_deepgram (line 141)
   ├─► merge_and_save  (job_config_manager) ─────► persists confirmed_spellings to job_config.json
   │                                                  (END OF LINE for confirmed_spellings)
   ▼
   returns result dict to ui/tab_transcribe.py
   │
   ▼  callback _on_transcription_done → calls _run_clean_format_job (line 3613)
ui/tab_transcribe.py::_run_clean_format_job
   │  imports (locally, lines 3615-3617):
   │     clean_format.format_transcript
   │     clean_format.write_deposition_docx
   │     clean_format.formatter.load_deepgram_words_from_json
   │     clean_format.low_confidence_markers.MarkerDriftError
   │
   ├─► clean_format.formatter.load_deepgram_words_from_json   (3637)
   ├─► clean_format.formatter.format_transcript               (3640)
   │      │
   │      ├─► _chunk_transcript_text  (clean_format/formatter.py)
   │      ├─► inject_markers          (clean_format/low_confidence_markers.py)
   │      ├─► Anthropic API call      (per chunk; system prompt = clean_format/prompt.py)
   │      ├─► validate_marker_round_trip  (raises MarkerDriftError if drift > 5% with floor)
   │      └─► _postprocess_formatted_text
   │
   └─► clean_format.docx_writer.write_deposition_docx   (3652)
          │
          └─► split_into_runs (low_confidence_markers) → yellow <w:highlight w:val="yellow"/>
```

**What is NOT in this graph:**
- `spec_engine.*` — not called.
- `apply_proper_noun_corrections` — not called.
- `confirmed_spellings` post-persistence — not read.
- `pipeline.exporter.export_results` — not called.
- `pipeline.pyannote_diarizer` — not called.
- `ufm_engine.*` — not called (Templates tab only).

## Surprises Worth Naming

1. **`confirmed_spellings` flows through six modules and seven layers of code on the way to `job_config.json`, then is never read by the active path that produces the DOCX.** The intake-side investment exceeds the active-path consumption. The dict's only consumer is the Run-Corrections offline path.
2. **`pipeline/exporter.py` is dead but is tested.** `pipeline/tests/test_exporter.py` covers a module no production caller invokes. The intent suggested by the function names (`save_raw_deepgram_output`, `export_results`) matches what `core/job_runner.py` does inline — those responsibilities migrated into the orchestrator without removing the original module.
3. **`spec_engine/ufm_rules_backup.py` is a literal backup file** with the `_backup` naming convention. No inbound imports. DEAD by the same criterion as `pipeline/pyannote_diarizer.py`.
4. **`clean_format/__main__.py` is a CLI that doesn't work against real case folders without manual file staging.** It expects `raw_deepgram.txt`, `raw_deepgram.json`, and `case_meta.json` in the same directory, but a real case folder splits them between `case_root/` (case_meta) and `case_root/Deepgram/` (raw_*). Functional as an offline harness but not invokable on a real case as-is.
5. **The `[SCOPIST: FLAG ...]` annotations the cleanup pass emits in body text are not documented in `clean_format/prompt.py`** as required output. They appeared in the smoke run anyway (58 instances). Either the prompt has a section that produces them implicitly, or the model is learning the pattern from in-context examples. Worth re-reading the prompt to confirm.
