# Caram AI Correct — Post-NOD-Migration Revert Analysis

Generated: 2026-04-27
Subject: AI Correct re-run on Caram (DC-25-13430) with the 31
confirmed_spellings + 31 populated UFM fields migrated from the
abandoned `m.d._bianca/` folder.
Validator: instrumented per commit `3c7b3b2` — each revert log line
now includes the specific check that failed.
Method: invoked `run_ai_correction` directly with the migrated
job_config and the existing `_corrected.txt` input. ~10 minutes
wall clock, ~$0.30 API cost.

---

## Headline

| Measure | Pre-migration (2026-04-26) | Post-migration (2026-04-27) | Δ |
|---|---|---|---|
| Total chunks | 18 | 18 | — |
| Successes | 8 (44.4 %) | **12 (66.7 %)** | +4 chunks |
| Reverts | 10 (55.6 %) | **6 (33.3 %)** | −4 chunks |
| Wall-clock | 10m 53s | 10m 03s | similar |
| Scopist flags emitted | 0 | 0 | — |

**Direction: LOWER.** NOD migration helped by **22.3 percentage
points**. Four chunks that previously reverted now succeed.

The 22.3-point improvement is consistent with the hypothesis that
about half of the pre-migration reverts were caused by the AI
producing different proper-noun corrections than the validator's
"verbatim and structure preserving" thresholds tolerated, and that
giving the AI explicit `confirmed_spellings` + UFM context
narrowed its degrees of freedom enough to stay within those
thresholds on the chunks that previously failed.

The 33.3 % residual revert rate — still well into Tier 3 (>15 %)
per the prior diagnostic's rubric — is the structural ceiling
imposed by the validator. NOD context can't lower it further on
its own; loosening (or fixing) the validator is the next lever.

---

## Job-config state at run time (verified)

```
confirmed_spellings:        31 entries
ufm_fields total keys:      43
ufm_fields populated:       31  (was 2 pre-migration: just speaker_map / verified)
witness_name:               'Bianca Caram, M.D.'
cause_number:               'DC-25-13430'
speaker_map_verified:       True
low_confidence_words count: 575
```

The migration applied correctly. JobConfig built from this data has
31 confirmed_spellings on the dataclass. Both the confirmed_spellings
list and the UFM proper-noun fields (witness_name, defense_counsel,
court_caption, etc.) reach the AI prompt as case context.

## Validator state at run time (verified)

`_validate_ai_output` in `spec_engine/ai_corrector.py` returns
`(passed: bool, reason: str)`. The seven possible reason strings:
`verbatim_count`, `special_verbatim_forms`, `structure`,
`length_delta`, `word_change_ratio`, `line_count`,
`protected_content`. Plus a separate revert path on
`_all_protected_tokens_preserved` (the `__VERBATIM_X__` placeholder
guard that runs before validation).

The call site at line 484 logs the reason in the existing revert
message: `AI output failed validation (<reason>) — reverting to
original chunk`.

---

## Per-chunk outcome table

Reconstructed from the script's stdout timeline (chunk start times
and revert events). A chunk is marked SUCCESS when no revert log
appears between its start marker and the next chunk's start marker
(or the run-complete marker).

| Chunk | Chars | Wall-time | Outcome | Reason | Pre-migration outcome |
|---|---|---|---|---|---|
| 1/18 | 8,496 | ~33s | **REVERT** | `structure` | REVERT (failed validation) |
| 2/18 | 8,068 | ~30s | **REVERT** | `structure` | REVERT (failed validation) |
| 3/18 | 8,192* | ~47s | SUCCESS | — | REVERT (verbatim-protected) |
| 4/18 | 8,077* | ~45s | SUCCESS | — | SUCCESS |
| 5/18 | 7,976 | ~27s | SUCCESS | — | SUCCESS |
| 6/18 | 7,894 | ~44s | SUCCESS | — | SUCCESS |
| 7/18 | 7,989 | ~26s | SUCCESS | — | REVERT (failed validation) |
| 8/18 | 8,189 | ~54s | **REVERT** | verbatim-protected | REVERT (failed validation) |
| 9/18 | 8,124 | ~21s | SUCCESS | — | SUCCESS |
| 10/18 | 7,957 | ~24s | SUCCESS | — | REVERT (failed validation) |
| 11/18 | 8,039 | ~25s | SUCCESS | — | SUCCESS |
| 12/18 | 8,370 | ~25s | SUCCESS | — | REVERT (failed validation) |
| 13/18 | 8,366 | ~47s | SUCCESS | — | REVERT (failed validation) |
| 14/18 | 8,144 | ~21s | SUCCESS | — | SUCCESS |
| 15/18 | 8,083 | ~27s | **REVERT** | `word_change_ratio` | SUCCESS |
| 16/18 | 7,975 | ~50s | SUCCESS | — | SUCCESS |
| 17/18 | 8,207 | ~45s | **REVERT** | `structure` | REVERT (failed validation) |
| 18/18 | 2,882 | ~10s | **REVERT** | `word_change_ratio` | REVERT (failed validation) |

`*` = Chunk 3 and 4 char counts shifted slightly between runs because
the chunker's split decision can vary as the input text changes
(this run's input was the same `_corrected.txt`, so the shift
suggests an earlier-stage character drift; minor, not the focus).

**Net flip relative to pre-migration:**
- Newly succeeding (was REVERT, now SUCCESS): chunks 3, 7, 10, 12, 13 (5 chunks gained)
- Newly reverting (was SUCCESS, now REVERT): chunk 15 (1 chunk lost)
- Net improvement: **+4 chunks** = the 22.3-point revert-rate drop

The single regression (chunk 15) is interesting: it was a clean
success pre-migration and now reverts with `word_change_ratio`.
Plausible interpretation: with 31 confirmed_spellings now in the
prompt, the AI is more aggressive about applying proper-noun
substitutions in chunk 15, and crosses the 15 % word-change
threshold that didn't previously fire. This is a "validator now
biting harder because the AI is correcting more" failure mode —
not a regression in correctness, but a regression in
let-the-AI-keep-working-on-this-chunk.

---

## Reason categorization (the new data)

```
Total chunks:        18
Successes:           12   (66.7 %)
Reverts:              6   (33.3 %)

By validator reason (the 5 _validate_ai_output reverts):
  structure          3    (50.0 % of reverts)   chunks 1, 2, 17
  word_change_ratio  2    (33.3 % of reverts)   chunks 15, 18
  verbatim_count     0
  special_verbatim_forms 0
  length_delta       0
  line_count         0    (defensive branch — unreachable here)
  protected_content  0

By non-validator revert path:
  verbatim-protected token removal  1   chunk 8
  All N API attempts failed          0
```

**Interpretation of the dominant reason — `structure` (50 % of reverts):**

The `structure` check fires when line count, signatures (Q/A/SP
markers), or speaker prefixes change between input and AI output.
That's three different things bundled into one validator. To know
which, the validator would need finer-grained reasons (sub-types of
`structure`).

The most plausible cause given 50 % concentration: the AI is
restructuring Q/A or SP attributions in some chunks — re-attributing
a line from `Q.` to a speaker label, or vice versa, or re-wrapping
content across line boundaries. In a deposition transcript with
mostly clean Q/A structure, this is the AI overreaching.

**Interpretation of `word_change_ratio` (33 % of reverts):**

The 15 % threshold is firing on chunks where the AI is applying
many corrections at once. With 31 confirmed_spellings now in the
prompt, this risk is real: a chunk full of proper-noun garbles can
trip the threshold even when each individual change is correct.

**Interpretation of the verbatim-protected revert (chunk 8):**

The `__VERBATIM_N__` placeholder system protects specific token
sequences. The AI removed at least one such placeholder in its
output for chunk 8, so the chunk reverted before validation even
ran. Same path as pre-migration's chunk 3 verbatim revert — likely
the same underlying issue (AI dropping a placeholder token in some
edge case).

---

## Tier classification (per the rubric in `ai_correct_revert_diagnostic_2026-04-27.md`)

| Tier | Range | Interpretation |
|---|---|---|
| 1 | < 5 % | Validator working well |
| 2 | 5–15 % | Validator rejecting some good work; loosening may help |
| 3 | > 15 % | **Validator is the bottleneck** |

Pre-migration: 55.6 % → Tier 3.
Post-migration: 33.3 % → still Tier 3.

NOD migration moved the rate from "double the upper bound of Tier
2" to "double the upper bound of Tier 2" — still in the same tier,
but the headroom from the threshold is significantly reduced.

---

## What this run unlocks

1. **`structure` is now identified as the dominant validator block.**
   3 of 6 reverts. Sub-categorizing the `structure` check (line
   count vs signatures vs speaker prefixes) would tell you which
   specific structural change the AI is making most often. That's a
   one-function refactor in `_preserves_structure` to return a more
   specific reason string.

2. **`word_change_ratio` is the secondary block.** 2 of 6. The 15 %
   threshold may be too tight for chunks where 31 confirmed_spellings
   apply. Worth measuring the actual ratio on the failed chunks to
   see how far over they fall — if they're at 16-18 %, raising the
   threshold to 20 % might unlock the remaining successes without
   permitting hallucinated rewrites. If they're at 30 %+, the AI is
   genuinely over-rewriting and the threshold is correct.

3. **The verbatim-protected revert (chunk 8) is the same failure as
   pre-migration's chunk 3.** Possibly a stable AI behavior — the
   model drops `__VERBATIM_N__` tokens in some specific context.
   Worth a separate investigation of which token/context.

4. **Zero scopist flags emitted, again.** Pre-migration finding
   replicates. Either the AI isn't producing flags despite the
   prompt instruction, or the chunks that contain flags are exactly
   the ones reverting on `structure` (because adding a flag changes
   the line structure). The latter is testable: re-run with the
   `structure` check temporarily relaxed and see if flags appear.

---

## Recommended next actions (no implementation here, just sequencing)

The original master-fix-prompt's tail items (Phase I speaker mapper,
Phase J COUNSEL placeholders, Phase K NOD/keyterm flow audit)
remain on the queue. But this run produces evidence that the
**highest-leverage AI-Correct-side action** is now:

**Sub-categorize the `structure` check** in
`_preserves_structure` so reverts distinguish line-count drift,
signature drift, and speaker-prefix drift. Single-file change in
`spec_engine/ai_corrector.py`. Mirror Phase A's pattern:
return a more specific reason; add per-branch unit tests. Then
re-run Caram a third time to see the structure breakdown — that
data tells you whether to relax the validator, change the prompt,
or treat structure-drift as a real AI failure mode that needs
prompt engineering.

This is a discrete next phase, not yet authorized. Awaiting your
direction.

---

## Files produced this run

| File | Purpose |
|---|---|
| `temp/caram_post_nod_corrected.txt` | Output of `run_ai_correction` on Caram (the corrected text). 140,772 chars vs input 141,045 chars — small reduction consistent with the 12 successful corrections + 6 reverts (where reverts return original text, no length change). |
| `temp/caram_post_nod_log_offsets.txt` | Pipeline.log byte offsets at run boundaries. Note: the script's logger handler did not write to `pipeline.log` when invoked outside the GUI pipeline path; the offsets bracket a window that contains other log activity. The data above is sourced from the script's stdout, not from pipeline.log. |
| `temp/run_caram_ai_correct.py` | The runner script itself. Read-only diagnostic — no code or job_config mutation. |
| `caram_post_nod_revert_analysis_2026-04-27.md` (this file) | Categorized analysis. |

---

## Hard-stop discipline honored

- No code change to `spec_engine/ai_corrector.py`, `spec_engine/corrections.py`, or any other module.
- No change to `caram_dr/source_docs/job_config.json` (its mtime predates this run by hours).
- No change to the validator thresholds (`MAX_LENGTH_DELTA_RATIO = 0.30`, `MAX_WORD_CHANGE_RATIO = 0.15`).
- The corrected text written to `temp/` is a measurement artifact, not a transcript-pipeline output. The case folder's `_corrected.txt` is unchanged.

End of report. Awaiting direction on next workstream — sub-categorize
`structure`, MD cleanup Phase B, or something else.
