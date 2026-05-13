# Transcript Change Surface Report (2026-05-09)

## Scope and method

This report inventories files that **change transcript content, structure, labels, or final formatting** for accuracy/compliance outcomes.

Search + review method:
- `rg -n "clean|format|correction|correct|normalize|stutter|filler|Q\.|A\.|speaker|rewrite|fix" clean_format core spec_engine pipeline ui`
- Manual inspection of candidate files.

## A) Active clean-format path (current production path)

1. `clean_format/formatter.py`
   - Runs Anthropic cleanup pass and applies deterministic post-processing to normalized output text.
   - Transcript-altering behaviors include speaker relabeling, punctuation/spacing normalization, role-specific formatting (`Q.`/`A.`/label blocks), and body-text normalization helpers.

2. `clean_format/prompt.py`
   - Defines the cleanup instructions that drive transcript transformations for filler removal, stutter smoothing, term corrections, Q/A conversion, label normalization, and spacing/interruptions policy.

3. `clean_format/docx_writer.py`
   - Converts formatted plain text into deposition DOCX structures, parses transcript blocks, merges consecutive same-speaker blocks, and normalizes sentence spacing while writing output.

## B) Deterministic correction pipeline (present in repo; separate from clean-format prompt path)

4. `core/corrections_runner.py`
   - Orchestrates deterministic correction run from raw JSON to corrected transcript text using `spec_engine`.

5. `spec_engine/corrections.py`
   - Applies deterministic text corrections (spacing, sentence starts, stutters, ellipses, dash handling, punctuation endings, proper noun replacements, legal dictionary + keyterm driven normalization).

6. `spec_engine/qa_fixer.py`
   - Enforces strict Q/A sequencing and re-types blocks into `question`/`answer` using deterministic heuristics and speaker context.

## C) Upstream transcript-structure transforms (before clean-format)

7. `pipeline/transcriber.py`
   - Performs speaker smoothing, utterance merge logic, duplicate/skipped glitch handling, and request parameters that influence transcription formatting output (`smart_format`, filler handling, etc.).

8. `pipeline/assembler.py`
   - Deterministically normalizes/merges utterances, filters speaker-flip glitches, de-duplicates overlap, remaps speaker IDs across chunks, and attaches speaker labels.

9. `pipeline/exporter.py`
   - Chooses whether to emit corrected transcript text or raw assembled text and writes final text files used downstream.

## D) Explicitly non-active / inactive transcript relabel path

10. `pipeline/pyannote_diarizer.py`
   - Contains speaker reassignment functions that would alter transcript speaker labels, but file header states this path is dead code and not wired into active flow.

## E) Notes

- This inventory focuses on **transcript-changing** code, not purely UI or audio-container formatting.
- In current architecture docs, `clean_format/formatter.py` is identified as the full transcript cleanup pipeline; files in sections B/C remain relevant to deterministic and upstream transcript-shaping behavior present in the repository.
