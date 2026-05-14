# Thomas Defect Workflow - Completed Fixes

2026-05-13 - Defect #1 exhibit markers - commit 480a6f8
2026-05-13 - Defect #2 Q/A by-line resumption - commit 2cfd13c
2026-05-13 - Defect #3 objection routing - commit dee6f53
2026-05-14 - Defect #3 refinement colloquy phrase exclusion - commit 12b7f15
2026-05-14 - Defect #4 date and year normalization - commit 3043409
2026-05-14 - Defect #5 money and percent normalization - commit 94a6d00
2026-05-14 - Defect #6 age and time normalization - commit a94e00c
2026-05-14 - Defect #7 DOCX writer Q/A parse and continuation geometry - commit d07336d
2026-05-14 - Defect #8 recess and off-record pair collapsing - commit 0302202
2026-05-14 - Defect #9 reporter's certificate page from UFM template - commit 53a4941

## Defect #10 — `_adapt_saved_utterances` word preservation

**Date:** 2026-05-14
**Branch:** `review/phase-a-production`
**Layer:** `core/`
**Files changed:** `core/corrections_runner.py`, `core/tests/test_corrections_runner.py`

### Symptom
Production blocks had `words: None` even though `raw_deepgram.json`
carried 13,598 word objects with full Deepgram timing data.

### Discovery
v5 pipeline probe on Thomas case: 978 processed blocks, all with
`words=None`. Discovery probe traced the cause to
`core/corrections_runner._adapt_saved_utterances` building output
dicts that excluded the `words` field.

### Fix
Added one key to the adapter's output dict literal:
`"words": u.get("words")`. Preserves None semantics. No
`spec_engine/` changes required — downstream stages already handle
the carry-through contract per Step B.0
(`docs/plans/_archive/step_b0_word_carry_2026-05-12.md`).

### Verification
- 39 existing word-carry tests pass unchanged
  (`test_word_carry.py`, `test_word_carry_b1.py`)
- 3 new adapter-focused tests in `test_corrections_runner.py`
- Full suite: 982 passed / 6 skipped
- Thomas baseline: 6/6

### Defers
- Defect #11 (attorney exam-time computation) — can now re-enter
  discovery; words should populate on real Thomas data.
- Examiner-population bug surfaced by v5 probe (14 garbage values).
- Speaker-mapper failing to apply `speaker_map_suggestion` on
  Thomas (numeric `SPEAKER 1:` instead of named attorneys).

## Defect #11 — `_looks_like_directive` strict BY-line match

**Date:** 2026-05-14
**Branch:** `review/phase-a-production`
**Layer:** `spec_engine/`
**Files changed:** `spec_engine/classifier.py`, `spec_engine/tests/test_classifier.py`

### Symptom
v5 post-defect-#10 probe on Thomas: 14 question blocks had garbage
examiner values like `'PUTTING AROUND 20 WINDOWS ON THE SHEET CART?'`.

### Discovery
Pre-implementation probe traced the cascade:
1. `classifier._looks_like_directive` matched any `"BY "` prefix,
   regardless of suffix.
2. `qa_fixer._directive_examiner_name` extracted text after `"BY "`
   as the examiner name.
3. `qa_fixer.enforce_structure` propagated that bad examiner to
   subsequent question blocks until a real directive replaced it.

The fix lives at step 1. Tightening the trigger stops the cascade.

### Fix
Added trailing-colon requirement to `_looks_like_directive`. Match
now requires both `text.startswith("BY ")` (or `"BY\t"`) AND
`text.endswith(":")`. Aligns with the strict form
`byline_resumption._is_section_header_directive` already documented
as the canonical classifier output.

### Verification
- All 14 existing BY-line test fixtures across 7 test files use
  colon-terminated form (audited via grep)
- 4 new tests in `test_classifier.py`
- Full suite: 986 passed / 6 skipped
- Thomas baseline: 6/6

### Unblocks
- Defect #12 (attorney exam-time computation) — examiner field
  now reliable enough to key totals by

### Defers
- Build speaker name-mapping (numeric `SPEAKER 1:` → `MR. NUNEZ`).
  Future Next-A.
- Loosen `is_question_loose` so it catches semantic questions, not
  just `"Q."` prefix. Out of scope for #11.
