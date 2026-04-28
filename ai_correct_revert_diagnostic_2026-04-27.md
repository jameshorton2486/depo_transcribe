# AI Correct Revert-Rate Diagnostic

Generated: 2026-04-27
Source: `logs/pipeline.log` (current) and rotated logs `.1` / `.2` / `.3`
Read-only diagnostic. No code modified, no logs modified, no pipeline run.

---

## Logs surveyed

| File                  | Lines  | `Split transcript into…` markers | `AI correction complete…` markers |
|-----------------------|--------|----------------------------------|-----------------------------------|
| `logs/pipeline.log`   | 33,531 | 1                                | 1                                 |
| `logs/pipeline.log.1` | 58,550 | 0                                | 0                                 |
| `logs/pipeline.log.2` | 58,974 | 0                                | 0                                 |
| `logs/pipeline.log.3` | 58,543 | 0                                | 0                                 |

**Total runs found: 1.** Older AI Correct activity, if any, has aged out
of the rotation window.

---

## Run identification

A single run is present in the logs. The case is identifiable from the
pipeline-summary block written 10 seconds before the run started:

> `output: 04-09-26 Biana Caram MD 01_1_combined_20260426_223304_corrected.txt`

This is the Caram (DC-25-13430) deposition.

**Run window:** 2026-04-26 23:03:41 → 23:14:34 (wall clock 10m 53s)
**Job-config state at run time:** 2 ufm_fields keys (`speaker_map`,
`speaker_map_verified`), 0 `confirmed_spellings`, 0 `keyterms`. Pre-NOD-
migration baseline.
**Pre-run warning emitted by correction_runner:**

> `[CorrectionRunner] confirmed_spellings empty — name corrections will not run for this transcript`

---

## Run 1 — Caram (DC-25-13430), 2026-04-26 23:03:41

```
Total chunks:            18
Validation reverts:       9    (9/18  = 50.0 %)
Verbatim-token reverts:   1    (1/18  =  5.6 %)
API failure reverts:      0    (0/18  =  0.0 %)
Total reverts:           10    (10/18 = 55.6 %)
Scopist flags generated:  0
```

**Tier classification: Tier 3 — Total revert rate > 15 %.**
Per the prompt's interpretation rubric, the validator is the
bottleneck; significant chunks of work are being silently dropped.

---

## Tier rubric (from the prompt)

| Tier | Range  | Interpretation                                                                         |
|------|--------|----------------------------------------------------------------------------------------|
| 1    | < 5 %  | Validator working well; chat/pipeline gap is from somewhere else                       |
| 2    | 5–15 % | Validator rejecting some good work; loosening thresholds may help                      |
| 3    | > 15 % | **Validator is the bottleneck; significant chunks of work are being silently dropped** |

Run 1 sits at **55.6 %**, more than triple the upper bound of Tier 2
and more than eleven times the upper bound of Tier 1. This is
unambiguously Tier 3 territory.

---

## One-paragraph plain-prose interpretation

The single AI Correct run captured in the current log rotation shows
55.6 % of all chunks silently reverting back to the original
(uncorrected) text. Of those, the overwhelming majority (9 of 10
reverts) were generic "failed validation" — the validator rejected the
AI's output but the log does not record which specific check failed.
One revert was attributable to verbatim-protected token removal, which
is the only revert reason currently logged with specificity. No API
calls failed outright. The job-config at run time had zero
`confirmed_spellings` and zero `keyterms`, which means the model was
operating without any case-specific noun context — the orphan-folder
migration that landed earlier today was not in effect for this run.
Whether the migration would change the revert rate is unknown until a
post-migration run produces a comparable measurement; the prompt rubric
is clear that this run alone places us in the highest-leverage tier.

---

## Limitations of this diagnostic (kept brief, per prompt scope)

- **Sample size is one run.** The rotated logs do not contain earlier
  AI Correct activity, so trend or per-case variation cannot be
  characterized from current data.
- **The 9 generic "failed validation" reverts cannot be sub-categorized
  from the log alone.** They could be one root cause repeated nine
  times or nine distinct causes — the log does not say.
- **Run was pre-NOD-migration.** A re-run on the migrated job_config
  would produce a comparable post-migration number. That re-run is
  out of scope for this diagnostic.

End of report.
