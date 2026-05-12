# Phase 2A — Known Limitations and Long-Term Direction

**Status:** Shipped 2026-05-12 (commits `91e8282` Phase 2A wiring, `887ec98` Phase 2A.1 prompt fix, `4215f9b` threshold calibration).

This document records what Phase 2A delivers, what it does *not* deliver, and the direction the architecture is intended to move in. Read this before designing Phase 2B or any successor work that touches `clean_format/prompt.py` or `clean_format/low_confidence_markers.py`.

## What Phase 2A delivers

1. **The 33-entry `confirmed_spellings` dict reaches the Anthropic cleanup prompt.** Previously persisted in `source_docs/job_config.json` and never read by the active path; now attached to `case_meta` in `_build_clean_format_case_meta` at `ui/tab_transcribe.py:3598-3610` and serialized into the prompt user message by `_case_meta_for_prompt` at `clean_format/formatter.py:95-117`.

2. **The 84-entry `deepgram_keyterms` list reaches the same prompt.** Same mechanism, in the same `case_meta` slice.

3. **The cleanup prompt has explicit testimony-preservation guardrails.** Added in `clean_format/prompt.py` lines 42–79. The model is instructed to apply `confirmed_spellings` corrections only when context is unambiguous, to emit `[SCOPIST: FLAG ...]` annotations when uncertain rather than silently rewriting, and to never alter testimony content (quoted speech, contrasted forms, spelled-aloud passages).

4. **A `MARKER INVIOLABILITY` subsection precedes the reference-data instructions.** Added in `clean_format/prompt.py` lines 48–78. Tells the model that `‹LC:...›` markers are Deepgram audio-confidence indicators from a separate upstream system, must be preserved character-for-character, and are not part of the correction-workflow scaffolding.

5. **Real confirmed-spelling corrections fire on real cases.** Verified on Cavazos: `‹LC:Mister› Cavazos → Mr. Cavazos` applies 33 times in a single chunk; `‹LC:cause› number → Cause Number` applies once via the keyterm path.

6. **The drift safety net (`MarkerDriftError`) is calibrated to 10%.** Catches catastrophic regressions (model ignoring the marker preservation rule wholesale) while accepting the model's normal run-to-run interpretation variance.

## What Phase 2A does NOT deliver

1. **Stable marker preservation across all runs.** Observed marker-drop rates across 7 Cavazos runs span 0% to 85.1%, on identical inputs. The cleanup model's interpretation of the prompt is stochastically variable. The 10% threshold is the operational compromise; it is not a guarantee that any given run will preserve every marker.

2. **Complete elimination of marker stripping.** Per `docs/audits/PHASE_2A_CORRECTION_APPLICATION.md`, on a typical run roughly 6–10 LC markers are stripped from "well-formed" tokens like `David`, `Jr`, `Mr`, `Animal`, `That`. The underlying text is preserved (so the transcript content is correct), but the yellow-highlight signal for those specific tokens is lost. The MARKER INVIOLABILITY rule reduced this from the catastrophic levels seen in the original Phase 2A run, but did not zero it out.

3. **Per-token traceability of which corrections were applied.** When `‹LC:Mister›` becomes `Mr.`, the resulting DOCX does not record that a correction was made, what the original form was, or whether the `confirmed_spellings` dict drove the change. Miah cannot tell from the output document whether `Mr.` is original or corrected. This is the most significant limitation for legal-defensibility purposes.

4. **`[SCOPIST: FLAG ...]` annotations in their own surface.** The annotations the model emits land inline in the DOCX body text, not in a separate review queue or comment layer. This was flagged in `docs/audits/CASE_MUTATION_REPORT.md` and remains unaddressed.

5. **Q/A paragraph balance.** The structural classifier in the cleanup pass produced 108 Q / 55 A / 125 three-tab non-QA on the Cavazos smoke run, vs. a pre-Phase-2A baseline of 106 Q / 102 A. The witness's answers are being misclassified as non-QA paragraphs. Phase 2A did not address this; flagged in `CASE_MUTATION_REPORT.md`.

## Failure modes and their handling

| Failure | Frequency observed | Detected by | Handled how |
|---|---|---|---|
| Catastrophic marker stripping (>10% drift) | 1 of 7 runs (the 85.1% outlier) | `validate_marker_round_trip` in `clean_format/low_confidence_markers.py` | Raises `MarkerDriftError`; caught at the UI boundary in `_run_clean_format_job`; popup surfaced to user via `_on_clean_format_done`; no DOCX produced |
| Moderate marker stripping (0–10% drift) | 5 of 7 runs | `marker_drift_stats` WARNING log | Logged but not surfaced to user; DOCX produced with reduced highlight coverage |
| Marker stripped on a `confirmed_spellings`-corrected token | always when correction fires | Not detected automatically | Acceptable side effect — the underlying text is correctly corrected; the yellow highlight is lost on that one token |
| Marker stripped on a "well-formed" token without correction | observed 4–8 times per run | Not detected automatically | Yellow highlight lost on that token; underlying text preserved |
| `SCOPIST: FLAG` substitution for a LC marker | observed once per run on opening word | Not detected automatically | Inline annotation appears in DOCX body; scopist sees the flag |
| Silent drop of trimmed closing remarks | observed on Cavazos | Not detected | Affects only deposition-boundary transitional content the model judged extraneous |

## Long-term direction

The fundamental architectural tension Phase 2A exposed: **inline markers in cleanup-pass input text are an unstable channel for provenance.** The Anthropic cleanup model is trained to produce natural language output and views markers as scaffolding to remove. Telling it not to via prompt instructions works imperfectly because the instruction competes with the model's normal text-cleanup behavior.

The intended Phase 2B (planned, not scheduled) pivot:

- **Move provenance metadata out of the inline text stream and into a structured layer.** The cleanup model produces clean text without markers; a separate post-processing step takes the model's output and the original Deepgram word array and re-derives which output tokens correspond to which Deepgram words. Yellow highlights are computed from the alignment, not from in-stream markers.
- **Replace MARKER_ONLY_DROPPED with NEVER_INJECTED.** If markers are never in the input, the model can't strip them. The cleanup pass operates on plain text; provenance lives alongside it.
- **Capture per-token correction provenance explicitly.** A side-channel that records, for each output token: source Deepgram word index, confidence, whether a `confirmed_spellings` correction was applied, what the original form was. This is the foundation for the "review queue" surface that `docs/audits/CASE_MUTATION_REPORT.md` referenced.

Phase 2B is downstream of three short-horizon items on the current list:

1. `[SCOPIST: FLAG ...]` body-text emission cleanup
2. Q/A classification ratio improvement
3. Dead-module hygiene

Phase 2B should not begin until those land. The provenance pivot is non-trivial (estimated multi-day work, including word-alignment design, post-processing pipeline, DOCX writer updates, regression tests on real cases) and benefits from a clean baseline.

## What this means for users today

Miah can use the Transcribe tab as currently shipped. The output DOCX is testimony-accurate in content; yellow highlights are present where Deepgram had per-word audio confidence below 0.85, *minus* approximately 6–10 specific tokens per case (typically proper-noun-adjacent or short common words) that the cleanup model strips. The `confirmed_spellings` dict actively corrects mis-heard variants where they appear in audio. The `MarkerDriftError` popup surfaces only on catastrophic runs (~1 in 7); when it fires, the safe action is to re-run the job, which will likely produce a clean result given the model's variance.

For legally-sensitive uses where every Deepgram low-confidence token must be reviewed: Phase 2A is *necessary but not sufficient*. The provenance pivot in Phase 2B is the upgrade path.
