# Step D — Yellow-Highlight DOCX Rendering

Final step of the verbatim-punctuation plan
(`docs/plans/verbatim_punctuation_plan_2026-05-12.md`). Step C wrapped
low-confidence Deepgram tokens in `‹LC:...›` markers and routed them
through the Anthropic cleanup pass with preservation instructions. Step
D renders those marked tokens as yellow-highlighted runs in the final
DOCX so the scopist can spot them at a glance.

## Scope

Files modified:

- `clean_format/docx_writer.py` — added `_add_marked_runs` helper and
  updated the Q/A and speaker render paths to split body text on
  marker boundaries. Marker characters are stripped at render time;
  marked tokens get `WD_COLOR_INDEX.YELLOW` highlight.

New file:

- `clean_format/tests/test_docx_low_confidence_highlight.py` — 12 tests
  across 3 classes (highlight rendering, no-marker non-regression,
  layout preservation).

## Render flow

For each paragraph body that may contain markers (Q/A bodies and
speaker bodies), the rewritten render path:

1. Adds a non-highlighted prefix run holding the canonical leading
   tabs and label (e.g., `\tQ.\t`, `\t\t\tMR. SMITH:  `, or `\t\t\t`).
2. Calls `_add_marked_runs(paragraph, body_text)`.
3. `_add_marked_runs` calls `split_into_runs(body_text)` from
   `clean_format.low_confidence_markers` to produce a list of
   `(chunk, is_low_confidence)` tuples.
4. Each chunk becomes its own `Run`. Low-confidence chunks get
   `run.font.highlight_color = WD_COLOR_INDEX.YELLOW`. Unmarked chunks
   render with default styling.

The marker boundary characters (`‹LC:`, `›`) never appear in the
rendered document — they were inline metadata only.

## Layout invariants

These existing layout contracts are preserved across the marker-aware
render path:

- Q/A paragraphs keep their `1.0"` left indent and `-1.0"` first-line
  indent (hanging indent for wrap continuation).
- Q/A paragraphs keep their `0.5" / 1.0" / 1.5"` tab stops.
- Speaker paragraphs keep their three-tab prefix landing the content
  at the `1.5"` tab stop.
- `paragraph.text` (concatenation of all run text) is byte-identical
  to the pre-D render for marker-free input.

The existing `test_docx_writer.py` tests covering tab stops, hanging
indent, leading-tab preservation, and three-tab prefix continue to
pass without modification.

## Header path unchanged

Headers (block `kind == "header"`) render a single bold run as before.
Headers don't contain body text; markers wrap word tokens in body
text only.

## Backward compatibility

- Marker-free input renders byte-identically to pre-D output.
- Existing `clean_format/tests/test_docx_writer.py` (18 tests) passes
  unchanged.
- The 32 Step C tests pass unchanged.
- Full suite: 524 → 536 passing (+12 Step D tests, zero failures).

## End-to-end visual outcome

A deposition transcript with a low-confidence proper noun renders like
this in the DOCX (where `[acebo]` is yellow-highlighted):

```
    Q.    Did you see Dr. [Acebo] on the day of the accident?

    A.    Yes, Dr. [Acebo] examined me that afternoon.
```

The scopist scans the document for yellow blocks and reviews each
against the source audio — the verbatim review workflow the plan was
built to enable.

## Authority

- `docs/plans/verbatim_punctuation_plan_2026-05-12.md`
- `docs/plans/step_c_low_confidence_markers_2026-05-12.md`
