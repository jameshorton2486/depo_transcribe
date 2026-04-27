# Depo-Pro House Style Guide

> **What this is.** The formatting rules Depo-Pro's pipeline enforces and
> that human scopists should apply when producing certified transcripts
> from Depo-Pro output. This document is the authoritative reference for
> our pipeline corrections and for hand-correcting `pipeline_output.txt`
> into `ground_truth.txt` during corpus building.
>
> **What this is not.** A comprehensive court reporting style manual.
> Court reporters using Depo-Pro should also consult their own copies of
> standard references: Morson's English Guide for Court Reporters, the
> UFM (Uniform Format Manual) for Texas, NCRA's Transcript Format
> Guidelines, and any firm-specific style guides their employers maintain.
> This guide captures only the subset of rules that affect Depo-Pro's
> automated output and our corpus-driven rule promotion process.

---

## How to use this guide

When producing a `ground_truth.txt` for the training corpus, apply these
rules consistently. When the categorized diff tooling reports a divergence
between pipeline output and ground truth, tag the fix with the relevant
section number from this guide so we can track which rules our pipeline
enforces well and which need work.

When proposing new MULTIWORD_CORRECTIONS rules or AI Correct prompt
changes, cite the section here that the rule enforces. Rules without a
documented basis in this guide should be questioned during the promotion
review.

---

## 1. Speaker Labels

### 1.1 Court reporter

Use **THE REPORTER:** for the court reporter's on-record statements.
Do not use "THE COURT REPORTER:".

```
Correct:    THE REPORTER: We are now on the record.
Incorrect:  THE COURT REPORTER: We are now on the record.
```

### 1.2 Witness

Use the surname with title:

```
MR. SINGH:    (for male witness)
MS. KARAM:    (for female witness)
DR. KARAM:    (when the witness's professional title is on the record)
```

Use **THE WITNESS:** when the witness speaks but is not in question-and-
answer format (e.g., responding to the court directly, taking the oath).

### 1.3 Attorneys

Use the surname with title. Match the title the attorney uses for
themselves on the record:

```
MR. GONZALEZ:
MS. MALONEY:
```

If two attorneys share a surname, distinguish by full name on first
appearance, then continue with surname:

```
First appearance: MR. JAMES GONZALEZ:
Subsequent:       MR. GONZALEZ:
```

### 1.4 Judge

Use **THE COURT:** for the presiding judge's on-record statements,
regardless of the judge's actual title.

### 1.5 Videographer

Use **THE VIDEOGRAPHER:** for the videographer's on-record statements
during a video deposition.

---

## 2. Examination Headers

Each examination section begins with a centered, all-caps header:

```
                              EXAMINATION

BY MR. GONZALEZ:

   Q.   Please state your full name.
   A.   Peter Durai Singh.
```

Subsequent examinations use:

```
                          CROSS-EXAMINATION

BY MR. PENA:

   Q.   ...
```

```
                        REDIRECT EXAMINATION

BY MR. GONZALEZ:

   Q.   ...
```

```
                        RECROSS-EXAMINATION

BY MR. PENA:

   Q.   ...
```

The `BY [ATTORNEY]:` line appears once at the start of each examination
and again any time a different attorney takes over questioning.

---

## 3. Q/A Structure

### 3.1 During examination

Once `BY MR. [ATTORNEY]:` is established, use Q. and A. for the
question-and-answer exchange. Do not repeat the attorney's name on each
question.

```
   Q.   How long have you lived at that address?
   A.   Approximately three years.
   Q.   And before that?
   A.   I lived in Austin.
```

### 3.2 Outside examination

When dialogue occurs outside the structured Q&A (objections,
colloquy, off-the-record discussion summaries returning to the record),
use full speaker labels:

```
   Q.   Did you ever speak to him about that?

        MR. PENA: Objection, form.

        THE COURT: Overruled. You may answer.

   A.   No, sir.
```

### 3.3 Objections during Q&A

Objections appear on their own line with full speaker label, then Q&A
continues:

```
   Q.   What did she tell you?

        MR. PENA: Objection, hearsay.

   A.   She said she was leaving.
```

---

## 4. Caption Block

Every transcript begins with a caption block identifying the case.
Format:

```
                    CAUSE NO. 2025-CI-23267

BRYAN ROQUE REYES AND      §   IN THE DISTRICT COURT
JOSEFA RAMIREZ,            §
        Plaintiffs,        §
                           §
VS.                        §   408TH JUDICIAL DISTRICT
                           §
PETER DURAI SINGH,         §
        Defendant.         §   BEXAR COUNTY, TEXAS

                    *   *   *   *   *   *   *

                    ORAL DEPOSITION OF
                    PETER DURAI SINGH
                    APRIL 23, 2026

                    *   *   *   *   *   *   *
```

The cause number, party names, court designation, and date come from
`job_config.json` fields. The pipeline should never produce a transcript
without a caption block. If `job_config.json` is missing required fields,
flag rather than guess.

---

## 5. Verbatim Preservation (CRITICAL)

The witness's spoken testimony must be preserved exactly as spoken.
This is the single most important rule in legal transcription. A
transcript that "improves" the witness's words is grounds for challenge
in court.

### 5.1 Always preserve

- Disfluencies: uh, um, ah, you know, like, I mean
- Repetitions: "the the cops", "I and who I"
- False starts: "I went to — actually, I drove to the store"
- Witness's grammatical errors: "we was driving home"
- Witness's tense errors: "I seen him yesterday"
- Sentence fragments and run-ons from spoken testimony
- Informal contractions as spoken: gonna, wanna, gotta, kinda

### 5.2 Always correct

- Clear Deepgram phonetic errors with no ambiguity (e.g.,
  "so happy you god" → "so help you God" — the oath has only one
  correct form)
- Proper noun misspellings against the case's `confirmed_spellings`
- Punctuation and capitalization
- Standard contractions of common words ("its" vs "it's" where the
  meaning is unambiguous)

### 5.3 Always flag, never guess

When text appears wrong but the correct form is uncertain, emit a
scopist flag rather than guessing:

```
[SCOPIST FLAG: "in June" — likely "injured" but witness's accent
unclear; verify from audio.]
```

Trigger conditions for flagging:
- Text is grammatically wrong but the right word is unclear
- A proper noun has multiple spellings in the same transcript
- A name appears that isn't on the case's participant list
- A phrase doesn't fit the surrounding context

Over-flagging is recoverable. Over-correcting is not.

---

## 6. Punctuation

### 6.1 Em dashes vs double hyphens

Use double hyphens (`--`) with no surrounding spaces for interruptions
and dashes. Do not use em dashes (—).

```
Correct:    I was going to--well, never mind.
Incorrect:  I was going to—well, never mind.
```

This matches Texas court reporter convention and ensures consistency
across the typewriter-style monospace formatting that legal transcripts
use.

### 6.2 Periods and commas with quotation marks

Always inside the closing quotation mark:

```
Correct:    She said, "I will not."
Incorrect:  She said, "I will not".
```

### 6.3 Question marks with quotation marks

Inside if the quoted material is the question; outside if the
surrounding sentence is the question:

```
She asked, "Are you ready?"
Did he really say "I will not"?
```

### 6.4 Series with commas (Oxford comma)

Use the serial comma:

```
Correct:    red, white, and blue
Incorrect:  red, white and blue
```

### 6.5 Spelled-out words

When a witness spells a word letter by letter, use hyphens between
letters and capitalize as spoken:

```
Q.   Could you spell that?
A.   It's W-U-R-Z-B-A-C-H.
```

---

## 7. Numbers

### 7.1 Default rule

Spell out numbers one through nine. Use figures for 10 and above.

```
Correct:    I have three children.
Correct:    The accident happened 15 years ago.
Incorrect:  I have 3 children.
Incorrect:  The accident happened fifteen years ago.
```

### 7.2 Exceptions — always figures

Regardless of value, use figures for:

- Ages: "He was 7 years old."
- Dates: "April 23, 2026"
- Times: "3:30 p.m."
- Money: "$50" (not "$fifty")
- Measurements: "5 feet 6 inches"
- Percentages: "5 percent" (or "5%")
- Cause numbers: "Cause No. 2025-CI-23267"

### 7.3 Exceptions — always words

- Numbers beginning a sentence: "Fifteen years ago, ..."
- Round numbers used loosely: "There were about a hundred people."
- Fractions standing alone: "two-thirds of the witnesses"

### 7.4 Times of day

```
Use:        3:30 p.m.    (lowercase, periods, no space before p.m.)
Avoid:      3:30 PM
Avoid:      3:30 P.M.
```

### 7.5 Cause numbers

Texas cause numbers follow the format `YYYY-COUNTY-NNNNN`:

```
2025-CI-23267    (Bexar County civil)
DC-25-13430      (Dallas County)
```

The pipeline must preserve the exact format as it appears in
`job_config.json`. Common Deepgram errors include "Cause No. 2025 CI
23267" (missing hyphens) and "because No. 2025..." (the regex bug we
already fixed).

---

## 8. Proper Nouns and Case-Specific Spellings

### 8.1 Authority

For each case, the canonical spelling of every proper noun is the value
in `job_config.json` `confirmed_spellings`. The pipeline normalizes to
these values during AI Correct.

### 8.2 Common Texas/Bexar County terms

These should be in every Bexar County case's confirmed_spellings (or in
a future `bexar_county_proper_nouns.json` seed file):

| Correct | Common Deepgram errors |
|---------|------------------------|
| Wurzbach | Worsbach, Worsbuck, Wardsbug, Rose Buck |
| Bexar | Bear, Becks |
| Boerne | Bernie, Burney |
| Loop 1604 | Loop sixteen oh four |
| Helotes | Helotis, Heloties |

### 8.3 When the spelling isn't in confirmed_spellings

Flag rather than guess. The scopist will resolve from the witness's
testimony, the NOD (Notice of Deposition), or by direct verification.

---

## 9. Off-Record Notations

When the deposition goes off the record, mark it with a centered
parenthetical:

```
                    (Off the record at 10:47 a.m.)

                    (On the record at 11:02 a.m.)
```

Do not attempt to transcribe what was said off the record. If the
parties summarize off-record discussion when returning to the record,
that summary is on-record content and should be transcribed normally.

---

## 10. Exhibits

### 10.1 Marking

When an exhibit is marked, use a centered parenthetical:

```
                    (Plaintiff's Exhibit 1 marked.)
```

### 10.2 References in testimony

```
Q.   Showing you what's been marked as Plaintiff's Exhibit 1, do
     you recognize this document?
A.   Yes, I do.
```

### 10.3 Numbering convention

- Plaintiff's exhibits: "Plaintiff's Exhibit 1, 2, 3..." (Arabic numerals)
- Defendant's exhibits: "Defendant's Exhibit A, B, C..." (letters)

This is the most common Texas convention but firms vary. The scopist
should match the convention established by the noticing attorney on the
record.

---

## 11. Reporter's Certificate

Every transcript ends with a reporter's certificate. The format varies
by Texas county and by firm but always contains:

- Reporter's name and CSR number
- Statement that the transcript is a true and correct record
- Date of certification
- Reporter's signature line

The pipeline does not generate the certificate text — that's the human
reporter's responsibility. But the DOCX export should leave room for it
and not produce a transcript that ends abruptly with the last Q/A.

---

## 12. Document Structure

### 12.1 Page layout

- 25 lines per page
- Line numbers in the left margin (1-25)
- Page number top-right
- 1-inch left margin (with line numbers in the gutter)
- Double-spaced testimony
- Single-spaced caption and certificate

### 12.2 Section order

1. Caption page
2. Appearances (who's present)
3. Index of examinations and exhibits
4. Body of testimony
5. Reporter's certificate
6. Errata sheet (if read-and-sign)

The pipeline currently produces only the body of testimony. Wrapping
that body in the surrounding structure is what `document_builder.py` is
supposed to do, and what the "Generate Full DOCX" feature surfaces.

---

## 13. Multi-File Depositions

When a deposition is recorded across multiple audio files (session
breaks, file-size limits), the files are combined via the multi-file
combiner before transcription. Speaker IDs are maintained across the
combined file because Deepgram processes it as a single call.

The transcript itself does not reflect that the original audio came
from multiple files. References to breaks come from what the parties
actually said on the record:

```
THE REPORTER: We are off the record at 11:02 a.m.

                    (Recess from 11:02 a.m. to 11:18 a.m.)

THE REPORTER: We are back on the record at 11:18 a.m.
```

---

## 14. Versioning of This Document

This style guide is versioned in the repository. When rules change:

1. Update this document with the new rule and a brief justification.
2. Update any tests that depend on the old rule.
3. Note the change in the commit message and reference the rule number.
4. Re-run the corpus diff tooling against existing ground truths to
   verify no unintended regressions.

Version history:

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-26 | Initial draft based on first three corpus cases (Singh, Karam, Ozuna) and lessons from chunking-fix verification. |

---

## 15. Open Questions and Future Work

These are rules I haven't decided on yet. They'll be filled in as
evidence accumulates from corpus cases.

- **Read-and-sign vs waiver of signature.** When the witness reserves
  the right to read and sign, what's the correct certificate language?
  Need to verify against the next case where this applies.

- **Realtime vs final transcript distinctions.** Are there formatting
  differences between what gets shown live vs what gets certified?

- **Bilingual depositions.** When a witness uses an interpreter, the
  speaker labels and Q/A structure change. Need to document the
  convention before processing the first bilingual case.

- **Video deposition specifics.** Are timecode references in the
  transcript? At what granularity?

When evidence from a real case answers any of these, update this
section and promote the answer to a numbered rule above.
