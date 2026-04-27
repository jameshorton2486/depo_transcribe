# Depo-Pro House Style Guide

> **What this is.** The formatting rules Depo-Pro's pipeline enforces and
> that human scopists should apply when producing certified transcripts
> from Depo-Pro output. This document is the authoritative reference for
> our pipeline corrections and for hand-correcting `pipeline_output.txt`
> into `ground_truth.txt` during corpus building.
>
> **Primary authority.** For any reporter's record produced for a Texas
> court, the binding authority is the Uniform Format Manual for Texas
> Reporters' Records, approved by the Texas Supreme Court (Misc. Docket
> Nos. 10-9077 and 10-9113). Where this guide conflicts with the UFM,
> the UFM controls. Sections in this guide that rely on the UFM cite
> the relevant section number (e.g., "UFM 3.15"). Reporters can find
> the UFM on the Court Reporters Certification Board website.
>
> **Secondary authority.** Where the UFM is silent on a question of
> grammar, punctuation, or word usage, UFM 3.13 directs reporters to
> standard references including The Gregg Reference Manual (10th edition
> or later), The Merriam-Webster Dictionary (11th edition or later), and
> The Elements of Style. Many Texas reporters also consult Morson's
> English Guide for Court Reporters. Reporters using Depo-Pro should
> have their own copies of these references; we do not embed their
> content in the application.
>
> **What this is not.** A comprehensive court reporting style manual.
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
changes, cite the section here that the rule enforces. Sections that
cite a UFM rule (e.g., "UFM 3.15") have the strongest claim because
they reflect binding state authority. Sections without a UFM citation
are house-style decisions and may need more deliberation before they
become enforced rules.

Rules without a documented basis in this guide should be questioned
during the promotion review.

If something in this guide ever conflicts with the actual UFM document,
the UFM controls. Update this guide to match.

---

## 1. Speaker Labels

> **UFM authority.** Speaker identification is governed by UFM 3.22.
> All speakers must be identified in capital letters, using last name
> only unless two attorneys share the same last name and gender, in
> which case both first and last name are required. UFM 3.22 also
> provides a table of standard speaker designations.

### 1.1 Court reporter

Use **THE REPORTER:** for the court reporter's on-record statements.
Do not use "THE COURT REPORTER:". This matches UFM 3.22's standard
designation table.

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

Per UFM 3.22, full first and last names are required only when two or
more attorneys of the same gender share a surname. Otherwise surname
alone is correct from first appearance through the entire transcript.
If two attorneys share a surname and gender, distinguish by full name
throughout:

```
MR. JAMES GONZALEZ:
MR. ROBERT GONZALEZ:
```

### 1.4 Judge

Use **THE COURT:** for the presiding judge's on-record statements,
regardless of the judge's actual title.

### 1.5 Videographer

Use **THE VIDEOGRAPHER:** for the videographer's on-record statements
during a video deposition.

---

## 2. Examination Headers

> **UFM authority.** UFM 3.17 provides the full list of examination and
> proceeding headings that may be used in the body of the transcription
> and in the index.

Each examination section begins with a centered, all-caps header:

```
                              EXAMINATION

BY MR. GONZALEZ:

   Q.   Please state your full name.
   A.   Peter Durai Singh.
```

### 2.1 Approved heading list (UFM 3.17)

The following headings are approved by UFM 3.17. Use these exact forms:

```
DIRECT EXAMINATION
FURTHER DIRECT EXAMINATION
VOIR DIRE EXAMINATION
FURTHER VOIR DIRE EXAMINATION
CROSS-EXAMINATION
REDIRECT EXAMINATION
RECROSS-EXAMINATION
FURTHER REDIRECT EXAMINATION
FURTHER RECROSS-EXAMINATION
```

UFM 3.17 also lists trial-specific headings that won't typically appear
in deposition transcripts but may appear in trial transcripts processed
through Depo-Pro:

```
FINAL PRETRIAL HEARING
JURY VOIR DIRE BY THE COURT
JURY VOIR DIRE BY THE STATE / PLAINTIFF / DEFENDANT
STATE'S / PLAINTIFF'S / DEFENDANT'S OPENING STATEMENT
CONFERENCE ON JURY INSTRUCTIONS
STATE'S / PLAINTIFF'S / DEFENDANT'S CLOSING STATEMENT
JURY INSTRUCTIONS
COURT'S FINDINGS
JURY VERDICT
PUNISHMENT PHASE
SENTENCING
```

### 2.2 BY-line placement

The `BY [ATTORNEY]:` line appears once at the start of each examination
and again any time a different attorney takes over questioning.

Per UFM 3.22, after a parenthetical or colloquy interruption, the
resumed `Q.` may be followed by speaker identification on the same line
to remind the reader who is conducting the examination:

```
        (Discussion off the record)

   Q.   (BY MR. GONZALEZ) Returning to my earlier question --
```

---

## 3. Q/A Structure

> **UFM authority.** UFM 2.7 governs Q. and A. designations: "'Q.' and
> 'A.' must be used to signify questions and answers. The period
> following the 'Q' and 'A' designation is optional." UFM 2.11 governs
> tab placement: the first tab (5 spaces from left margin) is used for
> Q. or A.; the second tab (10 spaces) is used for the text after Q. or
> A.; subsequent lines return to the left margin.

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

The period after Q and A is optional under UFM 2.7. Depo-Pro defaults
to including the period (`Q.` and `A.`) for consistency with the most
common Texas firm style. If a particular firm or judge prefers the
period-less form (`Q` and `A`), that's a per-case configuration, not a
deviation from UFM.

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

> **UFM authority.** This is not a stylistic preference; it's binding
> Texas state authority.
>
> **UFM 3.15 (Editing of Speech).** "Any transcription should provide
> an accurate record of words spoken in the course of proceedings.
> All grammatical errors, changes of thought, contractions,
> misstatements, and poorly-constructed sentences must be transcribed
> as spoken."
>
> **UFM 3.14 (Striking from the Record).** "No portion of any
> proceeding may be omitted by a request or an order to strike. The
> material ordered stricken, as well as the order to strike, must all
> appear in any transcription."
>
> **UFM 3.8 (Language and Verbal Expressions).** "Except as noted
> below, a transcription must contain all English words and other
> verbal expressions uttered during the course of the proceedings."

The witness's spoken testimony must be preserved exactly as spoken.
This is the single most important rule in legal transcription. A
transcript that "improves" the witness's words violates UFM 3.15 and
is grounds for challenge in court.

### 5.1 Always preserve

- Disfluencies: uh, um, ah, you know, like, I mean
- Repetitions: "the the cops", "I and who I"
- False starts: "I went to -- actually, I drove to the store"
- Witness's grammatical errors: "we was driving home"
- Witness's tense errors: "I seen him yesterday"
- Sentence fragments and run-ons from spoken testimony
- Informal contractions as spoken: gonna, wanna, gotta, kinda
- Material that a party requests be stricken — keep it in the
  transcript with the strike order both visible (UFM 3.14)

### 5.2 Verbal/nonverbal expressions (UFM 3.9)

UFM 3.9 specifies how to handle affirmative and negative non-word
responses:

- "Uh-huh" — used when the speaker is answering affirmatively
- "Huh-uh" — used when the speaker is answering negatively
- For nodding or shaking head with no verbal response, the reporter
  may indicate the gesture parenthetically (see Section 9 below)

Note the spelling: UFM uses "Huh-uh" with an h-u-h prefix, not "uh-uh".
Match UFM's spelling exactly when transcribing these responses.

### 5.3 Always correct

- Clear Deepgram phonetic errors with no ambiguity (e.g.,
  "so happy you god" → "so help you God" — the oath has only one
  correct form)
- Proper noun misspellings against the case's `confirmed_spellings`
- Punctuation and capitalization
- Standard contractions of common words ("its" vs "it's" where the
  meaning is unambiguous)

### 5.4 Always flag, never guess

When text appears wrong but the correct form is uncertain, emit a
scopist flag rather than guessing:

```
[SCOPIST FLAG: "in June" -- likely "injured" but witness's accent
unclear; verify from audio.]
```

Trigger conditions for flagging:
- Text is grammatically wrong but the right word is unclear
- A proper noun has multiple spellings in the same transcript
- A name appears that isn't on the case's participant list
- A phrase doesn't fit the surrounding context

Over-flagging is recoverable. Over-correcting violates UFM 3.15 and
cannot be undone after the transcript is certified.

---

## 6. Punctuation

> **UFM authority.** UFM 3.13 directs: "Punctuation and spelling must
> be consistent with generally accepted standards." UFM cites The
> Elements of Style, The Gregg Reference Manual (10th ed. or later),
> and The Merriam-Webster Dictionary (11th ed. or later) as standard
> references. UFM 2.9 governs the specific use of dashes for speech
> interruption.

### 6.1 Dashes (UFM 2.9)

UFM 2.9 is explicit: "Interruptions of speech must be denoted by the
use of dashes ( -- ) at the point of interruption, and again at the
point the speaker resumes speaking."

Use double hyphens (`--`) for interruptions. Do not use em dashes (—).
The UFM uses double hyphens with surrounding spaces in its own examples
of interruption-and-resume; for our pipeline output, we use double
hyphens with no surrounding spaces, which matches the more common
Texas freelance firm style:

```
Correct:    I was going to--well, never mind.
Incorrect:  I was going to—well, never mind.
```

For interruption-and-resume across speakers (UFM 2.9 pattern):

```
   Q.   And then you went to the --
   A.   No, I never said that.
   Q.   -- the back of the building, correct?
```

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

### 6.5 Quotation marks (UFM 2.8)

UFM 2.8: "The use of quotation marks is optional." When a deposition
includes a witness quoting another speaker, Depo-Pro defaults to
including quotation marks for clarity even though they are not
mandatory under UFM. If a particular firm or judge prefers to omit
quotation marks for short quoted material, that's a per-case
configuration.

### 6.6 Spelled-out words

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

## 9. Parentheticals and Off-Record Notations

> **UFM authority.** UFM 3.16 governs parenthetical notations:
> "Parenthetical notations in any transcription are a court reporter's
> own words, enclosed in parentheses, recording some action or event.
> Parenthetical notations should be as short as possible and consistent
> with clarity and standard word usage. Blank lines before or after
> parenthetical notations are prohibited." UFM 3.21 specifies that
> "Private or off-the-record communications must be noted as follows:
> (Discussion off the record) or (Sotto voce discussion off the
> record)."

### 9.1 Approved parentheticals from UFM 3.16

Use these standard parentheticals exactly as written. The list is from
UFM 3.16(a):

```
(Call to order of the court)
(Jury not present)
(Jury present)
(The witness was sworn)
(Interpreter sworn)
(Recess from ^ to ^)
(Lunch recess from ^ to ^)
(At the Bench, on the record)
(At the Bench, off the record)
(Discussion off the record)
(Moving head up and down)
(Moving head side to side)
(Indicating)
(Descriptive sound)
(Snapping fingers)
(Writing)
(Weeping)
(No verbal response)
(Interruption)
(Witness complies)
(Sotto voce discussion between ^ and ^)
(Sotto voce discussion)
(Sotto voce discussion off the record)
(The jury was sworn)
(The witness was affirmed)
(Discussion between interpreter and witness)
(Pointing)
(Drawing)
(Pausing)
(Exhibit ^ marked)
(Proceedings concluded / recessed at ^)
(Requested portion was read)
```

The `^` characters in UFM are placeholders for actual values (times,
names, exhibit numbers). For example, `(Recess from ^ to ^)` becomes
`(Recess from 10:47 a.m. to 11:02 a.m.)` in the actual transcript.

### 9.2 Recess and break notation

Use UFM's `(Recess from ^ to ^)` form. Do not use the older
`(Off the record)` / `(On the record)` pattern as a primary recess
marker — that form is for very brief off-record discussions during
otherwise-running testimony (UFM 3.21).

```
                    (Recess from 10:47 a.m. to 11:02 a.m.)
```

For the lunch break specifically:

```
                    (Lunch recess from 12:15 p.m. to 1:30 p.m.)
```

For brief off-record discussions in the middle of testimony, use:

```
                    (Discussion off the record)
```

Per UFM 3.16, no blank lines may appear before or after parenthetical
notations. The parenthetical sits flush against surrounding content.

### 9.3 Witness gestures

When a witness responds non-verbally, the attorney is responsible for
noting the gesture for the record (UFM 3.16). If counsel fails to do
so, the reporter may use a parenthetical from UFM 3.16(a):

```
   Q.   Did you see who hit the car?
   A.   (Moving head up and down)
   Q.   Is that a yes?
   A.   Yes.
```

Prefer affirmative or descriptive parentheticals from the UFM list
over interpretive ones. `(Moving head up and down)` is correct;
`(Witness nodded affirmatively)` is interpretive and should be avoided.

### 9.4 Off-record content

Do not attempt to transcribe what was said off the record. If the
parties summarize off-record discussion when returning to the record,
that summary is on-record content and should be transcribed normally.

### 9.5 Criminal trial parentheticals (UFM 3.16(b))

For criminal trials, additional parentheticals are required to note
defendant and jury presence. Depo-Pro currently focuses on civil
depositions where these don't apply, but if a criminal trial transcript
is processed through Depo-Pro, use UFM 3.16(b)'s list:

```
(Open court, defendant and jury panel present)
(Open court, defendant present, no panel)
(Open court, defendant present, no jury)
(Open court, defendant and jury present)
(Chambers, defendant present, no jury)
(Discussion off the record in chambers, defendant not present)
(Discussion on the record in chambers, defendant present)
(Crime scene, defendant and jury present)
```

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

> **UFM authority.** UFM 3.3 governs certification of Official
> Reporter's Records; UFM 3.4 governs certification of Freelance
> Reporter's Records (which is what Depo-Pro typically produces for
> deposition work). UFM 3.4 requires the certification page to
> identify the party responsible for the costs and to include the
> firm registration number issued by the CRCB if applicable.

Every transcript ends with a reporter's certificate. The format varies
by Texas county and by firm but always contains:

- Reporter's name and CSR number
- Firm registration number (if firm-affiliated, per UFM 3.4 and
  Texas Government Code § 52.013(a)(7))
- Statement that the transcript is a true and correct record
- Identification of the party responsible for the costs
- Date of certification
- Reporter's signature line

UFM Figures 7-9 provide example forms for changes/signature pages and
certification pages. Reporters should consult the actual UFM document
for the figure templates.

The pipeline does not generate the certificate text — that's the human
reporter's responsibility, and the legal weight of the certificate
comes from the human reporter's attestation. But the DOCX export
should leave room for it and not produce a transcript that ends
abruptly with the last Q/A.

For non-stenographic records (audio/video recordings the reporter is
transcribing rather than capturing live), UFM 3.7 imposes additional
certification requirements including a statement of the transcription
fee and payor.

---

## 12. Document Structure

> **UFM authority.** UFM Section 2 governs page formatting in detail.
> Key requirements: 8.5 x 11 inch pages (UFM 2.1), 9 or 10 pitch
> character spacing (UFM 2.3), 25 numbered lines of text per page
> (UFM 2.13), no blank lines except where specifically permitted
> (UFM 2.14), page numbers top-right (UFM 2.16).

### 12.1 Page layout (UFM 2.x)

| Setting | Value | UFM Reference |
|---------|-------|---------------|
| Page size | 8.5 x 11 inches | UFM 2.1 |
| Page color | White, opaque | UFM 2.2 |
| Pitch | 9 or 10 characters per inch | UFM 2.3 |
| Margin width | 6.5 inches; 56-63 chars/line | UFM 2.5 |
| Format box | Solid lines on all four margins | UFM 2.6 |
| Lines per page | 25, numbered 1-25 | UFM 2.13 |
| Line numbers | Left of format box | UFM 2.12 |
| Page number | Top-right corner | UFM 2.16 |
| Page numbering | Sequential from 1 per volume | UFM 2.17 |
| Tab 1 | Position 5 (Q. or A.) | UFM 2.10, 2.11 |
| Tab 2 | Position 10 (text after Q. or A.) | UFM 2.10, 2.11 |
| Tab 3 | Position 15 (speaker IDs, parentheticals) | UFM 2.10, 2.11 |
| Spacing | Double-spaced testimony | UFM 2.13 |
| Blank lines | Prohibited except witness setup, admin pages, requested | UFM 2.14 |
| Font | Mixed upper/lowercase, clearly legible | UFM 2.4 |

### 12.2 Section order

For an Official Reporter's Record (UFM Section 3):

1. Title page (UFM 3.1)
2. Appearances (may be on title page or immediately after, UFM 3.1)
3. Index — chronological, alphabetical, exhibit (UFM 3.23)
4. Body of testimony
5. Reporter's certificate (UFM 3.3)
6. Exhibits in separate volume (UFM 6.4)

For a Freelance Reporter's Record (such as a deposition transcript,
which is what Depo-Pro typically produces):

1. Title page (UFM 3.1)
2. Appearances
3. Body of testimony
4. Changes/signature page if applicable (UFM 3.4, Figures 7-9)
5. Reporter's certificate (UFM 3.4)
6. Index (per UFM 3.24, may appear at beginning after admin pages or
   at end — Depo-Pro convention is end of transcript)
7. Exhibits

### 12.3 Volume size limits (UFM 6.3)

A single volume must not exceed 300 pages. If a deposition runs longer,
break at a logical point (UFM 6.2): start of new witness, end of one
type of examination and start of another, recess, or start/end of
motions.

### 12.4 Pipeline scope

Depo-Pro currently produces the body of testimony. Wrapping that body
in the surrounding structure (title page, appearances, certificate,
index) is the role of `document_builder.py` and the "Generate Full
DOCX" feature.

---

## 13. Indexes

> **UFM authority.** Index requirements differ between Official
> Reporter's Records (UFM 3.23, mandatory format) and Freelance
> Reporter's Records (UFM 3.24, more flexible). Depo-Pro typically
> produces freelance records (depositions), so UFM 3.24 is the primary
> reference, but pipeline output should be structured to make UFM
> 3.23-compliant indexes feasible if a transcript is later promoted
> to an Official Reporter's Record.

### 13.1 Freelance index requirements (UFM 3.24)

Per UFM 3.24(a), a Freelance Reporter's Record index must include,
where applicable:

1. Appearances
2. Stipulations
3. Examinations
4. Reporter's certification page
5. Signature and correction page(s)
6. Exhibits — numbered with description and page where formally
   referenced or marked
7. Certified questions
8. Requested information

UFM 3.24(b): "There is no required format for a Freelance Reporter's
Record index." Depo-Pro convention is to provide a chronological index
listing each examination type and the page it begins on, plus an
exhibit index in numerical order.

### 13.2 Official Record index requirements (UFM 3.23)

If a Depo-Pro transcript is being prepared as an Official Reporter's
Record (e.g., for an oral hearing or trial that was transcribed
through our pipeline), UFM 3.23 imposes stricter requirements:

- **Chronological index** — all witnesses in order of appearance, plus
  all events that occurred (UFM 3.23(a))
- **Alphabetical index** — alphabetical listing of witnesses
  (UFM 3.23(b))
- **Exhibit index** — complete description plus page offered/received
  (UFM 3.23(c))
- **Master index** — required for multi-volume records, always labeled
  "Volume 1" (UFM 3.23(d))
- **Columnar format** — required for exhibits and alphabetical
  witnesses (UFM 3.23(e))

The pipeline's index output should produce data that's straightforward
to format into either freelance or official style.

---

## 14. Interpreters

> **UFM authority.** UFM 3.11 governs swearing in interpreters; UFM
> 3.12 governs how interpreted testimony appears in the transcript.

### 14.1 Interpreter sworn (UFM 3.11)

When a witness testifies through an interpreter, the transcript must
include the interpreter's oath at the start of the testimony. UFM 3.11
provides suggested oath language:

> "Do you solemnly swear or affirm that the interpretation you will
> give in this deposition will be from English to [target language]
> and from [target language] to English to the best of your ability?"

Mark the interpreter's swearing-in with the standard parenthetical
from UFM 3.16(a):

```
                    (Interpreter sworn)
```

For a sign-language interpreter, the oath references American Sign
Language or Signed English (UFM 3.11).

### 14.2 Interpreted testimony (UFM 3.12)

Per UFM 3.12: "In interpreted testimony, court reporters must use Q&A
sequencing to reflect the question asked in English by the attorney
and the answer of the witness given in English through the
interpretation process."

The Q&A sequence shows English question → English answer (as rendered
by the interpreter). The transcript does not contain the foreign-
language exchange unless a party speaks directly to the witness in
that language. UFM 3.12 also notes: "When interpreters are used, it
will be assumed, unless otherwise stated, that answers are in a
foreign language and interpreted."

If part of an answer is given by the interpreter and part is in
English directly by the witness, mark the English-direct portion
parenthetically:

```
   A.   I went to the store -- (In English) the Walmart on Main.
```

If counsel speaks directly to the witness in the witness's native
language without using the interpreter, mark this with a parenthetical
(UFM 3.12 references Figure 22 for the standard form, which we don't
reproduce here).

### 14.3 Pipeline implications

The pipeline currently does not have specific handling for interpreted
depositions. When the first interpreted case is processed through
Depo-Pro, document the actual handling in this section and update as
needed.

---

## 15. Multi-File Depositions

When a deposition is recorded across multiple audio files (session
breaks, file-size limits), the files are combined via the multi-file
combiner before transcription. Speaker IDs are maintained across the
combined file because Deepgram processes it as a single call.

The transcript itself does not reflect that the original audio came
from multiple files. References to breaks come from what the parties
actually said on the record, formatted per UFM 3.16(a):

```
THE REPORTER: We are off the record at 11:02 a.m.

                    (Recess from 11:02 a.m. to 11:18 a.m.)

THE REPORTER: We are back on the record at 11:18 a.m.
```

---

## 16. Rough Drafts and Realtime Output

> **UFM authority.** UFM Section 4 governs unedited rough drafts.
> UFM 4.1: "When preparing a rough draft transcription or unedited
> electronic transcript, the transcript of the proceedings must not
> be certified and must not be used, cited, or transcribed as a
> certified transcription of the proceedings."

If Depo-Pro output is delivered to a party before scopist review and
certification, the output must be marked as a rough draft per UFM 4.2:

```
UNEDITED, UNPROOFREAD, UNCORRECTED, UNCERTIFIED ROUGH DRAFT
```

Or alternatively: `UNEDITED ROUGH DRAFT ONLY`

UFM 4.5 provides a recommended disclaimer for the start of unedited
output:

> "This unedited rough draft of the proceedings was produced in
> Realtime and is not certified. The rough draft transcription may
> not be cited or used in any way or at any time to rebut or
> contradict the certified transcription of proceedings. There will
> be discrepancies in this form and the final form, because this
> Realtime transcription has not been edited, proofread, corrected,
> finalized, indexed, or certified."

The pipeline's output before scopist review qualifies as a rough draft
under UFM 4.1 and must be marked accordingly. The DOCX export should
include the rough-draft watermark or header by default until a
certification step removes it.

UFM 4.4 prohibits format boxes, title pages, appearance pages,
certifications, and indexes in Realtime unedited rough drafts. Our
pipeline produces something between a Realtime rough draft and a
finished transcript, so this is a per-firm configuration question.

---

## 17. Versioning of This Document

This style guide is versioned in the repository. When rules change:

1. Update this document with the new rule and a brief justification.
2. Cite the UFM section if the change reflects a UFM-grounded rule.
3. Update any tests that depend on the old rule.
4. Note the change in the commit message and reference the rule number.
5. Re-run the corpus diff tooling against existing ground truths to
   verify no unintended regressions.

Version history:

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-26 | Initial draft based on first three corpus cases (Singh, Karam, Ozuna) and lessons from chunking-fix verification. |
| 1.1 | 2026-04-26 | Re-grounded the document in the Uniform Format Manual for Texas Reporters' Records (Tex. Sup. Ct. Misc. Docket No. 10-9077, as amended by 10-9113). Added UFM section citations throughout. New sections: 13 (Indexes, per UFM 3.23/3.24), 14 (Interpreters, per UFM 3.11/3.12), 16 (Rough Drafts, per UFM Section 4). Substantially expanded section 9 (Parentheticals) using UFM 3.16's authoritative list. Verbatim preservation (section 5) re-grounded in UFM 3.15. Document structure (section 12) re-grounded in UFM Section 2. |

---

## 18. Open Questions and Future Work

These are rules I haven't decided on yet. They'll be filled in as
evidence accumulates from corpus cases and from further reading of
secondary references.

UFM-answered questions from v1.0 are now closed:

- ~~Bilingual depositions and interpreter handling~~ — Answered by
  UFM 3.11/3.12, now Section 14.
- ~~Rough draft / Realtime distinctions~~ — Answered by UFM Section 4,
  now Section 16.

Still open:

- **Read-and-sign vs waiver of signature.** UFM 3.4 references Figures
  7-9 for changes/signature pages but doesn't dictate when a witness
  reserves signature vs waives it — that's case-by-case. Need to
  document the actual workflow when the first read-and-sign case
  comes through Depo-Pro.

- **Video deposition specifics.** UFM 8.10 governs video file format
  for electronic filing (.mp4, max 5 GB), but the question of timecode
  references in the transcript itself is not addressed by UFM. Need to
  verify against the next video deposition processed through Depo-Pro.

- **Realtime stream vs final DOCX deltas.** When Depo-Pro generates
  Realtime output during a deposition, what's the precise transition
  between rough-draft watermarked output and certifiable text? UFM
  Section 4 covers the labeling but not the technical state machine.

- **Per-firm style overrides.** Several UFM rules have explicit
  optional configurations (UFM 2.7 period-after-Q/A, UFM 2.8 quotation
  marks, UFM 2.15 time stamping). The pipeline needs a configuration
  layer for these so individual firms can match their established
  conventions without violating UFM. Where does this configuration
  live? `job_config.json`? A separate `firm_config.json`?

- **Certified questions in deposition workflow.** UFM 3.5 describes
  the procedure when a witness refuses to answer or counsel instructs
  not to answer. The pipeline currently doesn't have specific handling
  for this; document the behavior when the first certified-question
  case comes through.

- **Sealed portions of transcript.** UFM 8.7 governs sealed records
  for electronic filing. Depo-Pro doesn't currently distinguish sealed
  from unsealed material. Need to add this when a sealed case requires
  it.

When evidence from a real case answers any of these, update this
section and promote the answer to a numbered rule above with a UFM
citation if applicable.
