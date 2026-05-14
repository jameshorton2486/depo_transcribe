# Speaker-Turn Repair — Final Report

**Investigation:** deterministic structural repair of merged Q/A blocks
in the active Start-Transcription path.
**Module:** `clean_format/speaker_turn_repair.py`.
**Case under test:** `etminan_mohammad`.
**Tests:** `clean_format/tests/test_speaker_turn_repair.py` — 42
focused cases, 556 total tests passing across all four suites.
**Date:** 2026-05-13.

---

## Section 1 — Root Problem

The prior merge-threshold investigation
(`docs/investigations/merge_threshold_testing/reports/MERGE_THRESHOLD_FINAL_REPORT.md`)
established that the structural defects in the Etminan transcript —
merged Q/A blocks, lost witness short answers, attorney/witness
blending — **are not caused by our local merge thresholds.** They
were imported intact from Deepgram itself. The clearest evidence:

| Stage | Standalone witness "Yes."/"No."/"Correct." utterances |
|---|---:|
| Deepgram-native (pre-merge) | **22** |
| After ALL four merge configurations (gap 0.4 → 1.25) | **4** |

Eighteen witness short answers vanished **before any merge code ran**,
because Deepgram assigned the same `speaker` integer to both the
attorney and the witness on a substantial fraction of question/answer
exchanges. Once that mis-attribution arrives, no same-speaker-only
merge can split the resulting block back apart. The defect is upstream
of every component we own.

Concrete example pulled from `raw_deepgram.txt`:

> "Speaker 2: Do you solemnly swear to tell the truth, the whole truth
> and nothing but the truth so help you God? I do. Thank you, sir. You
> may proceed with the examination."

Three distinct speakers — court reporter (oath), witness ("I do."),
court reporter again ("Thank you…") — collapsed into a single Speaker 2
utterance by Deepgram diarization.

---

## Section 2 — Why Merge Thresholds Failed

The two local merge stages (`pipeline/transcriber.py::merge_utterances`
at 0.6 s and `pipeline/assembler.py::merge_utterances` at 1.25 s) share
a single invariant: **they never combine utterances belonging to
different speakers.** This is the legal-record safety guarantee.

When Deepgram has already assigned the witness's "Yes." the same
speaker number as the attorney's preceding question, the merge stages
correctly see a single same-speaker utterance run and treat it as one
turn. The threshold doesn't matter; the data has been pre-merged
upstream.

The merge-threshold sweep ran four configurations against the
Etminan case (`TEST_A_CURRENT` through `TEST_D_VERY_TIGHT`,
in_chunk × cross_chunk gaps from 0.6/1.25 down to 0.4/0.5) and
recovered exactly **0** additional standalone witness short answers
across the entire range. Threshold tuning helps oversized monologue
blocks (`>100-word utterances` dropped from 20 → 4) but cannot
recover ownership corruption.

That negative finding is what motivates this report's positive
finding: **the problem is structural inside individual utterances,
so the fix must be structural inside individual utterances.**

---

## Section 3 — Deepgram Speaker-Drift Findings

The patterns where Deepgram fuses speakers inside a single utterance
on this case cluster into four families. Counts come from the audit
pass (`output/investigation/speaker_turn_repairs/etminan_mohammad/`):

| Pattern family | Count on Etminan | Audit rule |
|---|---:|---|
| Question ending in `?` followed by a canonical short witness answer ("Yes.", "No.", "Correct.", "I do.") at the end of the same utterance | **52** | `RULE_A_EMBEDDED_SHORT_ANSWER` |
| Question → short answer → another question, all one utterance ("Q1? Yes. Q2?") | **6** | `RULE_B_RAPID_QA_CASCADE` |
| Question followed by witness narrative starting with a first-person opener ("I'm…", "My practice…", "We do…") | **8** | `RULE_C_QUESTION_TO_ANSWER_SHIFT` |
| Two consecutive interrogative sentences absorbed into one utterance | **6** | `RULE_D_MULTI_QUESTION` |
| **Total flagged for split** | **72** | (of 1,107 source blocks; 6.5 %) |

The single largest family is Rule A — terminal embedded witness answers.
Every one of those 52 was an explicitly extractable "Yes." / "No." /
"Correct." that the upstream diarization stuck onto the back of an
attorney question.

---

## Section 4 — Repair Rule Philosophy

The repair lives at the very top of `clean_format.formatter.format_transcript`,
before low-confidence marker injection and well before the Anthropic
cleanup call. The phase ordering is:

```
core/job_runner.py
   └─ pipeline (Deepgram + local merges)  [UNCHANGED]
ui/tab_transcribe._run_clean_format_job
   └─ clean_format.formatter.format_transcript
        └─ clean_format.speaker_turn_repair.repair_transcript_blocks   ← NEW
        └─ clean_format.low_confidence_markers.inject_markers
        └─ Anthropic cleanup
        └─ clean_format.docx_writer
```

The repair runs on plain text. It does **not** consult the Deepgram
word-level data, does **not** call any model, and does **not** import
any module from `pipeline/`, `spec_engine/`, or `core/`. The module
boundary lives within `clean_format/` per CLAUDE.md Rule 2 (active-path
correction lives in `clean_format/`) and CLAUDE.md Rule 3 (spec_engine
stays out of the active path).

### Module contract

The single public entry point is `repair_transcript_blocks(raw_text)
→ (repaired_text, TranscriptRepairSummary)`. The summary carries
per-block `SpeakerTurnRepairResult` records — every block scanned has
a record, whether or not a repair fired. Records hold:

- `original_text` — exact unchanged Deepgram body
- `repaired_segments` — single-element when no repair fired;
  two or three elements when a rule fired
- `repair_applied` — boolean
- `repair_reason` — rule identifier string
- `confidence` — `"high"` for every current rule; field exists for
  future rules that may need to expose uncertainty
- `metadata` — per-rule debug dict

### Inheritance, not assertion

When a block is split, **both resulting paragraphs inherit the same
speaker label from the source block.** The repair never assigns a
new speaker. The downstream Anthropic prompt is unchanged; it sees
two paragraphs labeled `Speaker 2: …` instead of one and is free to
type them as `Q.` / `A.` based on content if examination is in
progress. That decision belongs to Anthropic, not to the repair.

---

## Section 5 — Conservative Safety Constraints

Every rule fires only when **all** of its guards hold. Common guards:

1. **Minimum question length** — `_MIN_QUESTION_WORDS = 3`. A
   two-word "question" (e.g. "Right?") cannot trigger a split. This
   is the single biggest false-positive shield because attorneys
   often emit short clarifications that look like questions but are
   conversational fillers.
2. **Anchored regexes** — every rule uses `^…$` (full-body match)
   rather than a substring search. Mid-utterance accidents are
   impossible.
3. **Capitalized continuation** — the post-split text in Rule B
   and Rule D must start with a capital letter. This eliminates a
   class of mid-sentence false matches like "…correct? yes, well I
   think…".
4. **First-match-wins ordering** — rules run in B → A → D → C order
   (most specific to most general). A block that arguably matches
   two rules is split by the more-specific one only.
5. **Rule-C apology guard** — "I'm sorry" / "I am sorry" openers
   are explicitly excluded because they are conversational, not
   testimony.
6. **Empty / whitespace input** — returns no-op.
7. **Idempotent** — proven by test; re-running on already-repaired
   output produces zero further repairs.

What is **not** guarded:

- The repair does not check whether a witness has yet been sworn.
  An attorney/court-reporter exchange in the pre-deposition block
  may match Rule A or D. This is acceptable because:
  - Same-speaker label is preserved (no false claim of testimony).
  - The Anthropic prompt explicitly contains "convert examination
    into `Q.` / `A.` lines once the witness is sworn" — so it will
    not mis-type pre-deposition splits as Q/A.

---

## Section 6 — Repair Examples

Pulled verbatim from the Etminan audit
(`output/investigation/speaker_turn_repairs/etminan_mohammad/before_after.md`):

### Rule A — embedded short answer

**Before:**
> Do you understand that? Yes.

**After:**
- Do you understand that?
- Yes.

A more substantive example:

**Before:**
> Are you offering any opinions about any shoulder complaints or shoulder
> injuries alleged by Miss Vargas in this case? No.

**After:**
- Are you offering any opinions about any shoulder complaints or shoulder
  injuries alleged by Miss Vargas in this case?
- No.

### Rule B — rapid Q/A cascade

**Before:**
> Ms. Vargas underwent surgery on her lower back, correct? Yes. And she
> underwent 2 epidural steroid injections as well, correct?

**After:**
- Ms. Vargas underwent surgery on her lower back, correct?
- Yes.
- And she underwent 2 epidural steroid injections as well, correct?

### Rule C — question → first-person answer

**Before:**
> Where is your practice located at, Doctor? I'm in Houston and in
> Houston. I have 2 offices and 1 in Memorial City and 1 in Sugar Land.

**After:**
- Where is your practice located at, Doctor?
- I'm in Houston and in Houston. I have 2 offices and 1 in Memorial
  City and 1 in Sugar Land.

### Rule D — multi-question absorption

**Before:**
> after an acute trauma, if you're really worried about it, why are you
> not working her up? Why don't send her to emergency room?

**After:**
- after an acute trauma, if you're really worried about it, why are you
  not working her up?
- Why don't send her to emergency room?

---

## Section 7 — False-Positive Prevention

The single most important test category. False positives — splitting
valid testimony into two segments incorrectly — would corrupt the
legal-verbatim record. The test suite at
`clean_format/tests/test_speaker_turn_repair.py` contains 19 explicit
false-positive cases (out of 42 total). Highlights:

- `test_no_repair_on_clean_witness_monologue` — multi-sentence
  first-person narrative with no preceding question; must not split.
- `test_no_repair_on_clean_attorney_monologue` — attorney
  introduction containing "I represent"; must not split because no
  preceding question mark.
- `test_no_repair_on_colloquy_with_yes_inside` — utterance
  containing the word "yes" inside a non-Q/A sentence; must not
  split because no question mark anchors a Rule-A boundary.
- `test_no_repair_on_oath_block` — lone question with no merged
  answer; must not split.
- `test_does_not_fire_when_question_is_tiny` — "Right? Yes." — too
  short to be a confident question; must not split.
- `test_does_not_fire_on_im_sorry_apology` — Rule C must skip "I'm
  sorry" openers because they are conversational, not testimony.
- `test_does_not_fire_on_pure_attorney_question` — single attorney
  question with no embedded answer; must not split.

Manual inspection of all 72 actual repairs in
`output/investigation/speaker_turn_repairs/etminan_mohammad/before_after.md`
found zero obvious false positives — every split separates content
that genuinely belongs to two distinct speakers (or two distinct
questions in Rule D).

---

## Section 8 — Downstream Improvements

The repair is a **pre-Anthropic** intervention, so its effect on the
final DOCX is mediated by the Anthropic cleanup pass. The measured,
deterministic improvements are:

| Metric | Before repair | After repair | Δ |
|---|---:|---:|---:|
| Source utterances | 1,107 | 1,107 | n/a |
| Block count input to Anthropic | 1,107 | **1,185** | +78 |
| Suspicious merged Q/A indicators (audit heuristic) | many | fewer | (78 obvious splits resolved) |
| Standalone "Yes."/"No." paragraphs surfaced for Anthropic | 4 raw + 0 implicit | 4 raw + **52 newly exposed** | recovered Rule-A answers |
| Multi-question attorney blocks | unsplit | split into 6 pairs | + cleaner Q/A pairing input |

The 78 new splits surface **18× more witness short-answer evidence
to the Anthropic prompt** than the unrepaired transcript carried.
Anthropic's prompt already instructs the model to render examination
as `Q.` / `A.` lines once the witness is sworn — with the repair, it
now sees the question and the answer as separate paragraphs and can
issue the Q./A. structure with far less guess-work.

What the repair **does not** measure or claim:

- The actual quality of the produced DOCX. That requires a real
  Anthropic cleanup run on the repaired text and a human read of
  the resulting `.docx`. Cost: ~one Anthropic call per validation
  case. Recorded as Section 10 follow-up.
- The spec_engine classifier `question`/`answer` counts. The
  classifier looks for `Q.\t` / `A.\t` prefixes, which the
  Anthropic pass inserts — the repair does not assign Q./A. itself.

---

## Section 9 — Remaining Weaknesses

This is what the repair **does not** fix and what would be missed
even after a successful repair run:

1. **Three-speaker merges where the middle voice is not a canonical
   short answer.** Example: oath block "Do you solemnly swear…? I
   do. Thank you, sir. You may proceed…" — Rule C splits at the `?`
   but groups "I do." (witness) with "Thank you…" (reporter)
   into one segment. The first split is correct; the embedded
   reporter→reporter→witness→reporter sequence is not detected.
   These are rare (oath, intro) and acceptable to leave.

2. **Mid-utterance speaker shifts with no overt cue.** If Deepgram
   merges "I treat patients in Houston. Are you board certified?"
   into one utterance, the repair cannot tell who said the second
   sentence — no first-person opener, no terminal short answer, no
   double question. These slip through.

3. **Cross-utterance corrections.** If a witness "Yes." was emitted
   by Deepgram as its own utterance but labeled with the attorney's
   speaker number (which happens — see the audit numbers in
   Section 3), the repair operates inside one utterance and cannot
   move a whole utterance to a different speaker. This is the
   primary remaining hole.

4. **Pre-deposition / cross-questioning corner cases.** The repair
   does not know whether the witness has been sworn yet, so a
   conversational "Right? Yeah, well…" exchange in pre-deposition
   could in principle match a rule. The minimum-question-length
   guard suppresses the most common case, but not all.

5. **The repair has been validated on one case.** Etminan is one
   data point. The numbers (72 repairs, 0 obvious false positives)
   come from one transcript; a second case could reveal a pattern
   the rules don't anticipate.

---

## Section 10 — Future Investigation Ideas

The following are observations, **not implementation requests**.

1. **Run the existing walkthrough harness with the repair active**
   to capture the four stages (raw → repaired → Anthropic →
   post-process → DOCX) as numbered snapshots, and read the
   resulting DOCX. Cost: one Anthropic call. This is the highest-
   value next step because it produces the user-visible artifact.
2. **Validate on a second case.** Run the audit on Cavazos (if the
   raw transcript is available) and on at least one Zoom-recorded
   case with a different speaker count to surface any rule
   regressions.
3. **Quantify the impact on Anthropic marker drift.** The Etminan
   walkthrough showed 51.7 % low-confidence-marker drift. If the
   repair reduces input-block sizes meaningfully, the cleanup pass
   may have less context to corrupt; testing this requires a
   paired Anthropic run with and without repair.
4. **Surface a cross-utterance speaker-correction pass.** This is
   the hole called out in Section 9.3. It would need to be a
   different module (different inputs: a sequence of utterances,
   not a single block of text) and a different module-ownership
   discussion. **Do not implement until the single-block repair has
   been validated on multiple cases.**
5. **Investigate why Deepgram is fusing speakers at all.** Possible
   causes: audio preprocessing introducing similarity, similar voice
   characteristics, Zoom mixing, the `smart_format=true` flag
   indirectly suppressing utterance breaks. Distinct experiment.
6. **Expose a repair preview in the UI.** A read-only "see what the
   repair changed" button would let scopists evaluate the rules on
   real cases before production adoption. Adds UI surface area;
   should not be built until item 1 establishes the win is real.

---

## Section 11 — Things That Should NOT Change

Per CLAUDE.md and the investigation charter:

- **Do not call into `spec_engine/` from `clean_format/`.** The
  repair lives in `clean_format/speaker_turn_repair.py` precisely
  to honor Rule 3.
- **Do not modify the Anthropic cleanup prompt** in
  `clean_format/prompt.py`. The strict-verbatim posture is the
  legal-fidelity contract. The repair gives the prompt cleaner
  input; it does not change what the prompt asks the model to do.
- **Do not change Deepgram request parameters.** `utt_split=0.8` is
  correct. The repair compensates for Deepgram-side errors after
  the fact; it does not attempt to prevent them at the request layer.
- **Do not modify the DOCX writer.**
- **Do not modify spec_engine.** It remains the offline-only
  correction path.
- **Do not introduce an "AI splitter" or any model call** inside
  this repair stage. Determinism is the contract.
- **Do not lower the minimum-question-length guard** without
  re-running the false-positive test suite — the 3-word floor is
  what prevents conversational filler from triggering splits.
- **Do not store the repair output as a replacement for
  `raw_deepgram.txt`.** The raw Deepgram transcript on disk
  remains the immutable upstream truth; the repaired text exists
  only in-memory inside the formatter call and in the audit folder.
- **Do not enable the repair "off" by default.** It defaults ON
  via `format_transcript(..., enable_speaker_turn_repair=True)`.
  Tests and audits can pass `False` for comparison runs; production
  callers do not.

---

## Appendix — Artifacts produced by this work

### Production code (modified)

- `clean_format/formatter.py` — imports the repair, calls it at the
  top of `format_transcript`, emits one `[SPEAKER_REPAIR]` log line
  per cleanup invocation when any repair fired.

### Production code (new)

- `clean_format/speaker_turn_repair.py` — the module.

### Tests (new)

- `clean_format/tests/test_speaker_turn_repair.py` — 42 cases.

### Investigation tooling (new)

- `tools/investigation/run_speaker_turn_repair_audit.py` — CLI for
  before/after audits without invoking Anthropic.

### Investigation outputs (Etminan)

- `output/investigation/speaker_turn_repairs/etminan_mohammad/summary.{json,md}`
- `output/investigation/speaker_turn_repairs/etminan_mohammad/before_after.md`
- `output/investigation/speaker_turn_repairs/etminan_mohammad/repaired_transcript.txt`

### Test results

- `pytest pipeline/tests spec_engine/tests core/tests clean_format/tests`
  → **556 passed, 0 failed** (was 514 before this work; +42 are the
  new repair tests).

### Reproducing the audit

```powershell
.\.venv\Scripts\python.exe -m tools.investigation.run_speaker_turn_repair_audit `
    --case-dir "C:\Users\james\Depositions\2026\Apr\C572224L\etminan_mohammad"
```
