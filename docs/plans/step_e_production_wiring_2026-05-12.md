# Step E — Production Wiring

Steps A–D delivered the dormant infrastructure for verbatim correctness
and low-confidence yellow highlighting. Step E activates it: every
production call to ``format_transcript`` now passes Deepgram word-level
data so the yellow-highlight pipeline runs end-to-end.

## Scope

Files modified:

- ``clean_format/formatter.py`` — added ``load_deepgram_words_from_json``
  helper. Loads the ``words`` array from a ``raw_deepgram.json`` file,
  returning ``None`` for every degraded case (missing file, malformed
  JSON, no ``words`` key, empty list). Never raises.
- ``clean_format/__main__.py`` (CLI) — loads
  ``{case_dir}/raw_deepgram.json`` and passes ``deepgram_words`` to
  ``format_transcript``.
- ``ui/tab_transcribe.py`` (UI clean-format job) — loads
  ``{case_dir}/Deepgram/raw_deepgram.json`` (the canonical path
  ``core/job_runner.py`` writes) and passes ``deepgram_words`` to
  ``format_transcript``.

New files:

- ``clean_format/tests/fixtures/sample_raw_deepgram.json`` — synthetic
  Deepgram-shaped JSON with 16 words, two of which (Acebo, Cesar)
  carry confidence below the 0.85 threshold.
- ``clean_format/tests/test_production_wiring.py`` — 12 tests across
  2 classes:
  - ``TestLoadDeepgramWords`` — happy path plus the six degraded
    cases ``load_deepgram_words_from_json`` must handle silently.
  - ``TestEndToEndWiring`` — full pipeline integration with the
    fixture. Verifies marker injection from the JSON shape, that
    markers survive the round-trip, that the DOCX renders yellow
    highlights on the low-confidence tokens, and that missing /
    empty JSON degrades cleanly.

## Activation surface

| Caller | Previous | Step E |
|---|---|---|
| CLI (``python -m clean_format <case_dir>``) | ``format_transcript(raw_text, case_meta)`` | ``format_transcript(raw_text, case_meta, deepgram_words=load_deepgram_words_from_json(case_dir / 'raw_deepgram.json'))`` |
| UI (transcribe → clean-format button) | ``format_transcript(raw_text, case_meta)`` | ``format_transcript(raw_text, case_meta, deepgram_words=load_deepgram_words_from_json(case_dir / 'Deepgram' / 'raw_deepgram.json'))`` |

The path differs because the CLI takes a ``case_dir`` argument that
historically pointed at the directory holding the raw text files
directly, while ``core/job_runner.py`` writes the canonical JSON
inside a ``Deepgram/`` subfolder. Both layouts are supported by being
explicit in each call site.

## Degraded-path guarantees

When the JSON file is missing, malformed, or empty,
``load_deepgram_words_from_json`` returns ``None`` and
``format_transcript`` falls through to its pre-Step-C behavior —
identical text output, no markers injected, no yellow highlights.
The user sees the same DOCX they would have seen before any of the
Step A–D work; nothing breaks.

This is the same posture as Step C's validation policy: a missing
quality signal is preferred to a crashed pipeline.

## Test that catches the integration class of bug

``TestEndToEndWiring::test_full_pipeline_renders_yellow_highlights_in_docx``
is the load-bearing test. It exercises the full chain:

1. Load fixture JSON via ``load_deepgram_words_from_json``.
2. Build raw_text from the fixture's punctuated_word arrays.
3. Call ``format_transcript`` with the loaded words + a mocked
   Anthropic client that echoes the chunk back (simulating perfect
   marker preservation).
4. Pass the formatted text to ``build_deposition_document``.
5. Walk every paragraph's runs and collect text where
   ``run.font.highlight_color == WD_COLOR_INDEX.YELLOW``.
6. Assert ``"Acebo"`` and ``"Cesar"`` are in the yellow-run set.

A field-name mismatch between ``inject_markers``'s expectations
(``word``, ``start``, ``end``, ``confidence``) and the actual JSON
shape would fail this test at step 3. Any future Deepgram schema
drift will fail it loudly.

## Pending follow-ups (deferred — not part of Step E)

- **Tighten marker-drift validation to 5%/floor-of-5.** Step C's
  ``validate_marker_round_trip`` currently logs every drop without
  raising. The agreed policy is: when ``input_count >= 5`` and
  ``dropped / input_count > 0.05``, raise; otherwise log. This catches
  systematic prompt-instruction failures while tolerating one or two
  drops per chunk. Tracked as task #4.
- **Audit hygiene batched pass.** CLAUDE.md drift items, ``.cursorrules``
  pointing at a missing file, ``pipeline/exporter.py`` wiring status,
  orphaned ``core/field_mapping.py``, the ``ufm_template/`` directory
  triage, and the loose probe-output ``.txt`` files at the repo root.
  Tracked as task #5.

## Backward compatibility

- Existing callers that did not pass ``deepgram_words`` see no change.
- Existing tests pass unchanged.
- Existing UI flow with no captured Deepgram JSON (e.g., a case folder
  built from a hand-edited transcript) still produces a clean DOCX —
  the helper returns ``None`` and the pipeline degrades gracefully.

## Authority

- ``docs/plans/verbatim_punctuation_plan_2026-05-12.md``
- ``docs/plans/step_c_low_confidence_markers_2026-05-12.md``
- ``docs/plans/step_d_yellow_highlight_rendering_2026-05-12.md``
