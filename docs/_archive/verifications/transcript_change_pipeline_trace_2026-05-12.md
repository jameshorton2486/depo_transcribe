# Transcript Change Pipeline Trace (2026-05-12)

## 1) End-to-end diagram (where transcript text is changed)

```text
[UI: ui/tab_transcribe.py::start_transcription]
  -> [core/job_runner.py]
      -> [pipeline/transcriber.py]      (Deepgram request + utterance/speaker shaping)
      -> [pipeline/assembler.py]        (merge/dedupe/remap speaker utterances)
      -> [pipeline/exporter.py]         (writes raw/assembled transcript outputs)
  -> [ui/tab_transcribe.py::_start_clean_format]
      -> [clean_format/formatter.py]    (model cleanup + deterministic post-processing)
          -> [clean_format/prompt.py]   (cleanup instructions driving transformations)
      -> [clean_format/docx_writer.py]  (final block parsing/merge + DOCX layout)

[Manual utility path]
[UI: ui/tab_transcribe.py::_run_corrections]
  -> [core/corrections_runner.py]
      -> [spec_engine/block_builder.py]
      -> [spec_engine/classifier.py]
      -> [spec_engine/corrections.py]
      -> [spec_engine/qa_fixer.py]
      -> [spec_engine/speaker_mapper.py]
      -> [spec_engine/emitter.py]
      -> writes *_corrected.txt
```

## 2) File-by-file trace (actual transcript-changing files)

### Primary runtime path

1. `pipeline/transcriber.py`
   - Sends chunks to Deepgram and performs deterministic utterance/speaker shaping (speaker-glitch smoothing, merge constraints, duplicate handling), which changes intermediate transcript structure.

2. `pipeline/assembler.py`
   - Reassembles chunk outputs; normalizes utterances, merges overlaps, de-duplicates, remaps cross-chunk speaker IDs, and builds speaker-labeled transcript text.

3. `pipeline/exporter.py`
   - Chooses corrected transcript text when provided (otherwise raw assembled transcript) and writes emitted transcript artifacts.

4. `clean_format/prompt.py`
   - Defines the instruction contract for cleanup transformations (filler/stutter handling, speaker-role normalization, Q/A conversion, punctuation/spacing conventions).

5. `clean_format/formatter.py`
   - Executes model-driven cleanup pass and deterministic post-processing (label normalization, body text normalization, Q/A + speaker line post-fixes).

6. `clean_format/docx_writer.py`
   - Converts formatted transcript text into final DOCX blocks, merges consecutive speaker blocks, and applies output formatting conventions used for deliverables.

### Manual deterministic corrections path

7. `core/corrections_runner.py`
   - Loads raw JSON and invokes deterministic `spec_engine` pipeline to produce corrected text sidecar output.

8. `spec_engine/block_builder.py`
   - Builds text blocks from utterance/paragraph sources for downstream deterministic classification.

9. `spec_engine/classifier.py`
   - Classifies blocks into question/answer/directive/oath/colloquy types that drive structural enforcement.

10. `spec_engine/corrections.py`
    - Applies deterministic text normalization and proper-noun correction maps (spacing, punctuation, stutter/ellipsis/dash handling, endings).

11. `spec_engine/qa_fixer.py`
    - Enforces Q/A sequence integrity and context-based re-typing rules for question vs answer structure.

12. `spec_engine/speaker_mapper.py`
    - Normalizes speaker labels and directive identity formatting; includes short-turn sequence smoothing that can reassign speaker labels.

13. `spec_engine/emitter.py`
    - Emits final deterministic text format (`\tQ.\t`, `\tA.\t`, grouped colloquy formatting, time/spacing normalization).

14. `spec_engine/processor.py`
    - Orchestrates deterministic stage order across classifier/corrections/qa_fixer/speaker_mapper/emitter.

15. `spec_engine/ufm_rules.py`
    - Shared UFM rule helpers used by classifier/validation semantics for Q/A recognition/format checks.

16. `spec_engine/utterance_splitter.py`
    - Detects merged multi-exchange utterances; also contains AI-splitting implementation components used by diagnostics/workflows.

### Explicitly non-active transcript relabel path

17. `pipeline/pyannote_diarizer.py`
    - Contains transcript-altering speaker realignment functions but is documented as dead/unwired in active production flow.

## 3) Files reviewed but excluded from transcript-text correction scope

These are pipeline support modules and do not directly perform transcript text correction logic:
- `pipeline/audio_combiner.py`
- `pipeline/audio_quality.py`
- `pipeline/chunker.py`
- `pipeline/preprocessor.py`
- `pipeline/vad_trimmer.py`

They affect audio preparation quality, which can indirectly affect ASR output quality, but they do not apply direct transcript text rewrite/correction rules.
