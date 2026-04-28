# AICorrector Log Analysis — Caram Run

Generated: 2026-04-27
Source: `logs/pipeline.log` lines 33206–33527
Run timestamp: 2026-04-26 23:03:41 → 23:14:34 (10m 53s wall clock)
Subject: Caram (DC-25-13430), AI Correct pass — pre-NOD-migration baseline

---

## Headline number

**10 of 18 chunks (55.6%) silently reverted to the original (uncorrected) chunk.**

If your Fix 1 hypothesis was that the AI Correct pass is silently failing post-validation on a large fraction of the transcript, this run confirms it dramatically. More than half of the AI's output was thrown away and replaced with the pre-AI text — but the user-visible UI still reports the run as "complete." The user has no way to tell from the app alone that any reversion happened.

---

## Pattern counts (from log)

| Pattern | Count | What it means |
|---|---|---|
| `Split transcript into N chunk(s)` | 1 (N=18) | Transcript split into 18 ~8000-char chunks |
| `AI correcting chunk X/N` | 18 | Every chunk got an API call attempted |
| `AI output failed validation — reverting to original chunk` | **9** | API returned, but validator rejected the output |
| `AI output removed verbatim-protected tokens — reverting to original chunk` | **1** | API returned, but it scrubbed protected verbatim tokens (uh, um, etc.) |
| `All N API attempts failed` | 0 | No outright API failures — every chunk got a response |
| `AI correction complete — N scopist flags generated` | 1 (N=0) | Run completed, zero scopist flags emitted |

**Revert ratio:** (9 + 1) / 18 = **55.6%**

---

## Chunk-by-chunk outcome table

Reconstructed from the order of "AI correcting chunk X/N" markers and the revert lines that appear between them. A chunk is marked SUCCESS only if no revert line appears between its start and the next chunk's start (or the run-complete line).

| Chunk | Chars | Outcome | Revert reason | Wall-time |
|---|---|---|---|---|
| 1/18 | 8,496 | REVERT | failed validation | ~49s |
| 2/18 | 8,068 | REVERT | failed validation | ~66s |
| 3/18 | 7,834 | REVERT | verbatim-protected tokens removed | ~51s |
| 4/18 | 7,937 | **SUCCESS** | — | ~43s |
| 5/18 | 7,867 | **SUCCESS** | — | ~27s |
| 6/18 | 7,933 | **SUCCESS** | — | ~27s |
| 7/18 | 8,291 | REVERT | failed validation | ~29s |
| 8/18 | 8,035 | REVERT | failed validation | ~47s |
| 9/18 | 7,962 | **SUCCESS** | — | ~22s |
| 10/18 | 8,081 | REVERT | failed validation | ~43s |
| 11/18 | 8,511 | **SUCCESS** | — | ~46s |
| 12/18 | 8,370 | REVERT | failed validation | ~49s |
| 13/18 | 8,366 | REVERT | failed validation | ~32s |
| 14/18 | 8,147 | **SUCCESS** | — | ~20s |
| 15/18 | 8,086 | **SUCCESS** | — | ~25s |
| 16/18 | 7,978 | **SUCCESS** | — | ~46s |
| 17/18 | 8,207 | REVERT | failed validation | ~21s |
| 18/18 | 2,882 | REVERT | failed validation | ~10s |

**Successes: 8 chunks (44.4%) covering ~63,500 chars**
**Reverts: 10 chunks (55.6%) covering ~78,800 chars**

The reverts are roughly evenly distributed throughout the transcript — not clustered at the start or end. That rules out one specific hypothesis ("the model breaks down at long context lengths"); the pattern looks more like an across-the-board validator-too-strict problem.

---

## What "failed validation" means in code

Looking at `spec_engine/ai_corrector.py`, two distinct revert paths exist, both visible in the log:

1. **Generic validator failure** (9 occurrences in this run) — the post-API-response validator caught some structural issue with the AI's output (tokens dropped, character drift, structural divergence). The specific reason is not currently logged.
2. **Verbatim-protected token removal** (1 occurrence) — the AI tried to remove a protected verbatim token (uh, um, ah, yeah, etc.). This one is correctly flagged with a specific reason.

The asymmetry is itself a finding: when verbatim removal is the cause, you can tell from the log; when "generic" validation fails, you cannot. That's a gap that should be closed before you try to fix the underlying revert rate, because right now you can't distinguish "AI dropped a sentence" from "AI added a stray period" from "AI re-wrapped the lines and broke character count" — they all read the same in the log.

---

## What this run was operating against

| Setting | Value |
|---|---|
| Prompt pack | `legal_transcript_v1` |
| Model | `claude-sonnet-4-6` |
| Confirmed_spellings active | **0** (the orphan migration we did today was not yet applied at this run time) |
| UFM fields populated | 2 (`speaker_map` only) |

The run happened *before* today's migration of 31 confirmed_spellings + 29 UFM fields into Caram's job_config. So this is the "no NOD context" baseline. A re-run after the migration could change the picture in two directions:

1. **Better:** the AI has more proper-noun context, makes fewer name-related changes that the validator might object to, revert rate drops.
2. **Worse:** the prompt now includes 31 spellings, expanding the user prompt — if the validator is comparing AI output vs original at the character level and counting drift, more correction → more drift → more reverts.

We do not know which way it'll move until we re-run. The headline finding (55.6% silent revert rate) is independent of whether the migration helps or hurts.

---

## Implications for "the two tools"

Your earlier message asked me to improve "the two tools we used to fix and format transcripts." This log analysis tells you which fix has the highest leverage:

- **`spec_engine/ai_corrector.py` validator** is silently reverting more than half the AI's output. Until that's understood and tightened (or loosened, or instrumented to say *why* each revert happened), no amount of prompt engineering or NOD population will land — the validator is the bottleneck.
- **`spec_engine/corrections.py` (Pass 1 deterministic rules)** can't be evaluated from this log alone. It produced what it produced before AI Correct ran; AI Correct then reverted half of itself. Improvements to corrections.py should be driven by a categorized diff against `ground_truth.txt`, not from log inspection.

The prioritized order is therefore:

1. **Instrument the validator to log a specific reason for each "failed validation" revert** (cheap, single-file change, no behavior change). This is a prerequisite for any other improvement — without it, you're flying blind.
2. **Re-run AI Correct on Caram with the migrated NOD data** and see if revert rate moves. (This is Prompt 3 in your three-prompt sequence, but with a "before/after revert rate" comparison added to the report.)
3. **Once revert rate is under control,** then categorized-diff-driven improvements to `corrections.py` and `ai_corrector.py` prompt pack become meaningful.

Doing 2 and 3 first, before 1, is faster but uninformative — you'd be making changes without being able to measure their effect on the revert rate, which is the actual signal of whether the AI Correct pass is doing its job.

---

## Raw log excerpt (every [AICorrector] line from this run)

```
2026-04-26 23:03:41 | [AICorrector] Split transcript into 18 chunk(s) for AI correction
2026-04-26 23:03:41 | [AICorrector] AI correcting chunk 1/18 (8496 chars)…
2026-04-26 23:04:30 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:04:30 | [AICorrector] AI correcting chunk 2/18 (8068 chars)…
2026-04-26 23:05:36 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:05:36 | [AICorrector] AI correcting chunk 3/18 (7834 chars)…
2026-04-26 23:06:27 | [AICorrector] AI output removed verbatim-protected tokens — reverting to original chunk
2026-04-26 23:06:27 | [AICorrector] AI correcting chunk 4/18 (7937 chars)…
2026-04-26 23:07:10 | [AICorrector] AI correcting chunk 5/18 (7867 chars)…
2026-04-26 23:07:37 | [AICorrector] AI correcting chunk 6/18 (7933 chars)…
2026-04-26 23:08:04 | [AICorrector] AI correcting chunk 7/18 (8291 chars)…
2026-04-26 23:08:33 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:08:33 | [AICorrector] AI correcting chunk 8/18 (8035 chars)…
2026-04-26 23:09:20 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:09:20 | [AICorrector] AI correcting chunk 9/18 (7962 chars)…
2026-04-26 23:09:42 | [AICorrector] AI correcting chunk 10/18 (8081 chars)…
2026-04-26 23:10:25 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:10:25 | [AICorrector] AI correcting chunk 11/18 (8511 chars)…
2026-04-26 23:11:11 | [AICorrector] AI correcting chunk 12/18 (8370 chars)…
2026-04-26 23:12:00 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:12:00 | [AICorrector] AI correcting chunk 13/18 (8366 chars)…
2026-04-26 23:12:32 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:12:32 | [AICorrector] AI correcting chunk 14/18 (8147 chars)…
2026-04-26 23:12:52 | [AICorrector] AI correcting chunk 15/18 (8086 chars)…
2026-04-26 23:13:17 | [AICorrector] AI correcting chunk 16/18 (7978 chars)…
2026-04-26 23:14:03 | [AICorrector] AI correcting chunk 17/18 (8207 chars)…
2026-04-26 23:14:24 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:14:24 | [AICorrector] AI correcting chunk 18/18 (2882 chars)…
2026-04-26 23:14:34 | [AICorrector] AI output failed validation — reverting to original chunk
2026-04-26 23:14:34 | [AICorrector] AI correction complete — 0 scopist flags generated
```

The "Prompt pack=…" entries (one per chunk) and httpcore connection-management entries are omitted from the excerpt above for readability but were present and unremarkable in the original log.

---

## Recommended next step

Add a one-line change to `spec_engine/ai_corrector.py` so each `AI output failed validation — reverting` log line includes the *specific* validator that failed (character drift threshold? token removal? structural divergence? something else?). Without this, you cannot tell whether the 9 generic reverts are 9 instances of the same problem or 9 different problems requiring 9 different fixes.

That's a small, single-file, single-layer change. Worth making before any prompt-pack or pipeline-flow changes.

End of report.
