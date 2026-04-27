# Caram AI Correct — Structure Sub-Reason Analysis

Generated: 2026-04-27
Subject: AI Correct re-run on Caram (DC-25-13430) with the new
structure sub-categorization (commit `b4f0db5`). Same input, same
job_config as the prior `caram_post_nod_revert_analysis_2026-04-27.md`
run; only the validator's reason-string granularity changed.
Method: invoked `run_ai_correction` directly via
`temp/run_caram_ai_correct.py` (now writing to
`caram_substructure_*` output paths to avoid clobbering run #1).
Wall clock: 583s. Cost: ~$0.30.

---

## Headline

**Every structure revert in this run was `structure_line_count`.**
Zero `structure_signatures`. Zero `structure_speaker_prefix`. The AI
is not re-attributing speakers or restructuring Q/A skeletons — it is
collapsing or adding lines. That is a single, narrow failure mode,
not three competing ones bundled into "structure."

| Measure | Run #1 (Apr 27 a.m.) | Run #2 (Apr 27 p.m.) | Δ |
|---|---|---|---|
| Total chunks | 18 | 18 | — |
| Successes | 12 (66.7 %) | 10 (55.6 %) | −2 chunks |
| Reverts | 6 (33.3 %) | 8 (44.4 %) | +2 chunks |
| Wall-clock | 603s | 583s | similar |
| Scopist flags | 0 | 0 | — |

The success-rate regression (−2 chunks) is run-to-run model variance,
not an instrumentation regression — the validator's *logic* is
unchanged in `b4f0db5`, only the reason strings it emits. The same
input + same config + temperature > 0 gives different sampling.
Useful reminder: a single Caram run is a sample, not the population.

---

## Per-chunk outcome (this run)

| Chunk | Wall-time | Outcome | Reason |
|---|---|---|---|
| 1/18 | 33s | **REVERT** | `structure_line_count` |
| 2/18 | 52s | SUCCESS | — |
| 3/18 | 47s | SUCCESS | — |
| 4/18 | 47s | SUCCESS | — |
| 5/18 | 27s | SUCCESS | — |
| 6/18 | 25s | SUCCESS | — |
| 7/18 | 27s | **REVERT** | `word_change_ratio` |
| 8/18 | 58s | **REVERT** | `length_delta` |
| 9/18 | 21s | SUCCESS | — |
| 10/18 | 25s | **REVERT** | `word_change_ratio` |
| 11/18 | 44s | SUCCESS | — |
| 12/18 | 25s | SUCCESS | — |
| 13/18 | 29s | **REVERT** | `word_change_ratio` |
| 14/18 | 21s | SUCCESS | — |
| 15/18 | 26s | **REVERT** | `word_change_ratio` |
| 16/18 | 47s | SUCCESS | — |
| 17/18 | 21s | **REVERT** | `structure_line_count` |
| 18/18 | 8s | **REVERT** | `word_change_ratio` |

---

## Reason breakdown (the new data)

```
Total reverts:           8

structure_line_count:    2   (25.0 % of reverts)   chunks 1, 17
structure_signatures:    0   (0.0 %)
structure_speaker_prefix:0   (0.0 %)
word_change_ratio:       5   (62.5 % of reverts)   chunks 7, 10, 13, 15, 18
length_delta:            1   (12.5 % of reverts)   chunk 8
verbatim_count:          0
special_verbatim_forms:  0
protected_content:       0
```

Cross-run comparison — chunks 1 and 17 reverted on `structure` in
*both* runs. With the new instrumentation we now know they reverted
specifically on **line count drift** in this run. Run #1 didn't
distinguish, so we can't say with full certainty those were
line_count there too — but given a 100 % concentration on line_count
in this run and the same input, the prior run's `structure` reverts
on chunks 1 and 17 were almost certainly the same failure mode.

---

## What this isolates

**Hypothesis confirmed:** the prior analysis (line 159) speculated
"the AI is restructuring Q/A or SP attributions in some chunks." The
data rejects that. With 0 / 0 / 2 across signatures / speaker_prefix
/ line_count, the AI is *not* re-attributing or restructuring. It is
adding or removing line breaks.

What "line count drift" specifically means in this codebase:
`_check_structure` calls `text.splitlines()` on input and output. A
mismatch fires `structure_line_count`. The AI must be emitting either
fewer or more `\n` characters than the input had. Common ways this
happens:

1. **Wrapping/un-wrapping a long line.** The AI joins two visually-
   wrapped lines into one, or splits a long line onto two.
2. **Dropping a blank line.** Inter-block separators (Phase G's
   `\n\n` pattern) can lose a member.
3. **Adding a blank line.** Same in reverse.

To know which of those three is dominant, we'd need a finer measure
than "line count differs" — e.g., logging `len(original_lines) -
len(candidate_lines)` so the operator can tell whether the AI is
dropping 1 line (likely wrap-merge) or many (likely structural
collapse).

That's a one-line addition to `_check_structure`'s reason string.
Not pursued tonight — flagged as the natural next instrumentation
step if these two specific chunks need further drill-down.

---

## What word_change_ratio dominance tells us

5 of 8 reverts were `word_change_ratio` (>15 % of words changed).
This run shifted the dominant block from `structure` (run #1) to
`word_change_ratio` (run #2). Three readings, in decreasing
likelihood:

1. **Sampling variance, not signal.** Temperature > 0 means the
   model is making different choices on the same input. The
   threshold is the same; what changed is how aggressively the AI
   rewrote each chunk. Run a third time and the dominant block could
   shift again.

2. **The 15 % threshold is too tight.** The prior analysis flagged
   this. We'd want to log the actual ratio on each `word_change_ratio`
   revert to see whether they cluster at 16-18 % (threshold-grazing)
   or at 30 %+ (genuinely over-rewritten). Same one-line addition as
   above, mirror pattern.

3. **The AI is taking advantage of the new spelling list more
   aggressively.** With 31 confirmed_spellings now reaching the
   prompt (post-NOD migration), each chunk has more candidates for
   word-level substitution. This is the same hypothesis the prior
   analysis raised about chunk 15.

To distinguish (1) vs (2) vs (3), a single run is insufficient.
Three runs of the same input with the same config would give a
ratio distribution per chunk. Out of scope tonight.

---

## What this unlocks

1. **Structure failures are line-count, not Q/A or speaker drift.**
   Prompt-engineering effort should focus on telling the AI "preserve
   line breaks exactly," not on Q/A or speaker stability (which are
   already preserved).

2. **`word_change_ratio` is the real bottleneck right now.** 5 of 8
   reverts. Whether to relax the threshold is a measurement problem,
   not a guess problem — log the ratio per failure, then decide.

3. **Chunks 1 and 17 are the stable structural failures.** Both runs
   reverted them on `structure`. Worth a focused look at what's in
   those specific chunks (chunk 1 is the cover-page area, chunk 17
   is near the end — both regions where transcripts have unusual
   structure: appearances block, certificate, etc.). Plausible the
   AI is mis-handling preamble/closing layouts where the line-count
   contract is tightest.

---

## Recommended next actions (no implementation here)

In priority order:

**A. Log the actual word_change_ratio at the call site.** One
`logger.debug` line in `_validate_ai_output`'s `word_change_ratio`
branch. Tells you whether the threshold is too tight (16-18 %) or
correct (30 %+). Single-file, no behavior change. Mirror Phase A
discipline.

**B. Log line-count delta on `structure_line_count`.** Same
pattern. Tells you whether the AI is dropping 1 line (a wrap merge)
or many (a structural collapse). Single-file.

**C. Inspect chunks 1 and 17 manually.** They are the stable
structural failures. The cover/closing regions of a transcript have
fixed UFM-required structure that the AI doesn't have in its head
unless told. Worth a targeted prompt-engineering experiment: feed
the AI an explicit "preserve every line break in the cover/closing
sections verbatim" instruction and see if 1 and 17 succeed.

**D. Triple-run for variance characterization.** Three runs of the
same input would tell us how much of the per-chunk pass/fail pattern
is signal vs sampling noise. Total cost ~$1, total wall ~30 min.
Not urgent unless we want to make per-chunk threshold decisions.

---

## Files produced this run

| File | Purpose |
|---|---|
| `temp/caram_substructure_corrected.txt` | AI Correct output (140,779 chars vs 141,045 input). |
| `temp/caram_substructure_log_offsets.txt` | pipeline.log byte offsets bracketing the run. |
| `temp/caram_substructure_run.log` | Tee'd stdout (was empty mid-run due to buffering; fully populated post-exit). |
| `temp/run_caram_ai_correct.py` | Runner; output paths renamed to `caram_substructure_*` so this run's artifacts coexist with run #1's. |
| `caram_substructure_analysis_2026-04-27.md` (this file) | Categorized analysis. |

---

## Hard-stop discipline

- No code change to `spec_engine/ai_corrector.py` or any other
  module. The new instrumentation in `b4f0db5` is what enabled this
  measurement; this run consumes it without modifying it.
- No change to `caram_dr/source_docs/job_config.json`.
- No change to validator thresholds (`MAX_LENGTH_DELTA_RATIO = 0.30`,
  `MAX_WORD_CHANGE_RATIO = 0.15`).
- The corrected text in `temp/` is a measurement artifact; the case
  folder's `_corrected.txt` is unchanged.

End of report.
