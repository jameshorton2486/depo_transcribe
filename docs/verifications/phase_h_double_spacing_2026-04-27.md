# Phase H — DOCX double-spacing verification

Generated: 2026-04-27
Subject: Confirm `WD_LINE_SPACING.DOUBLE` reaches every body-emitter
paragraph type at runtime.
Method: build a sample DOCX programmatically, exercise every emitter
path, walk `doc.paragraphs`, inspect `paragraph_format.line_spacing_rule`.

Outcome: **No code patch required.** All 14 body-emitter paragraphs
verified at `WD_LINE_SPACING.DOUBLE` (line_spacing 2.0).

---

## Authority

UFM 2.13 (per `docs/transcription_standards/depo_pro_style.md` §12.1):
testimony body must be double-spaced. This phase verifies that
configuration is reaching the rendered file.

## Configuration sites in `spec_engine/emitter.py`

Two distinct sites set `WD_LINE_SPACING.DOUBLE`:

| Site | Lines | Used by |
|---|---|---|
| `_set_paragraph_format` | 88–94 | `emit_q_line`, `emit_a_line`, `emit_sp_line`, `emit_pn_line`, `emit_flag_line`, `emit_header_line`, `emit_by_line`, `emit_plain_line` |
| `emit_line_numbered` direct config | 444–448 | itself (does not call `_set_paragraph_format` because it adds line-number prefix manipulation) |

`create_document` (line 362) sets page dimensions and margins only — does
not configure line spacing at the document level. New paragraphs default
to whatever python-docx's default is until an explicit `paragraph_format`
write happens.

## Verification table

Built a sample DOCX, ran every body-emitter once, plus every
`emit_line_numbered` variant. Walked `doc.paragraphs`. Result:

| # | Paragraph type | `line_spacing_rule` | `line_spacing` |
|---|---|---|---|
| 1 | Q line | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 2 | A line | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 3 | SP line (with bold label) | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 4 | SP continuation (no label) | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 5 | PAREN line | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 6 | FLAG line | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 7 | Header line (examination) | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 8 | BY line | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 9 | Plain line | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 10 | `emit_line_numbered` Q | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 11 | `emit_line_numbered` A | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 12 | `emit_line_numbered` SP | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 13 | `emit_line_numbered` PN | `WD_LINE_SPACING.DOUBLE` | 2.0 |
| 14 | `emit_line_numbered` PLAIN | `WD_LINE_SPACING.DOUBLE` | 2.0 |

Total: 14 paragraphs across 14 distinct emitter paths. Aggregate count
of `WD_LINE_SPACING.DOUBLE`: **14**. Aggregate count of any other rule:
**0**.

## Out of scope: `spec_engine/pages/*.py`

Three sites in the page-writer modules use non-DOUBLE spacing. After
inspection, **all three are intentional, not defects:**

| File | Spacing | Reason |
|---|---|---|
| `_lined_page.py:59` | `line_spacing = 1` (single, inside table cell) | "Builds a 25-line bordered table per UFM page format." Single-spacing inside table cells; UFM-mandated visual spacing comes from row heights, not paragraph spacing. Body text never goes through this layout. |
| `corrections_log.py:24, 98` | default (paragraph-only `add_paragraph`) | File docstring: "Scopist corrections and changes log. **Not part of official transcript.**" Admin/working-reference page — not under UFM 2.13 testimony rule. |
| `post_record.py:22, 31, 78, 86` | default | "Post-record spellings colloquy block." Admin block — same rationale. |

UFM 2.13 governs **testimony body**. Admin pages, scopist references,
and table-cell layouts are intentionally outside that rule. The page
writers correctly do not go through `_set_paragraph_format`. **No patch
applied here.**

If a future requirement extends double-spacing to admin pages
(unlikely — that would conflict with their layout intent), that's a
separate scoping decision.

## Regression guard

The test `test_all_emitted_paragraphs_use_double_spacing` (added to
`spec_engine/tests/test_emitter.py` in this commit) builds the same
sample DOCX, walks the paragraphs, and asserts every paragraph has
`WD_LINE_SPACING.DOUBLE`. If a future change drops DOUBLE on any
body-emitter path, this test fails immediately rather than letting
the regression ship silently.

## Phase H verdict

**PASS.** No emitter code changed. One regression test added. This
verification doc captures the verified state and the reasoning for
the page-writer scope exclusion.

End of Phase H. Master fix sequence (Phases A–H) structurally complete.
