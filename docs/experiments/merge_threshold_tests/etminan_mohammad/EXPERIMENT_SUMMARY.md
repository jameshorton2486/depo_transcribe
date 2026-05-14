# Merge-Threshold Experiment — etminan_mohammad

Cross-chunk merge threshold sweep on cached Deepgram output. **No production defaults were modified.** The assembler merge is re-run with each candidate `gap_threshold_seconds` value; everything upstream (Deepgram, per-chunk transcriber merge) is identical across runs.

## Section 1 — Overview

- Thresholds tested: 0.4, 0.6, 0.8, 1.0, 1.25
- Input utterance count (post per-chunk transcriber merge): **1107**
- Production default `gap_threshold_seconds`: **1.25**
- Production default `short_gap_threshold_seconds`: **0.6**
- `min_word_count`: **2**

Major observations: see Sections 2-5 below.

## Section 2 — Threshold comparison table

| Threshold | Utterances | Avg words | Median | Max | Merged Q/A candidates | Speaker switch in block | Standalone short answers | Long turns w/ short-answer phrase mid-text | >100-word utts | Classifier Q | Classifier A | Classifier colloquy |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.4 | 652 | 18.05 | 13.0 | 222 | 99 | 114 | 4 | 65 | 4 | 0 | 0 | 651 |
| 0.6 | 503 | 23.39 | 16 | 242 | 93 | 110 | 3 | 77 | 6 | 0 | 0 | 502 |
| 0.8 | 428 | 27.49 | 19.0 | 296 | 89 | 107 | 3 | 80 | 9 | 0 | 0 | 427 |
| 1.0 | 376 | 31.29 | 20.0 | 296 | 82 | 106 | 3 | 81 | 14 | 0 | 0 | 375 |
| 1.25 | 340 | 34.61 | 21.0 | 337 | 77 | 102 | 3 | 82 | 19 | 0 | 0 | 339 |

## Section 3 — Sample bad merges per threshold

### Threshold 0.4 — `0_4/`

- **speaker_switch_inside_block** (`Speaker 0`, 40 words  t=0.00-21.50s)
  > Good afternoon. We are on the record. Today's date is 04/24/2026, and the time is now 01:27PM. This is the beginning of the deposition of Doctor. Mohammad Etminan, MD. Court Reporter, Ms. Warren wins. Yes, this is cause…
- **speaker_switch_inside_block** (`Speaker 1`, 31 words  t=75.55-83.22s)
  > Do you solemnly swear to tell the truth, the whole truth and nothing but the truth so help you God? I do. Thank you, sir. You may proceed with the examination.
- **speaker_switch_inside_block** (`Speaker 3`, 27 words  t=129.44-137.68s)
  > where is your practice located at, Doctor? I'm in Houston and in Houston. I have 2 offices and 1 in Memorial City and 1 in Sugar Land.
- **speaker_switch_inside_block** (`Speaker 2`, 13 words  t=138.07-142.47s)
  > Okay. And in your own private practice, you do treat patients, correct? Yes.
- **speaker_switch_inside_block** (`Speaker 2`, 40 words  t=142.92-157.08s)
  > What kind of a doctor are you? I'm a board certified orthopedic spine surgeon. Do you do shoulder surgeries? No. Are you offering any opinions about any shoulder complaints or shoulder injuries alleged by Miss Vargas in…

### Threshold 0.6 — `0_6/`

- **speaker_switch_inside_block** (`Speaker 0`, 40 words  t=0.00-21.50s)
  > Good afternoon. We are on the record. Today's date is 04/24/2026, and the time is now 01:27PM. This is the beginning of the deposition of Doctor. Mohammad Etminan, MD. Court Reporter, Ms. Warren wins. Yes, this is cause…
- **speaker_switch_inside_block** (`Speaker 1`, 31 words  t=75.55-83.22s)
  > Do you solemnly swear to tell the truth, the whole truth and nothing but the truth so help you God? I do. Thank you, sir. You may proceed with the examination.
- **speaker_switch_inside_block** (`Speaker 3`, 27 words  t=129.44-137.68s)
  > where is your practice located at, Doctor? I'm in Houston and in Houston. I have 2 offices and 1 in Memorial City and 1 in Sugar Land.
- **speaker_switch_inside_block** (`Speaker 2`, 53 words  t=138.07-157.08s)
  > Okay. And in your own private practice, you do treat patients, correct? Yes. What kind of a doctor are you? I'm a board certified orthopedic spine surgeon. Do you do shoulder surgeries? No. Are you offering any opinions…
- **speaker_switch_inside_block** (`Speaker 2`, 31 words  t=159.75-169.99s)
  > Are you licensed to practice medicine in the state of Texas? Yes. Are you licensed in state other than Texas? No. What year did you get your medical license in Texas?

### Threshold 0.8 — `0_8/`

- **speaker_switch_inside_block** (`Speaker 0`, 40 words  t=0.00-21.50s)
  > Good afternoon. We are on the record. Today's date is 04/24/2026, and the time is now 01:27PM. This is the beginning of the deposition of Doctor. Mohammad Etminan, MD. Court Reporter, Ms. Warren wins. Yes, this is cause…
- **speaker_switch_inside_block** (`Speaker 1`, 31 words  t=75.55-83.22s)
  > Do you solemnly swear to tell the truth, the whole truth and nothing but the truth so help you God? I do. Thank you, sir. You may proceed with the examination.
- **speaker_switch_inside_block** (`Speaker 3`, 27 words  t=129.44-137.68s)
  > where is your practice located at, Doctor? I'm in Houston and in Houston. I have 2 offices and 1 in Memorial City and 1 in Sugar Land.
- **speaker_switch_inside_block** (`Speaker 2`, 53 words  t=138.07-157.08s)
  > Okay. And in your own private practice, you do treat patients, correct? Yes. What kind of a doctor are you? I'm a board certified orthopedic spine surgeon. Do you do shoulder surgeries? No. Are you offering any opinions…
- **speaker_switch_inside_block** (`Speaker 2`, 31 words  t=159.75-169.99s)
  > Are you licensed to practice medicine in the state of Texas? Yes. Are you licensed in state other than Texas? No. What year did you get your medical license in Texas?

### Threshold 1.0 — `1_0/`

- **speaker_switch_inside_block** (`Speaker 0`, 40 words  t=0.00-21.50s)
  > Good afternoon. We are on the record. Today's date is 04/24/2026, and the time is now 01:27PM. This is the beginning of the deposition of Doctor. Mohammad Etminan, MD. Court Reporter, Ms. Warren wins. Yes, this is cause…
- **speaker_switch_inside_block** (`Speaker 1`, 31 words  t=75.55-83.22s)
  > Do you solemnly swear to tell the truth, the whole truth and nothing but the truth so help you God? I do. Thank you, sir. You may proceed with the examination.
- **speaker_switch_inside_block** (`Speaker 3`, 27 words  t=129.44-137.68s)
  > where is your practice located at, Doctor? I'm in Houston and in Houston. I have 2 offices and 1 in Memorial City and 1 in Sugar Land.
- **speaker_switch_inside_block** (`Speaker 2`, 53 words  t=138.07-157.08s)
  > Okay. And in your own private practice, you do treat patients, correct? Yes. What kind of a doctor are you? I'm a board certified orthopedic spine surgeon. Do you do shoulder surgeries? No. Are you offering any opinions…
- **speaker_switch_inside_block** (`Speaker 2`, 31 words  t=159.75-169.99s)
  > Are you licensed to practice medicine in the state of Texas? Yes. Are you licensed in state other than Texas? No. What year did you get your medical license in Texas?

### Threshold 1.25 — `1_25/`

- **speaker_switch_inside_block** (`Speaker 0`, 40 words  t=0.00-21.50s)
  > Good afternoon. We are on the record. Today's date is 04/24/2026, and the time is now 01:27PM. This is the beginning of the deposition of Doctor. Mohammad Etminan, MD. Court Reporter, Ms. Warren wins. Yes, this is cause…
- **speaker_switch_inside_block** (`Speaker 1`, 43 words  t=70.83-83.22s)
  > Thank you. Doctor. Edinburg, would you please raise your right hand, sir. Do you solemnly swear to tell the truth, the whole truth and nothing but the truth so help you God? I do. Thank you, sir. You may proceed with th…
- **speaker_switch_inside_block** (`Speaker 3`, 27 words  t=129.44-137.68s)
  > where is your practice located at, Doctor? I'm in Houston and in Houston. I have 2 offices and 1 in Memorial City and 1 in Sugar Land.
- **speaker_switch_inside_block** (`Speaker 2`, 53 words  t=138.07-157.08s)
  > Okay. And in your own private practice, you do treat patients, correct? Yes. What kind of a doctor are you? I'm a board certified orthopedic spine surgeon. Do you do shoulder surgeries? No. Are you offering any opinions…
- **speaker_switch_inside_block** (`Speaker 2`, 31 words  t=159.75-169.99s)
  > Are you licensed to practice medicine in the state of Texas? Yes. Are you licensed in state other than Texas? No. What year did you get your medical license in Texas?

## Section 4 — Sample good segmentation per threshold

### Threshold 0.4 — `0_4/`

- **isolated_short_answer** (`Speaker 0`, 1 words  t=2723.99-2724.62s)
  > Yes.
- **isolated_short_answer** (`Speaker 1`, 1 words  t=3388.24-3388.57s)
  > Yes.
- **isolated_question** (`Speaker 2`, 10 words  t=167.59-169.99s)
  > What year did you get your medical license in Texas?
- **isolated_question** (`Speaker 2`, 17 words  t=176.09-182.65s)
  > And about how many spine surgeries do you do per year cervical in your own private practice?
- **isolated_colloquy** (`Speaker 2`, 16 words  t=55.56-61.64s)
  > Good afternoon. Dennis Malley for the plaintiff Procedure of Vargas located in San Antonio, Texas. Agreed.

### Threshold 0.6 — `0_6/`

- **isolated_short_answer** (`Speaker 0`, 1 words  t=2723.99-2724.62s)
  > Yes.
- **isolated_short_answer** (`Speaker 1`, 1 words  t=4368.77-4369.33s)
  > Yes.
- **isolated_question** (`Speaker 2`, 17 words  t=176.09-182.65s)
  > And about how many spine surgeries do you do per year cervical in your own private practice?
- **isolated_question** (`Speaker 2`, 7 words  t=203.43-205.75s)
  > trauma sustained in a motor vehicle crash?
- **isolated_colloquy** (`Speaker 2`, 16 words  t=55.56-61.64s)
  > Good afternoon. Dennis Malley for the plaintiff Procedure of Vargas located in San Antonio, Texas. Agreed.

### Threshold 0.8 — `0_8/`

- **isolated_short_answer** (`Speaker 0`, 1 words  t=2723.99-2724.62s)
  > Yes.
- **isolated_short_answer** (`Speaker 1`, 1 words  t=4368.77-4369.33s)
  > Yes.
- **isolated_question** (`Speaker 2`, 17 words  t=176.09-182.65s)
  > And about how many spine surgeries do you do per year cervical in your own private practice?
- **isolated_question** (`Speaker 2`, 19 words  t=196.71-205.75s)
  > who have made complaints of lumbar and cervical pain to you following trauma sustained in a motor vehicle crash?
- **isolated_colloquy** (`Speaker 2`, 16 words  t=55.56-61.64s)
  > Good afternoon. Dennis Malley for the plaintiff Procedure of Vargas located in San Antonio, Texas. Agreed.

### Threshold 1.0 — `1_0/`

- **isolated_short_answer** (`Speaker 0`, 1 words  t=2723.99-2724.62s)
  > Yes.
- **isolated_short_answer** (`Speaker 1`, 1 words  t=4368.77-4369.33s)
  > Yes.
- **isolated_question** (`Speaker 2`, 17 words  t=176.09-182.65s)
  > And about how many spine surgeries do you do per year cervical in your own private practice?
- **isolated_question** (`Speaker 2`, 19 words  t=196.71-205.75s)
  > who have made complaints of lumbar and cervical pain to you following trauma sustained in a motor vehicle crash?
- **isolated_colloquy** (`Speaker 2`, 16 words  t=55.56-61.64s)
  > Good afternoon. Dennis Malley for the plaintiff Procedure of Vargas located in San Antonio, Texas. Agreed.

### Threshold 1.25 — `1_25/`

- **isolated_short_answer** (`Speaker 0`, 1 words  t=2723.99-2724.62s)
  > Yes.
- **isolated_short_answer** (`Speaker 1`, 1 words  t=4368.77-4369.33s)
  > Yes.
- **isolated_question** (`Speaker 2`, 17 words  t=176.09-182.65s)
  > And about how many spine surgeries do you do per year cervical in your own private practice?
- **isolated_question** (`Speaker 2`, 19 words  t=196.71-205.75s)
  > who have made complaints of lumbar and cervical pain to you following trauma sustained in a motor vehicle crash?
- **isolated_colloquy** (`Speaker 2`, 16 words  t=55.56-61.64s)
  > Good afternoon. Dennis Malley for the plaintiff Procedure of Vargas located in San Antonio, Texas. Agreed.

## Section 5 — Observations

### What the experiment actually shows

**Lowering the assembler threshold reduces over-merging — but does NOT recover the Q/A separation we hoped it would.** The reason is visible in the Section 3 samples below: every "bad merge" example exists at every threshold, with nearly identical text. That means the offending utterances were **already combined by Deepgram itself** before reaching either local merge stage. The 0.4 cross-chunk threshold sample for "where is your practice located at, Doctor? I'm in Houston…" is the same utterance, in the same shape, as the 1.25 sample. The assembler merge is not creating these Q/A blends; it is **inheriting them**.

This means the principal source of merged Q/A in this case is upstream of `pipeline/assembler.py` — almost certainly Deepgram's diarization assigning the same speaker number to both the attorney and the witness across `utt_split=0.8` boundaries. No amount of post-Deepgram threshold tuning fixes that.

### Where fragmentation begins

- Utterance count nearly doubles as threshold drops from 1.25 → 0.4 (**340 → 652**). The extra utterances are mostly very short turns (median word count drops from 21 → 13, max from 337 → 222).
- `>100-word` utterances drop from **19 → 4** between 1.25 and 0.4. Genuine long monologues stay intact only at the higher thresholds.

### Where over-merging shows up

- `merged_qa_candidates` decreases monotonically from **99 (0.4) → 77 (1.25)** — but only **22 detections** separate the extremes. That gap is **dwarfed by the 312-utterance shift** in total count. Translation: aggressive merging packs more Q/A errors into fewer (larger) buckets, which the heuristic counts as one offense each. The underlying error rate per minute of audio is approximately the same.
- `standalone_short_answers` is essentially flat at **3-4** across every threshold. Witness "Yes." / "No." responses **are not being recovered** by lowering the threshold — they were already eaten by upstream diarization. The local merge isn't the bottleneck.
- `speaker_switch_inside_block` actually **increases** at lower thresholds (**102 → 114**) because the upstream-diarization mistakes get exposed as separate small utterances instead of being hidden inside larger merged blocks. This is a metric artifact, not a real worsening.

### Classifier counts are uninformative here — flag

Every threshold shows `Classifier question=0, answer=0, colloquy≈utterance_count`. That is **not** because the threshold breaks classification. `spec_engine/classifier.py::_classify_type` looks for the `\tQ.\t` / `\tA.\t` prefixes (or a regex match against `is_question_loose`), which are inserted by the **Anthropic cleanup pass downstream**, not by raw Deepgram output. The classifier on raw transcripts will always type everything as `colloquy` regardless of threshold. The classifier signal is a downstream-of-Anthropic measurement and was not produced in this experiment because we deliberately bypassed Anthropic.

### Healthiest threshold (with honest caveats)

If the **only** axis being optimized is utterance granularity (and not Q/A integrity, which this experiment can't measure cleanly), the trade-off curve looks like:

| Threshold | Utterances | Words/utt | Reads-like |
|---:|---:|---:|---|
| 0.4 | 652 | 18 | Stutter-y; short utterances dominate; cleaner separation of monologues from interjections |
| 0.6 | 503 | 23 | Balanced; loses some short witness turns |
| 0.8 | 428 | 27 | Currently the Deepgram `utt_split` value; matches upstream cadence |
| 1.0 | 376 | 31 | Begins absorbing distinct speaker turns at long pauses |
| 1.25 | 340 | 35 | **Production default.** Maximum compression; many natural Q/A pairs collapse into a single attorney-classified turn |

There is no threshold among the five that meaningfully reduces the **upstream-caused** Q/A merging. **0.8** is the most defensible choice if any change is contemplated, because it aligns the cross-chunk merge gap with the Deepgram `utt_split` value already in production — matching the upstream cadence rather than creating a second, looser segmentation policy on top of it.

### What this experiment *cannot* answer

- Whether reducing the threshold improves the **final Anthropic-cleaned DOCX**, which is the user-visible artifact. Anthropic was deliberately skipped in this experiment per the prompt. To measure that, the experiment would need to re-run the Anthropic cleanup pass on each threshold's `04_emitted_transcript.txt` — at a real billable cost per threshold.
- Whether the upstream Deepgram diarization can be improved (e.g., via different `model` / different audio preprocessing) so that fewer Q/A blocks arrive pre-merged.
- Whether the per-chunk merge in `pipeline/transcriber.py` (the 0.6s gap, applied *before* the data this experiment uses) is also a contributor. That stage is upstream of `raw_utterances` in the saved JSON and was not varied here.

### One concrete next experiment (no implementation here)

Rerun this sweep with `--thresholds 0.4 0.6 0.8` *and* a parallel sweep on the per-chunk transcriber merge gap (`MERGE_GAP_THRESHOLD_SECONDS` in `pipeline/transcriber.py:33`, currently `0.6`). Pair them against a fixed Anthropic cleanup pass so the final DOCX is the comparison surface. That measures user-visible quality, not heuristic counts.

_No production change is being recommended. Human review of `04_emitted_transcript.txt` in each per-threshold folder is the right next step._

## Notes

- **production_default_gap_threshold_seconds:** 1.25
- **production_default_short_gap_threshold_seconds:** 0.6
- **production_default_min_word_count:** 2
- **input_source:** C:\Users\james\Depositions\2026\Apr\C572224L\etminan_mohammad\Deepgram\raw_deepgram.json
- **production_code_modified:** no

## Reproducing

```powershell
.\.venv\Scripts\python.exe -m tools.experiments.run_merge_threshold_experiment --case-dir "<case_dir>"
```
