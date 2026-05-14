# Merge-Threshold Stabilization Investigation

## Purpose

Determine whether the local utterance-merge thresholds in
`pipeline/transcriber.py` (per-chunk) and `pipeline/assembler.py`
(cross-chunk) are the principal cause of transcript structural
degradation observed in production — specifically merged Q/A blocks,
combined attorney/witness turns, and oversized utterances — and
identify the **safest** production merge configuration backed by
measurable evidence.

The prior audit
(`docs/audits/UTTERANCE_CONFIGURATION_AUDIT_2026-05-13.md`) confirmed
that Deepgram itself is receiving `utt_split=0.8` and returning
fine-grained utterances (~1,107 for the audited case). The
application then collapses those to ~340 through two local merge
passes. This investigation evaluates that compression empirically.

## Why utterance merging matters for legal depositions

Each utterance is the smallest unit the downstream pipeline treats
as one speaker's contiguous turn. The Anthropic cleanup pass uses
those boundaries to assign `Q.` and `A.` prefixes; the DOCX writer
uses them to lay out speaker labels; the offline `spec_engine/`
classifier looks at one utterance at a time to type it as
`question`, `answer`, `directive`, `oath`, or `colloquy`. If two
distinct speaker turns get glued into a single utterance, every
downstream stage inherits that merge — there is no later stage in
the active path that splits utterances back apart.

In a deposition context the verbatim record is the load-bearing
artifact. Specifically:

- **Speaker attribution must be exact.** A merged Q/A means the
  witness's words and the attorney's words appear under one speaker
  label. That is a legal-record defect, not a readability defect.
- **Short witness answers carry weight.** Standalone "Yes." / "No."
  / "Correct." responses are the legally meaningful answer in many
  questions. If they get absorbed into the preceding attorney
  utterance, the answer is invisible to the reader.
- **Examination structure depends on isolated questions.** UFM Q/A
  formatting requires the question and the answer to be separate
  utterances; merged blocks cannot be rendered as `Q.\t…` / `A.\t…`
  pairs.

## Risks the experiment is weighing

| Direction | What it costs |
|---|---|
| **Over-merging** (large gap, current default 1.25s) | Q/A pairs collapse, attorney/witness turns blend, short answers vanish, classifier types whole exchanges as colloquy. This is what we currently observe. |
| **Under-merging** (small gap, e.g. 0.4s) | Single utterances split mid-sentence, fragmented monologues, possible speaker-flip glitches surfacing as separate utterances, classifier instability driven by sub-sentence fragments. |

Neither extreme is acceptable. The investigation aims to locate the
threshold that minimizes Q/A blending **without** introducing
sentence-level fragmentation.

## Methodology

1. **Re-use cached Deepgram output.** No re-transcription, no API
   spend. The 1,141 pre-per-chunk-merge Deepgram-native utterances
   are read from `raw_deepgram.json["chunks"][*]["results"]["utterances"]`
   on disk.
2. **Sweep four configurations** defined in
   `tools/investigation/merge_threshold_matrix.py`:
   - `TEST_A_CURRENT` — production defaults (in 0.6 / cross 1.25)
   - `TEST_B_MODERATE` — same in-chunk, tighter cross-chunk (0.9)
   - `TEST_C_TIGHT` — both stages at 0.6
   - `TEST_D_VERY_TIGHT` — in 0.4 / cross 0.5
3. **Apply both merge stages** in their production order using the
   experimental gap values. Code lives in `tools/investigation/`;
   production source is **not** modified for the sweep, except for
   the opt-in override module in
   `pipeline/merge_debug_config.py` whose default is "no override".
4. **Measure downstream effects** on the merged output for each
   configuration: utterance counts, duration distribution,
   suspicious-Q/A indicators, speaker-transition-inside-utterance
   counts, and `spec_engine/classifier.py` type distributions.
5. **Save reproducible artifacts** per run under
   `docs/investigations/merge_threshold_testing/runs/<TEST_NAME>/`
   so any individual run can be re-opened and inspected.
6. **Compare runs pairwise** with
   `tools/investigation/compare_merge_runs.py` and produce a
   single final report.

## Success criteria

This investigation succeeds when:

1. We can state with evidence which of the four thresholds yields
   the most legally-faithful transcript structure on the audited
   case.
2. We can show the per-utterance distribution and bad-merge counts
   side-by-side for each configuration.
3. Production behavior is unchanged unless and until a separate
   decision is made to ship a different default.
4. Every CLAUDE.md contract holds:
   - `pipeline/` remains audio + Deepgram only.
   - `clean_format/` remains untouched.
   - `spec_engine/` is **only** invoked here for read-only
     classifier counting on experimental output; not wired into the
     active path.
   - DOCX rendering behavior unchanged.
   - Verbatim posture (filler words, low-confidence markers, em-dash
     normalization) unchanged.

## What this investigation explicitly will NOT do

- Re-architect the merge system.
- Implement adaptive per-case tuning.
- Modify Deepgram request parameters.
- Modify the Anthropic cleanup prompt.
- Modify spec_engine classifier rules.
- Modify the DOCX writer.
- Recommend production defaults without measured evidence on a
  representative case.

The output is **measurement + a recommended threshold**, not a
redesign.
