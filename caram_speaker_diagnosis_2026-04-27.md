# Caram Speaker-Mapping Diagnosis — End-of-Day Findings

Generated: 2026-04-27 (end of session)
Status: NOT COMMITTED. Read-only diagnostic for tomorrow's session.
Subject: What's actually wrong with Caram's speaker labels.

---

## Correction to earlier diagnosis

Earlier in session I claimed `_corrected.txt` had bare `Speaker 0:` /
`Speaker 1:` labels and that speaker_mapping wasn't applied. That
diagnosis was based on transcript content the operator pasted that
**did not match** the actual file content. Both Pass 1
`_corrected.txt` and Pass 2 `temp/caram_substructure_corrected.txt`
have **mapped names** (`MS. MALONEY:`, `MR. DUNNELL:`, `THE REPORTER:`,
`MS. KARAM:`). The pipeline's speaker_mapper is functioning.

**Apologies for the false alarm.** The recovery: I read 60 lines of
the actual file (lines 800–860, around the "back on the record"
passage the operator referenced) and identified the real problem
below.

---

## The real problem: diarization instability + wrong speaker_map values

### Evidence — `_corrected.txt` lines 809–841

```
Dr. Karam, I wanted to ask you about your second encounter, uh, with Hannah.
Q.  When were you and when and how were you notified that she had come to the hospital?
        THE REPORTER:  I was notified that October the second, um, I received a phone call from Dr. Anders that Hannah had arrived...
```

The label `THE REPORTER:` is on the **witness's answer**. The
witness (Dr. Caram) is being attributed to the speaker_map slot
labeled "THE REPORTER".

A few lines later:

```
        MS. MALONEY:  I was at our office.   ← witness's answer to "where were you?"
        ...
        THE REPORTER:  Labor and delivery?   ← witness continuing
```

In the same exchange, the witness's voice is split across **speaker_id
1 (THE REPORTER), speaker_id 2 (MS. MALONEY), and speaker_id 4 (MS.
KARAM)**. Deepgram's diarization assigned the witness to three
different speaker IDs across the same passage.

### Compounding factor: speaker_map values themselves are wrong

Current `ufm.speaker_map`:

```
"0": "THE VIDEOGRAPHER"
"1": "THE REPORTER"     ← actually predominantly the WITNESS
"2": "MS. MALONEY"      ← attorney + sometimes witness's answers slip in
"3": "MR. DUNNELL"
"4": "MS. KARAM"        ← witness, but typo: should be DR. CARAM
```

The map looks like it was built from a positional template assuming
the standard deposition opening order (videographer, reporter,
attorneys, witness). Deepgram's actual assignment in this audio
doesn't follow that order. Witness is on speaker_id 1 most often,
not speaker_id 4 as the positional default assumed.

### Why even fixing the map won't fully fix the output

If the operator changes "1" to "DR. CARAM" and "4" to "DR. CARAM"
(both pointing at the witness), they'd recover witness attribution
on those lines — but lose attribution for the actual reporter, who
also speaks on speaker_id 1 (the swearing-in passage). And speaker_id
2 (MS. MALONEY) genuinely is MS. MALONEY for *most* of her lines, so
remapping it would break her attribution.

This is the structural ceiling of post-hoc speaker_map repair when
the underlying diarization is unstable. The signal is mixed at the
speaker_id level; no per-id remapping can separate it back out.

---

## Other quality issues spotted in the same passages

### Name garbles needing confirmed_spellings entries

| Garbled in transcript | Correct | Source-of-truth field |
|---|---|---|
| `Biana Caram` (filename + line 4) | `Bianca Caram` | `ufm.witness_name = 'Bianca Caram, M.D.'` |
| `Bianca Karam` / `Dr. Karam` / `MS. KARAM` (throughout) | `Bianca Caram` / `Dr. Caram` | same |
| `Bianca Kedham, MD` (line 5, case caption) | `Bianca Caram, MD` | same |
| `Hannah Critzman` (line 5) | `Hannah K. Chrestman` | `speaker_map_suggestion.claimant` |
| `Hannah Kressman` (line 22) | `Hannah K. Chrestman` | same |
| `Hannah Kuipers` (line 27) | `Hannah K. Chrestman` (preferred) or `Hannah Kuipers` (her current maiden name per the witness's own statement at line 27) | needs operator decision |
| `Cassidy Chetzer` → was already noted; actual file shows `Cassidy Chesser` | n/a (already correct in this file) | — |
| `amifedipine` (mid-transcript, drug name) | `nifedipine` | medical |
| `a sauna` / `the Sano` (multiple) | `sonogram` | medical |
| `LNP` (twice) | `LMP` | medical (last menstrual period) |
| `Doctor.` with period before name (multiple) | `Dr.` or `Doctor` (no period) | typography rule, not spelling |

Note `Hannah Kuipers`: the witness explicitly states "Hannah goes by
her maiden name now, Hannah Kuipers" (line 25–27), so this may be a
**correct** transcription of a real alternate name, not a garble.
Worth confirming with the operator before "fixing" it.

### Diarization quality

Deepgram split the witness's voice across at least three speaker_ids
(1, 2, 4). This is the dominant cause of mis-labeled lines. Things
that *might* improve it:

- A different audio source (single-mic recording vs. Zoom
  multi-stream)
- A different speaker count hint to Deepgram
- A post-Deepgram smoother (already exists at
  `pipeline/transcriber.py:181`)

None of those are guaranteed; diarization is hard. Worth measuring
on the next case before deciding to invest.

---

## Recommended action sequence for tomorrow

In priority order:

1. **Confirm `Hannah Kuipers` vs `Hannah K. Chrestman`** with the
   operator (one-question check; the witness's own transcript
   suggests Kuipers may be the correct in-deposition reference).

2. **Update `caram_dr/source_docs/job_config.json`** (single-file
   edit, one commit):
   - Fix `ufm.speaker_map` values to match actual Deepgram speaker
     content. Operator needs to listen-spot-check or read more of
     the transcript to verify which Deepgram ID is really whom.
     Likely correct map (needs verification):
     ```
     "0": "THE VIDEOGRAPHER"
     "1": "DR. CARAM"           (was THE REPORTER)
     "2": "MS. MALONEY"
     "3": "MR. DUNNELL"
     "4": "DR. CARAM"           (was MS. KARAM)
     ```
   - Add confirmed_spellings entries for the name garbles + medical
     terms in the table above.

3. **Re-run Pass 1 only** on the existing Deepgram JSON (no
   Deepgram re-call). Verify the output reflects the corrected map.

4. **If Pass 1 looks correct, optionally re-run Pass 2.** No need
   to repeat Pass 2 measurement otherwise — the structure
   sub-reason data we have is sufficient.

5. **Investigate diarization instability separately.** Out of
   tonight's scope; document as its own workstream.

---

## What was NOT done tonight (intentionally)

- No code changes.
- No commits.
- No edits to `caram_dr/source_docs/job_config.json`.
- No edits to confirmed_spellings.
- No re-run of Pass 1 or Pass 2.

The decision matrix for *why* not: long session, multiple name
typos requiring operator confirmation, the witness's preferred
in-deposition name (Kuipers vs Chrestman) is a question only the
operator can answer, and committing wrong speaker labels to a
legal-record-adjacent file is the kind of mistake that's easy to
make at end-of-day. Better to come back fresh.

End of diagnostic. Standing by.
