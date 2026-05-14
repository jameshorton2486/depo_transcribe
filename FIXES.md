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
