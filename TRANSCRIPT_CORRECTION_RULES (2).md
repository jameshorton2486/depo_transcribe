# DEPO-PRO TRANSCRIPT CORRECTION RULES
# Rules for AI-Assisted Legal Deposition Transcript Correction
# Reporter: Miah Bardot, CSR No. 12129 — SA Legal Solutions, San Antonio, Texas
# Version: 1.0 — Generated from audit of Trevino v. Ortiz raw transcript
#
# PURPOSE
# These rules define how to transform raw Deepgram/ASR output into a
# properly formatted legal deposition transcript that meets Texas UFM
# standards and Miah Bardot's certified transcript format requirements.
# ─────────────────────────────────────────────────────────────────────────────

## RULE 1 — PRE-RECORD CONTENT EXCLUSION

**Rule:** Exclude ALL content that appears before the formal record opens.

**Pre-record markers (EXCLUDE everything before these):**
- "We are on the record"
- "Recording in progress"
- "Today is [date]. The time is [time]..."
- "This is the beginning of the deposition of..."

**What to exclude:** Zoom/Teams setup chatter, attorney small talk, technical
difficulties, side conversations, DJ music (yes, this happened), and any
content where parties are clearly off-record.

**What to preserve:** Everything from the first formal on-record statement forward.

**Post-record content (EXCLUDE):** Everything after "we are off the record" at
the end of the deposition, including post-record spellings session (that content
is used for back-correction only — it does not appear in the transcript body).

---

## RULE 2 — SPEAKER ATTRIBUTION CORRECTION

**Problem:** ASR systems frequently misattribute speaker labels. The most common
errors are:

| Raw (Wrong) | Correct | Reason |
|---|---|---|
| THE REPORTER | MS. [WITNESS NAME] | Reporter's voice used for witness testimony |
| MR. [NAME A] | MR. [NAME B] | Names swapped between attorneys |
| DR. [NAME] | MR. [NAME] | Attorneys misidentified as doctors |
| Q. [text] | A. [text] | Answer placed inside Q line |
| A. [text] | Q. [text] | Question placed inside A line |

**How to identify correct speaker:**
1. The EXAMINING ATTORNEY asks all Q lines (questions)
2. The WITNESS answers all A lines (answers)
3. THE REPORTER: opens the record, swears the witness, manages recesses
4. Objecting attorneys use SP (speaker label) format: `MR.  SMITH:  Objection.  Form.`
5. If a "Q." line contains an answer ("Yes." "No." "Correct."), split it:
   move the answer to A., keep the next question in Q.

**Never reassign speaker based on content assumptions. Flag for Scopist if
attribution is genuinely ambiguous.**

---

## RULE 3 — Q/A STRUCTURAL RECONSTRUCTION

**Rule:** Every question from the examining attorney = Q line. Every witness
answer = A line. These NEVER share a paragraph.

**Q format:** `\tQ.  [question text]`
(Tab + Q. + TWO spaces + text)

**A format:** `\tA.  [answer text]`
(Tab + A. + TWO spaces + text)

**Common broken patterns to fix:**

**Pattern A — Answer embedded in Q line:**
```
WRONG:  Q. Have you ever been deposed? No.
RIGHT:  Q. Have you ever been deposed?
        A. No.
```

**Pattern B — Question and answer merged:**
```
WRONG:  Q. Is this your first time? Yes, sir. Have you ever...
RIGHT:  Q. Is this your first time?
        A. Yes, sir.
        Q. Have you ever...
```

**Pattern C — Witness answer followed by next question in same line:**
```
WRONG:  A. No, sir. Are you currently employed?
RIGHT:  A. No, sir.
        Q. Are you currently employed?
```

**Rule for "Correct." / "Yes." / "No." after a declarative:**
When the witness says "Correct." after a declarative Q, it is an A line.

**Attribution after objection:**
When an attorney objects mid-examination, the next Q from the examiner uses:
`\tQ.  (BY: MR.  [NAME])  [question text]`

---

## RULE 4 — SPEAKER LABEL FORMAT

**Format:** `\t\t\t[LABEL]:  [text]`
(Three tabs + ALL-CAPS label + colon + TWO spaces + text)

**Honorific rules:**
- `MR.  ` (period + TWO spaces) — never `Mr.` with one space
- `MS.  ` (period + TWO spaces)
- `MRS.  ` (period + TWO spaces)
- `THE REPORTER:` — always this exact form (NEVER "THE COURT REPORTER:")
- `THE WITNESS:` — used only in reporter opening / oath section

**All honorifics are ALL-CAPS in speaker labels AND in Q/A body text:**
- `MR.  JONES:` in labels
- `...questions from MR.  Jones...` in body text

**No non-breaking spaces.** Use regular double spaces only.

---

## RULE 5 — VERBATIM LEGAL PHRASE CORRECTIONS

These specific phrases are consistently garbled by ASR and must always be
corrected:

| Raw (Wrong) | Correct |
|---|---|
| same effect as a weapon in the courthouse | same force and effect as if given in open court |
| penalty of curtory | penalty of perjury |
| remit for this remote deposition | agreement for this remote deposition |
| remotes for any witness | remote swearing of the witness |
| notice and attorney | noticing attorney |
| so help you guide | so help you God |
| They do. (oath response) | I do. |
| pass away / past witness | Pass the witness. |
| court border | court reporter |
| Infection. / Perfection. / Dissection. | Objection. |
| Detection. / Injection. / Perception. | Objection. |
| Addiction. / Deflection. / Eviction. | Objection. |
| Objection form. | Objection. Form. |
| THE COURT REPORTER: | THE REPORTER: |

---

## RULE 6 — OBJECTION FORMAT

**Rule:** Objections are ALWAYS on their own speaker label line, never embedded
in Q or A lines.

**Format:** `\t\t\tMR.  [NAME]:  Objection.  Form.`

**Objection types:**
- `Objection.  Form.` (most common)
- `Objection.  Form and leading.`
- `Objection.  Leading.`
- `Objection.  Nonresponsive.`
- Standalone: `Objection.`

**TWO spaces** between "Objection." and the basis — always.

**Counsel requesting basis:** `Counsel, state the basis.`
(NOT "can cancel state the basis" or similar garbles)

---

## RULE 7 — REPORTER NAME AND CREDENTIALS

**Miah Bardot's standard opening formula:**
`I am Miah Bardot, court reporter, licensed in Texas, CSR No. 12129.`

**Common garbles to correct:**
| Raw | Correct |
|---|---|
| Mia Bardo | Miah Bardot |
| Mia Bardell | Miah Bardot |
| Neobardeau | Miah Bardot |
| Miyamardeau | Miah Bardot |
| Mia Bardeau | Miah Bardot |
| Lea Bardot | Miah Bardot |
| court border | court reporter |
| license in Texas number 12129 | licensed in Texas, CSR No. 12129 |
| 12129. 9 | 12129 |
| Texas number 12129 | CSR No. 12129 |

---

## RULE 8 — NUMBER AND DATE FORMAT

**Dates in testimony:** Always digits, never words.
| Spoken | Written |
|---|---|
| March nineteen two thousand three | 03/19/2003 |
| April seventeenth twenty twenty four | 04/17/2024 |
| twenty twenty two | 2022 |
| twenty four (year reference) | '24 |
| twenty five (year reference) | 2025 |

**Time:** `9:58 a.m.` (not `09:58AM` or `9:58AM`)

**Street addresses:** Always numbers.
| Spoken | Written |
|---|---|
| twelve ten, B as in boy, Ash Street | 1210, B, as in Boy, Ash Street |
| two thousand five hundred North McCall | 2500 North McCall |
| forty two one twenty five | 42125 |
| zero eight six four zero | 08640 |
| four one zero nine | 4109 |

**Ages/quantities in testimony:** Numerals preferred for ages and specific counts.
- `eighteen` → `18`
- `ten to twenty pounds` → `10 to 20 pounds`
- `two fifty to three hundred dollars` → `$250 to $300`
- `thirty three` → `33`

**Cause numbers:** Always hyphenated.
- `242,754` → `24-2754` (ONLY when preceded by "Cause No." / "Cause number")
- `C226025 g` → `C-226025-G`
- `2025CVA001596D2` → keep as-is if already formatted

**Exception:** Do NOT convert numbers that are spelled out as part of natural
speech (e.g., "I was one of three employees" stays as written).

---

## RULE 9 — PARENTHETICALS

**Format:** Four tabs + navy blue text (RGBColor 0x1E, 0x3A, 0x5F)

**Standard parentheticals:**
```
				(The witness was sworn.)
				(Whereupon, the deposition commenced at 9:58 a.m.)
				(Whereupon, a recess was taken at 10:47 a.m.)
				(Whereupon, the proceedings resumed at 10:56 a.m.)
				(Whereupon, Exhibit 1 was marked.)
				(Whereupon, the deposition was concluded at 11:57 a.m.)
```

**Rule:** Parentheticals are NEVER in Q or A lines. Always standalone paragraphs.

---

## RULE 10 — SECTION HEADERS

**Examination types (left-aligned, bold):**
```
EXAMINATION
BY MR.  JONES:
```
```
CROSS-EXAMINATION
BY MR.  SICONI:
```
```
REDIRECT EXAMINATION
BY MR.  JONES:
```

**Rule:** Headers are plain left-aligned — NO centering. `BY MR.  [NAME]:` is
on its own line directly below the examination header.

---

## RULE 11 — SCOPIST FLAGS

**Use for anything that cannot be auto-corrected with confidence.**

**Format:** Bold orange text (RGBColor 0xB4, 0x5F, 0x06)
```
[SCOPIST: FLAG N: description of the issue — verify from audio/NOD]
```

**Always flag:**
- Any proper noun (name, company, city, street) that Deepgram garbles in a
  way that cannot be confirmed from the Notice of Deposition
- Dates or numbers that are unclear or internally inconsistent
- Any testimony where the witness's words are genuinely unclear even in context
- Exhibit numbers or Bates numbers that may be wrong
- Attorney or firm names not in the NOD
- Any word where the audio and context disagree with each other

**Never flag:**
- Standard objection garbles (fix them with Rule 5)
- Miah's name (fix it with Rule 7)
- Common legal phrases (fix with Rule 5)
- Duplicate blocks (remove them silently)

---

## RULE 12 — DUPLICATE BLOCK DETECTION

**Rule:** Deepgram frequently outputs the same utterance twice in sequence.
Remove the second occurrence silently (no flag needed).

**Criteria for removal:**
- Two consecutive blocks with identical text (after corrections applied)
- Same speaker ID
- Block length ≥ 15 characters (short "Yes." / "No." blocks are exempt)

---

## RULE 13 — VERBATIM PRESERVATION

**NEVER correct:**
- "uh" / "um" — always preserve
- Stutters: `I -- I was there` (em-dash between repeated words)
- Self-corrections: `it was -- was going to be`
- Trailing off: `and then I -- `
- "Okay." / "All right." / "Mm-hmm." — preserve as spoken

**Filler words:** "uh" and "um" are ALWAYS preserved in legal transcripts.
Deepgram's `remove_filler_words` feature is always OFF.

**Em dashes:** Always rendered as ` -- ` (space + two hyphens + space)
Never use actual em dash character (—).

---

## RULE 14 — TYPOGRAPHY AND SPACING

**Two spaces after every sentence-ending punctuation before a capital letter:**
- `I do.  Thank you.` ✓
- `I do. Thank you.` ✗

**Single space after abbreviations:**
- `Dr. Smith` ✓
- `Ms. Rivera` ✓

**No non-breaking spaces (\xa0):** Replace all with regular double spaces.

**Honorifics in body text:**
`MR.  Smith testified...` (all-caps, two spaces after period)
`MS.  Rivera stated...`

---

## RULE 15 — DOCUMENT STRUCTURE

**Every certified transcript contains exactly these pages in order:**

1. **Caption page** — case style, cause number, court, deponent name, date, time, method, reporter
2. **Appearances page** — all counsel, their clients, their cities
3. **Transcript body** — reporter opening → oath → examination(s) → close
4. **Certificate page** — reporter's certification signature block

**Caption page elements:**
- Court name: ALL CAPS, bold, centered
- Case style: parties bold, centered
- Cause number: bold, centered
- Deponent name: ALL CAPS, bold, centered
- Date, time, method: centered
- Reporter line: bold, centered

**Appearances page:**
- `FOR THE PLAINTIFF:` then attorney name (indented), city (indented)
- `FOR THE DEFENDANT:` then attorney name (indented), city (indented)
- `ALSO PRESENT:` then reporter (indented)

---

## RULE 16 — FONT AND LAYOUT

- Font: Courier New, 12pt throughout
- Line spacing: Double (480 twips)
- Margins: 1.25" left, 1" right/top/bottom
- Tab stops: 360 / 900 / 1440 / 2160 / 2880 twips
- Page size: US Letter (8.5" × 11")
- Lines per page: 25

---

## RULE 17 — WHAT NEVER GOES IN THE CERTIFIED TRANSCRIPT

- Corrections log or audit trail (terminal-only)
- Pre-record chatter
- Post-record conversation
- Spellings sessions (use for back-correction only)
- Technical setup discussion
- Off-the-record recesses content

---

## QUICK REFERENCE — MOST COMMON FIXES

| Raw Error | Correct Fix |
|---|---|
| same effect as a weapon | same force and effect as if given in open court |
| penalty of curtory | penalty of perjury |
| Infection. / Perfection. | Objection. |
| Dissection. / Detection. | Objection. |
| THE COURT REPORTER: | THE REPORTER: |
| They do. (oath) | I do. |
| Mia Bardo / Mia Bardell | Miah Bardot |
| Dr. [attorney name] | MR.  [name]: |
| Numbers spelled as words | Digits (in addresses, dates, ages) |
| Q. [answer text] | A. [answer text] |
| THE REPORTER: [witness answer] | MS. [WITNESS NAME]: [answer] |
| twenty twenty four | 2024 |
| zero eight six four zero | 08640 |
| so help you guide | so help you God |
| past witness / pasture witness | Pass the witness. |
| court border | court reporter |
| remit for this remote deposition | agreement for this remote deposition |
| notice and attorney | noticing attorney |
