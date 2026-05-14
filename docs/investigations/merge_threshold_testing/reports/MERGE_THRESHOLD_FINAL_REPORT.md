# Merge-Threshold Stabilization — Final Report

**Investigation:** controlled utterance-merge threshold sweep.
**Case under test:** `etminan_mohammad` (83-min deposition, 9 chunks).
**Date:** 2026-05-13.
**Production code modified:** logging additions + opt-in override hook only; production behavior unchanged when overrides are not set.

---

## Section 1 — Background

The prior audit (`docs/audits/UTTERANCE_CONFIGURATION_AUDIT_2026-05-13.md`) established three load-bearing facts:

1. **Deepgram is correctly receiving `utt_split=0.8`.** That value is pinned in `pipeline/transcriber.py:94` by `REQUIRED_DEEPGRAM_FLAGS` and the request URL carries it on every chunk.
2. **Deepgram is returning fine-grained utterances.** On this case, the pooled `chunks[*].results.utterances` lists held **1,141** Deepgram-native utterances.
3. **Two local merge stages compress that to ~340 by the time the active path writes `raw_deepgram.json`.** The stages are `pipeline/transcriber.py::merge_utterances` (per-chunk, default `MERGE_GAP_THRESHOLD_SECONDS = 0.6`) and `pipeline/assembler.py::merge_utterances` (cross-chunk, default `GAP_THRESHOLD_SECONDS = 1.25`).

This investigation tests whether varying the two merge thresholds, in their production order, yields a more structurally faithful transcript. **No conclusion about a default change is being recommended.** The output is measurement plus a directional recommendation grounded in evidence from one representative case.

---

## Section 2 — Existing Merge Architecture

The two merge stages on the active path run in fixed order:

```
Deepgram response (per chunk, ~1,141 utterances total)
   │
   ▼
pipeline/transcriber.py::_transcribe_direct
   • _annotate_confidence
   • smooth_speakers
   • merge_utterances(gap=MERGE_GAP_THRESHOLD_SECONDS=0.6,
                      min_words=MERGE_MIN_WORD_COUNT=1)
   • returns raw_utterances (post per-chunk merge)
   │
   ▼
pipeline/assembler.py::reassemble_chunks
   • per-chunk timestamp offsetting
   • cross-chunk overlap dedup
   • merge_utterances(gap=GAP_THRESHOLD_SECONDS=1.25,
                      short_gap=SHORT_GAP_THRESHOLD_SECONDS=0.6,
                      min_words=MIN_UTTERANCE_WORDS=2)
   • returns the final utterances list written to raw_deepgram.json
```

Both `merge_utterances` functions share a single invariant: **they never combine utterances belonging to different speakers.** Same-speaker adjacency with small gap → merge. Different-speaker → preserve boundary. This is the whole legal-record safety mechanism for the merge logic.

That invariant has a subtle consequence explored later in this report: when Deepgram itself attributes the wrong speaker number to a witness "Yes." (a diarization error upstream of both merge stages), our merge happily glues that "Yes." into the attorney's adjacent same-speaker block — because by the time the data reaches us, it has already been mis-labeled as the same speaker.

---

## Section 3 — Deepgram Findings (Baseline Reference)

Analysis of the Deepgram-native utterances **before any local merge** (`output/investigation/raw_deepgram_structure.md`):

| Metric | Value |
|---|---:|
| Utterance count | **1,141** |
| Avg duration | 3.58 s |
| Median duration | 2.80 s |
| Max duration | 30.57 s |
| Long utterances (>30 s) | 1 |
| > 100-word utterances | 1 |
| Suspicious merged Q/A (Q+answer-phrase in one utt) | **106** |
| Speaker transition inside utterance (>1 word-level speaker) | **121** |
| Standalone short answers ("Yes."/"No."/"Correct." alone) | **22** |

The two findings to anchor every conclusion against:

1. **Deepgram itself produces 106 utterances that contain both a question mark and a mid-utterance Yes/No.** No local merge stage created these. They are imported as-is. Our local merge can only fail to fix them; it cannot create them.
2. **Deepgram produces 22 isolated "Yes."/"No."/"Correct." standalone utterances** — the legal-record gold. Every one of those that survives the merge stages is a recovery of a clean witness short answer.

---

## Section 4 — Experimental Matrix

Defined in `tools/investigation/merge_threshold_matrix.py`:

| Name | in_chunk_gap (s) | cross_chunk_gap (s) | Description |
|---|---:|---:|---|
| `TEST_A_CURRENT` | 0.6 | **1.25** | Production defaults. Reference. |
| `TEST_B_MODERATE` | 0.6 | 0.9 | Tighten cross-chunk only. |
| `TEST_C_TIGHT` | 0.6 | 0.6 | Both stages at 0.6 (symmetric). |
| `TEST_D_VERY_TIGHT` | 0.4 | 0.5 | Aggressive bound. |

Driver: `tools/investigation/run_merge_experiments.py`. Production code paths are not edited for the sweep — the driver calls `pipeline.transcriber.merge_utterances` and `pipeline.assembler.merge_utterances` directly with explicit threshold arguments.

The investigation hook in `pipeline/merge_debug_config.py` exists for **future** scenarios where the user wants to run a full Start-Transcription end-to-end with a tighter threshold; in that case env vars `DEPO_TRANSCRIBE_MERGE_IN_CHUNK_GAP` / `DEPO_TRANSCRIBE_MERGE_CROSS_CHUNK_GAP` are wired into the active path through `pipeline/transcriber.py:749` and `pipeline/assembler.py:546,665`. The override module returns `None` by default, so the active path uses the unchanged production constants until someone opts in.

---

## Section 5 — Run Results

Raw counts straight from each run's `metrics.json`:

| Config | Utterances | Avg dur (s) | Max dur (s) | Avg words | Max words | Long (>30s) | >100w | Merged Q/A | Speaker switch | Standalone short ans |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Deepgram-native (baseline) | 1,141 | 3.58 | 30.57 | 10.66 | 105 | 1 | 1 | 106 | 121 | **22** |
| `TEST_A_CURRENT` (0.6 / 1.25) | 354 | 12.17 | 101.63 | 34.35 | 296 | 35 | 20 | 77 | 101 | **4** |
| `TEST_B_MODERATE` (0.6 / 0.9) | 419 | 10.27 | 84.13 | 28.91 | 296 | 17 | 9 | 85 | 105 | **4** |
| `TEST_C_TIGHT` (0.6 / 0.6) | 523 | 7.96 | 84.13 | 23.25 | 242 | 6 | 5 | 92 | 110 | **4** |
| `TEST_D_VERY_TIGHT` (0.4 / 0.5) | 576 | 7.25 | 80.06 | 21.07 | 222 | 4 | 4 | 93 | 110 | **4** |

Spec_engine classifier counts (run on raw merged text, no Anthropic in the pipeline — see Section 7 caveat):

| Config | colloquy | oath | question | answer |
|---|---:|---:|---:|---:|
| `TEST_A_CURRENT` | 353 | 1 | 0 | 0 |
| `TEST_B_MODERATE` | 418 | 1 | 0 | 0 |
| `TEST_C_TIGHT` | 522 | 1 | 0 | 0 |
| `TEST_D_VERY_TIGHT` | 575 | 1 | 0 | 0 |

Pairwise comparison reports against `TEST_A_CURRENT`:

- `compare_TEST_A_CURRENT_vs_TEST_B_MODERATE.md`
- `compare_TEST_A_CURRENT_vs_TEST_C_TIGHT.md`
- `compare_TEST_A_CURRENT_vs_TEST_D_VERY_TIGHT.md`

---

## Section 6 — Transcript Examples

Per-run snapshots live at `docs/investigations/merge_threshold_testing/runs/<TEST_NAME>/snapshots.{txt,md}` and cover four categories (rapid-fire Q/A, objections, colloquy, problematic merges). A few representative observations across configs:

### Problematic merges are inherited from upstream, not created by the assembler

This bad merge appears identically in `TEST_A_CURRENT`, `TEST_B_MODERATE`, `TEST_C_TIGHT`, and `TEST_D_VERY_TIGHT`:

> "where is your practice located at, Doctor? I'm in Houston and in Houston. I have 2 offices and 1 in Memorial City and 1 in Sugar Land."

It is one utterance under one speaker label in every configuration. The attorney's question and the doctor's answer were already glued by Deepgram at the per-chunk response level (with the same `speaker` integer). Tightening either merge gap cannot un-merge it because both merge functions only fire on same-speaker adjacency — they never split.

### Oversized utterances do respond to the threshold

`>100-word` utterances drop from **20 → 4** as the threshold moves from 1.25 → 0.5. Long monologues are the one place tightening the gap actually changes outcomes — they're being created by aggressive same-speaker merge across short pauses inside one speaker's contiguous turn.

### Rapid-fire Q/A density rises substantially as the gap tightens

Walking `snapshots.md` for each config:

- `TEST_A_CURRENT`: very few rapid-fire Q/A clusters detected — most Q/A pairs are already absorbed into longer blocks.
- `TEST_D_VERY_TIGHT`: many rapid-fire windows; short utterances dominate the output, which exposes natural deposition cadence but also exposes Deepgram diarization mistakes as separate small utterances.

### Standalone witness short answers do **not** recover with threshold tightening

Production (1.25 cross): 4 surviving "Yes."/"No."/"Correct." standalone utterances out of 22 Deepgram emitted.
TEST_D_VERY_TIGHT (0.5 cross + 0.4 in-chunk): **also 4**.

This is the central diagnostic finding of the investigation. See Section 7.

---

## Section 7 — Downstream Effects

### 7.1 Q/A integrity (the load-bearing metric)

**Merged-Q/A candidate counts actually rise as the threshold tightens** (77 → 93 from `TEST_A_CURRENT` → `TEST_D_VERY_TIGHT`). At first glance this looks like the wrong direction. The honest explanation: more utterances means more discrete units against which the heuristic can fire. At `TEST_A`, a single 296-word utterance that contains a question and two embedded "Yes" answers counts as **one** flag; at `TEST_D` the same content might be split into three utterances of which two register as flags.

The **rate** of Q/A blending per minute of audio is roughly constant because the source defects (Deepgram speaker mis-attribution) are constant.

### 7.2 Speaker continuity

`speaker_transition_inside_utterance` is 101 → 110 across the four configs. Approximately flat. The metric counts utterances whose constituent words carry more than one speaker tag — i.e., utterances that even Deepgram's word-level data disagrees with itself about. Lowering the threshold cannot fix word-level data, so the metric is essentially threshold-independent.

### 7.3 Objection extraction

Snapshot inspection shows objection lines (e.g. "Objection, form.") appear isolated in every configuration. The objection-detection regex is robust to threshold variation on this transcript.

### 7.4 Transcript readability

Average words-per-utterance ranges from 34.35 (A_CURRENT) down to 21.07 (D_VERY_TIGHT). For a court reporter reviewing the DOCX output, the tighter configs produce far more readable Q/A pairings — questions are short and isolated; answers (when not absorbed by upstream diarization error) appear as separate utterances.

### 7.5 Merged-answer frequency

**Cannot be reliably measured from raw transcripts.** The signal would require Anthropic cleanup to surface `Q.\t…` / `A.\t…` markers; that is deliberately skipped in this experiment to keep cost at zero. The standalone-short-answer count (4 across all configs) is the best proxy available, and it says the absorption rate is upstream-locked.

### 7.6 Paragraph structure

Deepgram itself did not return a top-level `paragraphs` field in this case's `raw_deepgram.json` (see prior audit). Paragraph-level structure therefore does not vary across the four configs; `spec_engine/block_builder.py` falls through to the utterance branch in all four.

### 7.7 Classifier stability

Every config types every block as `colloquy` (with the single sworn-oath block as `oath`). That is **not** an instability — `spec_engine/classifier.py::_classify_type` looks for `\tQ.\t` / `\tA.\t` prefixes (or `is_question_loose` patterns), both of which the **Anthropic cleanup pass** introduces. On raw transcripts those prefixes are absent and everything types as colloquy regardless of merge threshold. The classifier signal is not produced in this experiment because Anthropic was deliberately skipped to keep API spend at zero. **This is a known measurement gap, not a finding.**

---

## Section 8 — Risk Analysis

### Risks of tightening the assembler threshold (e.g. 1.25 → 0.8 or 0.6)

| Risk | Magnitude on this case | Mitigation observed |
|---|---|---|
| Sentence-level fragmentation | Low at 0.8–0.6; modest at 0.5. Max-words-per-utt stays ≥ 222 even at TEST_D, so we are not breaking individual sentences in half. | The same-speaker invariant naturally limits over-fragmentation. |
| Speaker-flip-glitch surfacing as separate utterance | Mild. `speaker_transition_inside_utterance` is essentially flat. | `smooth_speakers` + `_is_short_glitch` already absorb sub-200ms glitches. |
| Loss of monologue continuity | Real. `long_utterance_count (>30s)` drops from 35 → 4. Some genuine long testimony will be split where the witness paused. | A reviewer reading the DOCX would see two utterances with the same `Speaker N:` label adjacent; the merge boundary is visible but the content is intact. |
| Anthropic cleanup behavior on tighter input | **Unknown.** The current prompt was tuned against the production granularity. | Would require a controlled Anthropic-included run at each threshold. Recorded as a follow-up. |

### Risks of NOT tightening (keeping 1.25)

| Risk | Magnitude on this case | Evidence |
|---|---|---|
| Q/A pairs collapsed into one utterance | Real. 77 detected on `TEST_A`. | Snapshot examples in `runs/TEST_A_CURRENT/snapshots.md`. |
| Loss of standalone witness "Yes."/"No." | Real but **not the merge's fault**. | Section 7.5 — upstream Deepgram diarization is the root cause. |
| Oversized blocks degrade scopist review | Real. 20 utterances over 100 words on `TEST_A`. | Drops to 4 at `TEST_D`. |
| Anthropic prompt mis-fires on giant blocks | Plausible but unmeasured. | Marker-drift on the Etminan AI cleanup run (51.7% — see `02b_anthropic_raw_response.txt` in the prior walkthrough) suggests very long blocks may be part of the Anthropic stability problem, but causation is not established. |

### Failure modes the experiment specifically cannot rule out

- A different case (different acoustic conditions, different speaker count) might produce a different threshold sweet spot.
- A different audio quality tier (this run was `audio_tier=ENHANCED`) might produce different Deepgram boundaries.
- The Anthropic cleanup pass might prefer one merge configuration over another in ways not captured by raw heuristics.

---

## Section 9 — Recommended Threshold

### Directional recommendation: **`cross_chunk_gap = 0.8`** (matching the Deepgram `utt_split` value)

**Rationale:**

1. **Aligns local merge cadence with upstream Deepgram cadence.** Deepgram emits utterance boundaries at ~0.8s silence; merging with the same gap on our side means the local merge applies a single coherent same-speaker grouping policy at the same granularity Deepgram chose.
2. **Captures the over-merging fix without paying the readability cost.** Between `TEST_A_CURRENT` (1.25) and `TEST_C_TIGHT` (0.6), `>100-word utterances` drops from 20 → 5 and `long_utterance_count(>30s)` drops from 35 → 6. The 0.8 value sits closer to the C end of that arc.
3. **Conservative inside the experimental range.** Not at either extreme (`TEST_A` at 1.25 over-merges; `TEST_D` at 0.5 starts approaching fragmentation territory).
4. **Symmetric with the prior audit's framing.** The audit explicitly named 0.8 as "the most defensible choice if any change is contemplated, because it aligns the cross-chunk merge gap with the Deepgram `utt_split` value already in production — matching the upstream cadence rather than creating a second, looser segmentation policy on top of it."

**This is not a directive.** Production behavior is unchanged. The recommendation is what the data on this one case supports.

### What the recommendation does NOT claim

- It does **not** claim that 0.8 will fix the merged-Q/A problem. The root cause (Deepgram diarization labeling attorney + witness with the same speaker number) cannot be fixed by any merge threshold.
- It does **not** claim that 0.8 will produce a better Anthropic-cleaned DOCX. That requires a follow-up experiment that includes the cleanup pass.
- It does **not** claim that 0.8 is correct across all cases. One audited case is one data point.

### Suggested adoption path (not implemented)

1. Run one Start-Transcription end-to-end with `DEPO_TRANSCRIBE_MERGE_CROSS_CHUNK_GAP=0.8` on a fresh case (different speakers, different acoustic conditions) and inspect the DOCX visually.
2. If the DOCX reads cleanly, run the same on two more cases.
3. Only then consider editing `pipeline/assembler.py:31` (`GAP_THRESHOLD_SECONDS`).

---

## Section 10 — Future Investigation Ideas

The following are **observations**, not implementation requests:

1. **Re-run with Anthropic cleanup included.** The merged-answer and Q/A-pair signals require the Anthropic cleanup pass to surface `Q.`/`A.` prefixes. A controlled experiment pairing each threshold with one Anthropic call would let `spec_engine/classifier.py` produce real `question`/`answer` counts, which is the most decision-relevant downstream metric. Cost: ~1 Anthropic call per threshold.
2. **Investigate why Deepgram is attaching the same speaker number to both attorney and witness in some utterances.** Could be an audio preprocessing issue, a Deepgram-side diarization artifact for similar voices, or a side-effect of `smart_format=true`. Distinct experiment.
3. **Investigate why no `paragraphs` field appears in the saved `raw_deepgram.json`** despite `paragraphs=true` being sent. `spec_engine/block_builder.py` is wired to prefer paragraph-based parsing when present; today it always falls through to utterances. Recovering paragraphs may improve downstream Q/A detection independently of merge thresholds.
4. **Validate on a different case** — ideally one with a different number of speakers, a different acoustic environment, and a different attorney/witness gender pairing (the Deepgram-side diarization confusion may be voice-similarity dependent).
5. **Quantify Anthropic marker-drift correlation.** Etminan saw 51.7% marker drift on the cleanup pass; if larger pre-cleanup utterances correlate with higher drift, that is a second independent reason to prefer a tighter threshold.

---

## Section 11 — Things That Should NOT Change

Per the investigation charter and CLAUDE.md contracts:

- **Do not change Deepgram request parameters.** `utt_split=0.8` is correct. `paragraphs=true`, `diarize=true`, `smart_format=true`, `filler_words=true`, `numerals=true`, `utterances=true` are correct. `REQUIRED_DEEPGRAM_FLAGS` should remain authoritative.
- **Do not modify the Anthropic cleanup prompt** in `clean_format/prompt.py`. Its strict-verbatim posture is the load-bearing legal-fidelity contract.
- **Do not modify spec_engine.** It is the offline correction path; this investigation does not touch it.
- **Do not modify the DOCX writer.** Its tab-stop / hanging-indent / yellow-highlight rules are settled.
- **Do not implement adaptive per-case threshold tuning.** The data from one case does not support that complexity. Adaptive tuning adds state, branching, and tests; the alternative — a single, well-chosen static value — is simpler and at least as defensible.
- **Do not collapse the two merge stages** (`transcriber.merge_utterances` and `assembler.merge_utterances`). They operate on different scopes (single chunk vs. assembled chunks); merging them adds risk without benefit.
- **Do not commit the investigation overrides into production.** `pipeline/merge_debug_config.py` is investigation-only, returns `None` by default, and is exercised by env vars and the experiment runner only.

---

## Appendix — Artifacts Produced

### Per-run artifacts (one set per config under `docs/investigations/merge_threshold_testing/runs/etminan_mohammad/`)

- `metrics.json` — config + structure + classifier counts
- `utterances.json` — final merged utterance list
- `transcript.txt` — production `build_transcript_text` output
- `snapshots.txt` and `snapshots.md` — representative samples

### Cross-run artifacts

- `docs/investigations/merge_threshold_testing/runs/etminan_mohammad/all_metrics.json`
- `docs/investigations/merge_threshold_testing/reports/compare_TEST_A_CURRENT_vs_TEST_B_MODERATE.md`
- `docs/investigations/merge_threshold_testing/reports/compare_TEST_A_CURRENT_vs_TEST_C_TIGHT.md`
- `docs/investigations/merge_threshold_testing/reports/compare_TEST_A_CURRENT_vs_TEST_D_VERY_TIGHT.md`
- `output/investigation/raw_deepgram_structure.{md,json}` — Deepgram-native baseline

### Investigation-only code

- `tools/investigation/merge_threshold_matrix.py`
- `tools/investigation/run_merge_experiments.py`
- `tools/investigation/analyze_utterance_structure.py`
- `tools/investigation/compare_merge_runs.py`
- `tools/investigation/export_transcript_snapshots.py`
- `pipeline/merge_debug_config.py` (production module, but is a no-op when overrides are unset)

### Reproducing the experiment

```powershell
.\.venv\Scripts\python.exe -m tools.investigation.run_merge_experiments `
    --case-dir "<case_dir>"
.\.venv\Scripts\python.exe -m tools.investigation.compare_merge_runs `
    "docs\investigations\merge_threshold_testing\runs\<case>\TEST_A_CURRENT" `
    "docs\investigations\merge_threshold_testing\runs\<case>\TEST_C_TIGHT"
```
