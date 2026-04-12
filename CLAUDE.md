# AI_CONTEXT.md — Depo-Pro Transcribe
## Universal AI Coding Assistant Context File

**This file is read by:** Claude, Claude Code, Cursor, Codex, GitHub Copilot,
VS Code AI extensions, and any other AI coding assistant working on this project.

Read this file completely before making any changes to this codebase.
When in doubt about any decision, **stop and ask** rather than guessing.

---

## AI Operating Rules — Read Before Every Session

### Session Protocol
BEFORE: Read `CLAUDE.md` fully and check `STABILIZATION_PLAN.md` for the active phase and step.
DURING: Work one step at a time and keep changes to a single layer.
VERIFY: Run `py_compile` on every modified file and run the verification required by the current plan step.
AFTER: Review `git diff`, then commit the completed step, including any `CLAUDE.md` or `STABILIZATION_PLAN.md` updates made during that step.

### Stop and Ask Rule
If you are unsure about ANY of the following — stop immediately and ask:
- Which layer a change belongs in
- Whether a change could affect transcript meaning
- Rule priority position in `clean_block()`
- Whether a function already exists that does what you're about to write
- Whether a change could break the word map or confidence highlighting

**Guessing is not acceptable in a legal transcript system.**

### Single-Layer Rule
Every change must affect exactly ONE layer.
Do not modify `pipeline/` and `spec_engine/` in the same change.
Do not modify `spec_engine/` and `ui/` in the same change.
If a task requires changes in multiple layers, break it into separate
changes, each verified independently before the next begins.

---

## 1. What This Application Is

**Depo-Pro Transcribe** is a professional Windows desktop application for
certified court reporter Miah Bardot at SA Legal Solutions, San Antonio, Texas.

It transcribes and corrects legal deposition transcripts to conform with
two mandatory standards:
- **Texas Uniform Format Manual (UFM)** — page layout, line types, margins
- **Morson's English Guide for Court Reporters** — punctuation, verbatim rules

The output is a legally admissible transcript document. Every formatting
decision, every correction rule, and every verbatim protection exists because
it is required by these standards or by Texas legal procedure.

**Do not remove, simplify, or "improve" rules without understanding which
legal standard they serve. When in doubt, preserve existing behavior.**

---

## 2. Project Location and Environment

```
Project root:   C:\Users\james\PycharmProjects\depo_transcribe
Virtual env:    C:\Users\james\PycharmProjects\depo_transcribe\.venv
Run app:        .\.venv\Scripts\python.exe app.py
Run tests:      .\.venv\Scripts\python.exe -m pytest
Compile check:  .\.venv\Scripts\python.exe -m py_compile <file>
```

**SEPARATE PROJECT — DO NOT CONFUSE:**
`C:\Users\james\transcript_formatter` is a completely separate application.
Never make changes to `depo_transcribe` that reference or affect
`transcript_formatter`, and vice versa.

---

## 3. Tech Stack

| Component | Technology |
|---|---|
| UI framework | CustomTkinter (NOT standard tkinter — see Section 14) |
| Speech-to-text | Deepgram Nova-3 (direct HTTP via httpx, NOT the SDK) |
| AI correction | Anthropic Claude API (claude-sonnet-4-6) |
| Audio processing | FFmpeg (subprocess calls) |
| Media playback | python-vlc / VLC |
| Document output | python-docx |
| PDF output | reportlab |
| Config/secrets | python-dotenv (.env file) |

---

## 4. Pipeline Contract — What Each Layer May and May Not Do

This is the most important section. Every layer has a defined role.
Violating these boundaries is the most common source of bugs.

### `pipeline/` — Audio and Transcription Only
```
MAY:     Process audio (FFmpeg normalization, chunking)
MAY:     Call Deepgram API and return raw JSON
MAY:     Merge chunks and deduplicate boundary words
MAY:     Write raw .txt and .json output files
MUST NOT: Apply any text corrections
MUST NOT: Make classification decisions (Q vs A vs COLLOQUY)
MUST NOT: Know anything about legal formatting rules
```

### `spec_engine/` — All Intelligence, All Legal Rules
```
MAY:     Apply all 14 deterministic correction rules
MAY:     Classify blocks as Q / A / COLLOQUY / PAREN / FLAG
MAY:     Restructure Q/A, extract objections, map speakers
MAY:     Generate [SCOPIST: FLAG N:] markers
MAY:     Validate output structure
MUST NOT: Touch audio or Deepgram API calls
MUST NOT: Perform document layout or DOCX assembly
MUST NOT: Make network calls of any kind
```

### `spec_engine/ai_corrector.py` — Text Corrections Only
```
MAY:     Correct spelling and grammar in context
MAY:     Resolve homophones with certainty (their/there, know/no)
MAY:     Apply proper noun corrections from the provided list
MAY:     Insert [VERIFY: ...] flags for uncertain corrections
MUST NOT: Change speaker labels or Q/A structure
MUST NOT: Remove or normalize verbatim words (uh, um, yeah, etc.)
MUST NOT: Reorder blocks or merge paragraphs
MUST NOT: Perform formatting (spacing, tabs, line wrapping)
```

### `spec_engine/emitter.py` and `core/correction_runner.py` — Formatting Only
```
MAY:     Apply tab stops, line wrapping, spacing
MAY:     Write python-docx paragraphs with correct typography
MUST NOT: Change the meaning or content of any text
MUST NOT: Apply correction rules
MUST NOT: Make classification decisions
```

### `ufm_engine/` — Document Assembly Only (CURRENTLY INACTIVE)
```
MAY:     Assemble DOCX pages from structured data
MAY:     Apply page layout, margins, headers, footers
MUST NOT: Modify transcript content in any way
STATUS:  Not connected to active pipeline.
         Do NOT import from ufm_engine without a deliberate activation decision.
```

### `ui/` — Display and User Input Only
```
MAY:     Display data, receive user input, trigger pipeline calls
MAY:     Show confidence highlighting, VLC sync, Edit Mode
MUST NOT: Contain business logic or correction rules
MUST NOT: Make direct Deepgram or Claude API calls
MUST NOT: Decide which corrections to apply
```

---

## 5. Forbidden Actions — Never Do These

These protect the legal record. Violating them corrupts the transcript.

```
NEVER normalize or remove verbatim words:
  uh, um, ah, uh-huh, uh-uh, yeah, yep, yup, nope, nah,
  gonna, wanna, gotta, b-b-bank (stutters), word -- (false starts)
  These are testimony. Changing them alters the legal record.

NEVER change text inside _render_with_confidence()
  This function applies color tags only. It must never replace
  textbox content. Doing so corrupts the file on save.

NEVER save from the raw textbox
  _save_transcript() must save _canonical_text, not textbox content.
  These differ during confidence highlighting.

NEVER change the order of rules in clean_block()
  Rules 1-14 have dependencies. Running them out of order
  produces incorrect output. The order is documented in Section 10.

NEVER add correction logic to pipeline/
  pipeline/ handles audio and Deepgram only. All text intelligence
  belongs in spec_engine/.

NEVER connect ufm_engine/ to the pipeline without an explicit
  activation decision and full testing.

NEVER add a pip dependency without updating requirements.txt
  and explaining why it is necessary.

NEVER delete a test — fix the code or update the test with an
  explanation of why the contract changed.
```

---

## 6. Architectural Stability Policy

**The current architecture is functional. Do not refactor it for theoretical
improvements.**

This application is a legal transcription system, not a software architecture
demonstration. The pipeline works, transcripts are produced correctly, and the
separation between layers is deliberate and appropriate for this domain.

```
ALLOWED:    Incremental changes — add a function, fix a bug, add a rule
ALLOWED:    Changes within a single layer that don't affect other layers
ALLOWED:    New features that follow the existing pattern

NOT ALLOWED: Moving logic across layers "for cleanliness"
NOT ALLOWED: Collapsing pipeline/ and spec_engine/ into a single layer
NOT ALLOWED: Rewriting a working module because it "could be cleaner"
NOT ALLOWED: Applying generic software patterns that conflict with domain needs
```

### The Anti-Generic-Refactor Rule

Depo-Pro is a **legal transcription system**, not a generic web app or
data pipeline. Recommendations from AI tools that are based on general
software engineering patterns must be evaluated against domain requirements
before being accepted.

If a recommendation would:
- Remove keyterms → REJECT (keyterms directly improve accuracy for legal names)
- Collapse pipeline/ into spec_engine/ → REJECT (they serve different domains)
- Remove filler word handling → REJECT (verbatim record is legally required)
- Simplify the correction rule system → EVALUATE CAREFULLY

**The test for any architectural change:**
"Does this make the legal transcript more accurate, more traceable,
or easier to verify? Or does it just make the code look cleaner?"

If the answer is "it just looks cleaner" — do not make the change.

---

## 7. Architecture Decisions Log

These decisions were made deliberately. Do not reverse them without
re-reading the reason column and confirming the domain impact.

| Decision | Reason | Do Not Reverse Because |
|---|---|---|
| Direct HTTP to Deepgram (not SDK) | SDK had version instability | Direct HTTP is stable and fully controlled |
| Nova-3 only (not Nova-2) | Nova-3 has significantly lower WER | Nova-2 is superseded |
| Keyterms kept in pipeline | Boosts case-specific names (Coger, Murphy Oil, 2025CI19595) | Without keyterms, proper nouns have higher error rates |
| afftdn over neural denoisers | Neural denoisers increase WER for ML models | They sound better but hurt Deepgram accuracy |
| 24kHz sample rate | Preserves 4-8kHz sibilant band for name disambiguation | Lower rates lose consonant distinction (Coger vs Coker) |
| smart_format=false | Keeps Deepgram from rewriting dates/currency while filler_words remain enabled | Turning it on increases formatting drift for legal transcript review |
| Two correction passes (Python then AI) | Python = fast + free for deterministic patterns; AI = context-dependent cases only | Merging them makes simple fixes slow and expensive |
| CorrectionRecord on every change | Audit trail for corrections log and diff viewer | Without it, changes are invisible to the court reporter |
| run_logger.py for snapshots | Single tracing system | Do not create additional ad-hoc logging systems |

---

## 8. Complete File Map

### Entry Points
```
app.py                           — Launcher. Entry point is __main__.
config.py                        — All pipeline constants and API key loading.
app_logging.py                   — Logging configuration.
requirements.txt                 — All pip dependencies.
```

### UI Layer (`ui/`)
```
ui/app_window.py                 — Main window, tab container, wiring.
ui/tab_transcribe.py             — Transcribe tab: file picker, case info,
                                    NOD upload, keyterms, CREATE TRANSCRIPT.
ui/tab_transcript.py             — Transcript tab: text display, VLC sync,
                                    confidence highlighting, Edit Mode,
                                    Find & Replace (Ctrl+H), right-click menu.
ui/tab_corrections.py            — Corrections tab: Pass 1 + Pass 2 + DOCX export.
```

### Core Layer (`core/`)
```
core/job_runner.py               — Orchestrates transcription job (caller only,
                                    minimal logic, runs in background thread).
core/correction_runner.py        — Orchestrates Pass 1 pipeline.
                                    Contains format_blocks_to_text().
core/file_manager.py             — Case folder creation, path building.
core/pdf_extractor.py            — Extracts case data from NOD PDFs.
core/intake_parser.py            — AI-assisted NOD data extraction.
core/keyterm_extractor.py        — Extracts proper nouns for Deepgram keyterms.
core/word_data_loader.py         — Loads Deepgram word-level JSON for confidence.
core/confidence_docx_exporter.py — Exports confidence-highlighted review DOCX.
core/transcript_merger.py        — Merges Deepgram utterances at chunk boundaries.
core/ufm_field_mapper.py         — Maps NOD data to UFM field names.
core/vlc_player.py               — Thin VLC wrapper with graceful fallback.
core/docx_formatter.py           — DOCX formatting utilities.
```

### Pipeline Layer (`pipeline/`)
```
pipeline/preprocessor.py         — FFmpeg: mono → 24kHz → highpass → denoise
                                    → loudnorm. Output cached as normalized_*.wav.
pipeline/chunker.py              — Splits audio >10min into 600s chunks, 20s overlap.
pipeline/transcriber.py          — HTTP POST to Deepgram. Returns words + utterances.
pipeline/assembler.py            — Merges chunks, deduplicates boundary words.
pipeline/processor.py            — run_pipeline() public API.
pipeline/exporter.py             — Writes .txt and .json to case folder.
```

### Spec Engine (`spec_engine/`)
```
spec_engine/block_builder.py     — Deepgram utterance JSON → List[Block].
spec_engine/models.py            — All data classes: Block, BlockType, Word,
                                    JobConfig, CorrectionRecord, ScopistFlag, etc.
spec_engine/processor.py         — process_blocks(): orchestrates all sub-steps.
spec_engine/corrections.py       — 14 deterministic correction rules.
                                    clean_block() is the master function.
spec_engine/classifier.py        — Labels blocks: Q/A/COLLOQUY/PAREN/FLAG.
spec_engine/qa_fixer.py          — Splits inline Q/A, merges orphans.
spec_engine/speaker_mapper.py    — Maps Speaker 0/1/2 → real names.
spec_engine/objections.py        — Extracts objections to separate SP blocks.
spec_engine/validator.py         — Post-pipeline structural validation.
spec_engine/ai_corrector.py      — Pass 2 AI correction via Claude API.
spec_engine/emitter.py           — python-docx line writer with UFM tab stops.
spec_engine/document_builder.py  — Assembles full DOCX from processed blocks.
spec_engine/parser.py            — Parses transcript text into blocks.
spec_engine/exporter.py          — Exports final DOCX and PDF.
spec_engine/run_logger.py        — Pipeline snapshot logging. Use this —
                                    do not create separate logging systems.
spec_engine/pages/               — One file per UFM page type (title, caption,
                                    certificate, witness index, exhibit index,
                                    corrections log, post-record, changes page).
```

### UFM Engine (`ufm_engine/`) — INACTIVE
```
ufm_engine/                      — Future template-rendering subsystem.
                                    NOT connected to the active pipeline.
```

---

## 9. Data Flow

### Transcription Path
```
User selects audio
    → ui/tab_transcribe.py → core/job_runner.py (thread)
    → pipeline/preprocessor.py   (FFmpeg normalization, cached WAV)
    → pipeline/chunker.py        (split >600s, 20s overlap)
    → pipeline/transcriber.py    (Deepgram Nova-3, keyterms)
    → pipeline/assembler.py      (merge chunks, dedup)
    → pipeline/exporter.py       (write {stem}.txt + {stem}.json)
    → ui/tab_transcript.py       (display + VLC sync)
```

### Correction Path — Pass 1 (Python, deterministic, always runs)
```
User clicks "Run Corrections"
    → core/correction_runner.py (thread)
    → spec_engine/block_builder.py           (JSON → List[Block])
    → spec_engine/processor.py process_blocks():
        1. corrections.py   apply_corrections()
        2. speaker_mapper.py map_speakers()
        3. classifier.py    classify_blocks()
        4. qa_fixer.py      fix_qa_structure()
        5. objections.py    extract_objections()
        6. classifier.py    classify_blocks() (second pass)
        7. validator.py     validate_blocks()
    → format_blocks_to_text()
    → write {stem}_corrected.txt
    → write {stem}_corrections.json  (CorrectionRecord audit trail)
```

### Correction Path — Pass 2 (AI, optional)
```
User clicks "Run AI Corrections"
    → spec_engine/ai_corrector.py
    → split at paragraph boundaries (MAX_CHARS = 12000)
    → Claude API per chunk
    → reassemble + renumber [SCOPIST: FLAG N:]
    → write {stem}_ai_corrected.txt
```

### DOCX Export Path
```
User clicks "Export DOCX"
    → spec_engine/document_builder.py
    → spec_engine/emitter.py      (UFM tabs + line wrap)
    → spec_engine/pages/*.py      (title, appearances, certificate, etc.)
    → spec_engine/exporter.py     (final DOCX + PDF)
```

---

## 10. Correction Rules — Pass 1

All in `spec_engine/corrections.py`. Order in `clean_block()` MUST NOT change.

```
Priority  Function                        What it does
--------  ------------------------------  ----------------------------------------
1         apply_multiword_corrections()   Legal phrase variants → canonical form
2         apply_case_corrections()        confirmed_spellings from NOD
3         apply_universal_corrections()   60 single-word fixes
4a        apply_number_to_word()          Numbers 1-10 in count context → words
4b        apply_date_normalization()      Date mashups → [SCOPIST: FLAG N:]
4c        apply_sentence_start_number()   "3 witnesses" → "Three witnesses"
5         apply_artifact_removal()        Deepgram duplicates (4+ char only)
6         fix_spaced_dashes()             word--word → word -- word
7         fix_uh_huh_hyphenation()        "uh huh" → "uh-huh"
8         fix_even_dollar_amounts()       $450.00 → $450
9         fix_conversational_titles()     "mister Garcia" → "Mr. Garcia"
10        normalize_spaces()              Multiple spaces → single
11        capitalize_first()              First character uppercase
12        enforce_direct_address_comma()  "Yes sir" → "Yes, sir."
13        enforce_terminal_punctuation()  Ensure . ? or ! at end
14        normalize_sentence_spacing()    Two spaces after sentence punct
```

---

## 11. AI Corrector Details

```
Model:    claude-sonnet-4-6
Trigger:  User action only — never automatic
Chunks:   MAX_CHARS = 12000, paragraph boundaries only
Cost:     ~$0.31 per 1-hour deposition (4 chunks)
```

---

## 12. Change Tracking — CorrectionRecord

Every rule that changes text MUST create a CorrectionRecord.

```python
records.append(CorrectionRecord(
    original=old_text,
    corrected=new_text,
    pattern="rule_name:detail",   # e.g. "confirmed_spelling:Koger"
    block_index=block_index,
))
```

This is the audit trail. It powers the corrections log.
Do not skip it. Use `spec_engine/run_logger.py` for pipeline snapshots.

---

## 13. Case Folder Structure

```
{base}/                          default: C:\Users\james\Depositions\
  {YYYY}/{Mon}/{CauseNumber}/{last_first}/
    Deepgram/
      {stem}.txt                 raw transcript
      {stem}.json                Deepgram data (words + timestamps)
      {stem}_corrected.txt       after Pass 1
      {stem}_corrections.json    CorrectionRecord objects
      {stem}_ai_corrected.txt    after Pass 2 (if run)
      {stem}_ufm_fields.json     case metadata
    source_docs/
      {NOD}.pdf
      reporter_notes.txt         (optional)
    keyterms.json
```

---

## 14. CustomTkinter Rules

```python
# bind_all is blocked — use winfo_toplevel().bind()
self.bind_all(...)                               # WRONG
self.winfo_toplevel().bind("<Control-h>", ...)   # CORRECT

# CTkTextbox.bind() requires add=True (not False, not "+")
textbox.bind("<Button-3>", handler, add=False)   # WRONG
textbox.bind("<Button-3>", handler, add=True)    # CORRECT
textbox._textbox.bind("<Button-3>", handler)     # CORRECT (inner widget)

# tk.Menu — no color params on Windows (silent fail)
tk.Menu(self, tearoff=0, bg="#000")              # WRONG
tk.Menu(self, tearoff=0)                         # CORRECT

# Right-click coordinates — must translate to inner widget space
inner_x = event.x_root - widget.winfo_rootx()
inner_y = event.y_root - widget.winfo_rooty()
```

---

## 15. Word Map Invariants

```
1. Word replacement → shift ALL subsequent char_start/char_end by length delta
2. After replacement → reset confidence to 1.0 (clears highlight)
3. _build_word_map → whole-word boundary matching (prevents drift)
4. widget.see() → only when word is NOT already visible
5. Sync timer → every 250ms during playback
```

---

## 16. Confidence Highlighting Invariant

`_render_with_confidence()` applies color tags ONLY.
It must NEVER replace textbox content.
Replacing content corrupts the file on save (prior regression — do not repeat).

---

## 17. Key Invariants — Never Violate

1. Verbatim words are NEVER changed (uh, um, yeah, nope, etc.)
2. `_render_with_confidence()` — color tags only, never replace content
3. `_save_transcript()` saves `_canonical_text`, not raw textbox
4. Rule order in `clean_block()` — 14 rules — MUST NOT change
5. Character replacement — MUST shift all subsequent word map offsets
6. `smart_format` stays OFF while `filler_words` stays ON for Nova-3

---

## 18. UFM Formatting Reference — Authoritative Spec

### Line Formats

```
Q line:  \t + "Q." + TWO SPACES + text
         Example: \tQ.  Did you go there?
         IMPORTANT: Two literal spaces after Q. — NOT a tab.

A line:  \t + "A." + TWO SPACES + text
         Example: \tA.  Yes, sir.
         IMPORTANT: Two literal spaces after A. — NOT a tab.

SP line: \t\t\t + LABEL + ": " + TWO SPACES + text
         Example: \t\t\tMR. GARCIA:  Objection.  Form.
         Three tabs before the label.

PAREN:   ({text})
         Example: (Whereupon, a recess was had.)

FLAG:    [SCOPIST: FLAG N: description]
```

### Continuation Lines

```
ALL line types — continuation wraps to LEFT MARGIN.
No indent on continuation. Not aligned to text start.

Correct:
    \tQ.  This is the beginning of a very long question that
continues here at the left margin on the next line.

Wrong:
    \tQ.  This is the beginning of a very long question that
         continues here aligned to the Q. text start.
```

### Speaker Label Rule

```
The label (SP prefix) appears ONLY on the FIRST paragraph
of a multi-paragraph block from the same speaker.

Subsequent paragraphs from the same speaker are plain text
indented to the SP position (three tabs) with NO label.

Correct:
    \t\t\tTHE REPORTER:  This is Cause Number 2025-CI-19595.

    \t\t\tThis deposition is being taken in accordance with...

    \t\t\tCounsel, will you please state your agreement...

Wrong:
    \t\t\tTHE REPORTER:  This is Cause Number 2025-CI-19595.

    \t\t\tTHE REPORTER:  This deposition is being taken...
```

### Court Reporter Label

```
CORRECT:   THE REPORTER:
WRONG:     THE COURT REPORTER:
WRONG:     REPORTER:
WRONG:     COURT REPORTER:

This is UFM Rule 13. It is enforced by both the Python
pipeline (speaker_mapper.py) and the AI system prompt.
```

### Witness Introduction Block (Fixed Template)

This block is generated from a template. It does not vary
in structure — only the witness name and attorney name change.

```
[center tab]WITNESS FULL NAME,
having been first duly sworn, testified as follows:

[center tab]EXAMINATION

BY MR./MS. [ATTORNEY LAST NAME]:
```

Rules:
- Witness name: ALL CAPS, bold, centered, followed by comma
- "having been first duly sworn..." — left margin, not indented
- "EXAMINATION" — ALL CAPS, bold, centered
- "BY MR./MS. [NAME]:" — left margin, not indented, colon at end
- The attorney name on the BY line is the examining attorney

### Court Reporter Preamble (Three-Paragraph Format)

Standard opening preamble. Only first paragraph carries the label.

```
\t\t\tTHE REPORTER:  This is Cause Number [CAUSE#]: 
[Plaintiff] versus [Defendant], Defendant; in the District 
Court, [Nth] Judicial District, [County] County, Texas.

\t\t\tThis deposition is being taken in accordance with the 
Texas Rules of Civil Procedure.  I am [REPORTER NAME], Court 
Reporter, licensed in Texas, No. [CSR#].

\t\t\tCounsel, will you please state your agreement for this 
deposition and state your name and affiliation for the record?
```

Punctuation rules for the case style line:
- Colon after cause number: `Cause Number 2025-CI-19595:`
- Semicolon after defendant designation: `Inc., Defendant;`
- Two spaces after all sentence-ending punctuation

### Typography and Page Layout

```
Font:          Courier New, 12pt
Spacing:       Double-spaced
Margins:       Left 1.25" / Right 1.0" / Top 1.0" / Bottom 1.0"
Lines per page: 1–25 (line numbers at right margin)

Tab stops:
  Stop 1:  0.5"  = 720 twips   (left aligned)   ← Q./A. indent
  Stop 2:  1.0"  = 1440 twips  (left aligned)   ← Q./A. text start
  Stop 3:  1.5"  = 2160 twips  (left aligned)   ← SP label start
  Stop 4:  center of page      (center aligned)  ← headers/witness name

NOTE: Current emitter.py uses 360/900/1440/2160 twips.
These do NOT match the 720/1440/2160 spec above.
Correcting the tab stops is a Phase 7 task.
```

### Numbers in Testimony

```
Numbers 0–9 in testimony text must be spelled out:
  "I have 3 questions"  → "I have three questions"
  "page 2"              → "page two"

Exceptions — keep as numerals:
  Case numbers:    2025CI19595
  Exhibit numbers: Exhibit No. 15
  Addresses:       123 Main Street
  Zip codes:       78216
  CSR numbers:     No. 12129
  Judicial district: 408th Judicial District
  Times:           10:08 a.m.
  Dates:           03/24/2026
```

---

## 19. Deepgram Configuration

```python
model        = "nova-3"   # or "nova-3-medical"
smart_format = "false"
punctuate    = "true"
paragraphs   = "false"
diarize      = "true"
utterances   = "true"
filler_words = "true"
numerals     = "false"
utt_split    = 1.2        # adjustable in UI
keyterms     = [...]      # up to 100, from NOD PDF / reporter notes
```

---

## 20. Testing Standards

```powershell
.\.venv\Scripts\python.exe -m pytest                    # all tests
.\.venv\Scripts\python.exe -m pytest <file> -v          # specific file
.\.venv\Scripts\python.exe -m py_compile <file>         # compile check
```

Baseline: 363 passing, 34 failing (all documented in STABILIZATION_PLAN.md).
Do not introduce new failures. Run suite before and after every change.

All tests must be: offline, deterministic, one assertion per method,
exact equality (not substring). Test file ships with the rule.

---

## 21. Adding a Correction Rule — Four Gates

**Gate 1 — Define** (before coding)
What it fixes (one sentence) + 3 real examples + 2 false-positive guards
+ priority slot in clean_block()

**Gate 2 — Implement**
Standalone function in corrections.py + registered in clean_block()
+ CorrectionRecord on every change + compile check

**Gate 3 — Test** (five classes)
HappyPath / FalsePositiveGuard / PunctuationBoundary / PassOrdering / Interface

**Gate 4 — Integrate**
Full suite: zero regressions before merging

---

## 22. Safe Change Checklist

```
[ ] Correct layer for this change? (Section 4)
[ ] Violates any forbidden action? (Section 5)
[ ] Touches a known invariant? (Section 17)
[ ] Test covering this behavior?
[ ] Affects word map? (shift offsets if yes)
[ ] Affects confidence highlight? (never replace content)
[ ] py_compile run on changed file?
[ ] Full test suite run?

If any answer is unclear → STOP and ask.
```

---

## 23. Known Issues

See `STABILIZATION_PLAN.md` for the complete phased plan.

| Failure | Count | Cause | Phase |
|---|---|---|---|
| `from formatter import ...` | 22 | Module renamed | 1 |
| `main.py not found` | 4 | Entry point is `app.py` | 1 |
| Path separator | 1 | `\\` vs `os.path.join` | 1 |
| Tab format mismatch | 2 | Wrong tab in format_blocks_to_text | 2 |
| `from ai_tools import ...` | 2 | Module not yet built | 1 |
| `docxtpl` missing | 1 | ufm_engine inactive | 1 |

Zero-coverage functions (Phase 3): `apply_case_corrections`,
`fix_conversational_titles`, `fix_even_dollar_amounts`,
`fix_uh_huh_hyphenation`, `normalize_time_and_dashes`, `fix_qa_structure`
