# NOD Ingestion Diagnostic

Generated: 2026-04-27
Subject: Why did uploading the Caram NOD not populate `confirmed_spellings`?

---

## Verification

- CWD: `C:\Users\james\PycharmProjects\depo_transcribe`
- `training_corpus/caram_2026_04_09/`: present
- `docs/transcription_standards/depo_pro_style.md`: present

All preconditions satisfied.

---

## Step 1 — Caram corpus folder inventory

`training_corpus/caram_2026_04_09/` contents:

| Filename | Bytes | Type | NOD-related? |
|---|---|---|---|
| `case_id.txt` | 13 | one-line plaintext, contains `DC-25-13430\n` | no |
| `ground_truth.txt` | 143,176 | UTF-8 plaintext, byte-identical to `pipeline_output_pass1_2026-04-26.txt` (pre-seeded copy, not hand-corrected) | no |
| `job_config.json` | 66,372 | JSON, copied from `{case}/source_docs/job_config.json` | no |
| `notes.md` | 1,323 | markdown stub | no |
| `pipeline_output_pass1_2026-04-26.txt` | 143,176 | UTF-8 plaintext, the deterministic Pass 1 output | no |

**Finding:** No NOD or NOD-derived file lives inside the corpus folder. This is correct per `training_corpus/README.md` — the corpus stores derived evidence (pipeline outputs + ground truth), not source documents. The NOD itself, if present, lives in the case folder under `Depositions/`, not here.

---

## Step 2 — Caram `job_config.json` analysis

Read from `training_corpus/caram_2026_04_09/job_config.json` (a copy of `{case}/source_docs/job_config.json`):

- Top-level keys: `model`, `audio_quality`, `low_confidence_words`, `version`, `ufm_fields` (5 keys)
- `confirmed_spellings`: **NOT PRESENT** (the key itself is missing — not just empty)
- `low_confidence_words`: 575 entries
- `ufm_fields` populated keys: `speaker_map` (with 5 speakers), `speaker_map_verified` = True
- `ufm_fields` UNPOPULATED keys (None / empty): `cause_number`, `witness_name`, `case_style`, `depo_date`, `depo_date_year/month/day`, `defense_counsel`, `plaintiff_counsel`, `reporter_name`, all the rest

**Finding:** Caram's `job_config.json` has **zero** confirmed_spellings entries. None of the proper-noun fields that an NOD would supply (cause_number, witness_name, case_style, defense_counsel, etc.) are populated. Only the speaker_map — which gets populated by a different UI flow (manual speaker mapping after transcription) — is filled in.

This is the second finding the prompt asked for: confirmed_spellings is missing, not present-but-empty.

---

## Step 3 — Pipeline output proper-noun audit (sample)

The transcript text in `pipeline_output_pass1_2026-04-26.txt` contains proper-noun garbles. Examples drawn from `low_confidence_words`:

```json
{"word": "biana", "confidence": 0.6132, "start": 8.64, "end": 9.04}
```

The witness's name is **Bianca Caram, M.D.** (per session context). Deepgram transcribed her first name as `biana` at 0.61 confidence in the first ten seconds of audio. A populated `confirmed_spellings` mapping `Biana Caram → Bianca Caram, M.D.` would have caught this in the AI Correct pass — the entry exists in the orphan job_config (see Step 6) but never reached the active case.

Other low-confidence proper-noun garbles in Caram's pipeline output (sampled, not exhaustive):

| Token | Confidence | Likely intended |
|---|---|---|
| `biana` | 0.61 | Bianca |
| `brittany` | 0.40 | (proper noun, unverified — probably a person mentioned in testimony) |
| `swear` | 0.25 | likely the swearing-in oath |
| `pass` | 0.31 | likely "pass the witness" — the orphan job_config has `Past witness → Pass the witness.` |
| `cause` | 0.38 | likely "Cause Number" — orphan has `cop number → Cause Number` |

**Finding:** The pipeline output has the exact class of errors that NOD-derived `confirmed_spellings` is designed to fix. None of those fixes ran for this case because confirmed_spellings is empty.

ANOMALY: 246 distinct low-confidence words in this transcript. That's high. Either the audio quality is challenging (the case used the `ENHANCED (fair audio)` preprocessing tier), or the lack of NOD-derived keyterms compounded the problem during Deepgram transcription itself (keyterms boost recognition before transcription, separate from confirmed_spellings which fixes after).

---

## Step 4 — Codebase search for NOD handling

The NOD ingestion path **exists and is fully wired**. Found these components:

| File | Function / Class | Role | Caller |
|---|---|---|---|
| `core/intake_parser.py` | `parse_intake_document()` | AI-driven (Claude) extraction of NOD text → `IntakeParsedResult` with `confirmed_spellings: dict` field | `core/pdf_extractor.py:288` |
| `core/intake_parser.py` | `IntakeParsedResult` dataclass | Holds extracted fields including `confirmed_spellings`, `all_proper_nouns`, `keyterm_map`, etc. | (return value type) |
| `core/case_vocab.py` | `build_case_vocab_from_text()` | Regex fallback when AI parser unavailable; produces a smaller `confirmed_spellings` mostly for diacritics | `core/pdf_extractor.py:34, 54` |
| `core/pdf_extractor.py` | `extract_case_info_from_pdf()` (line 279) | Hybrid pipeline: regex + AI; returns dict with `confirmed_spellings` key (line 343) | `ui/tab_transcribe.py:1977` |
| `core/job_runner.py` | `run_transcription_job()` (line 81) | Accepts `confirmed_spellings: dict \| None` parameter | `ui/tab_transcribe.py:2260` |
| `core/job_config_manager.py` | `merge_and_save()` (line 172) | Persists confirmed_spellings to `{case}/source_docs/job_config.json` | `core/job_runner.py:348` |
| `core/correction_runner.py` | reads confirmed_spellings during Pass 1 (lines 121, 232, 234) | Populates `JobConfig.confirmed_spellings` for the corrections engine | (downstream) |
| `spec_engine/nod_corrections.py` | `apply_nod_corrections()` | Applies confirmed_spellings to blocks during Pass 1 | `spec_engine/processor.py:82` |
| `spec_engine/ai_corrector.py` | (lines 246-249) | Injects up to 40 confirmed_spellings entries into the Claude AI Correct prompt | (Pass 2) |

No dead code among these. `parse_intake_document` has tests (`core/tests/test_intake_parser.py`). `apply_nod_corrections` has tests (`spec_engine/tests/test_nod_corrections.py`). The path is real and exercised.

---

## Step 5 — UI search for NOD upload

Found the upload entry point in `ui/tab_transcribe.py`. Trace:

1. **Line 1962** — `filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")])` opens the file picker
2. **Line 1969** — `saved_pdf_path = self._persist_source_doc(filepath)` copies the PDF into `{case_root}/source_docs/`
3. **Line 1977** — `extract_case_info_from_pdf(saved_pdf_path, ...)` runs in a background thread
4. **Line 1981** — result delivered to `_apply_pdf_results(results, ...)` on the main thread
5. **Line 2079** — `self._confirmed_spellings = dict(intake_result.confirmed_spellings)` stores the extracted spellings on the tab instance
6. **Line 2270** — `confirmed_spellings=self._confirmed_spellings` passed into `run_transcription_job(...)`
7. **`core/job_runner.py:348`** — `merge_and_save(...confirmed_spellings=...)` persists to `job_config.json`

The UI element is the **Upload NOD / PDF** button (`self._upload_pdf_btn`, label includes the emoji `📄`).

---

## Step 6 — Caram-specific upload trace

NOD-shaped PDFs found on disk under the Caram cause folder:

| Path | Bytes (approx) | Useful content? |
|---|---|---|
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/caram_dr/source_docs/04-09-26 @ 8am - Marynell Maloney Law Firm (1).pdf` | (NOD PDF) | Yes — this is the actual NOD |
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/m.d._bianca/source_docs/04-09-26 @ 8am - Marynell Maloney Law Firm (1).pdf` | duplicate of above | Yes |
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/m.d._bianca/source_docs/04-10-26 @ 9am & 1pm - Volk & McElroy (3).pdf` | (different case PDF) | Stray — belongs to a different deposition |
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/m.d._bianca/source_docs/PDF CARAM.pdf` | (Caram-related PDF) | Likely useful |

**The decisive finding** — comparing the two `job_config.json` files under the same cause:

| Folder | mtime | `confirmed_spellings` count | Populated UFM fields |
|---|---|---|---|
| `caram_dr/source_docs/job_config.json` | 2026-04-26 22:43 (later) | **0** (key absent) | `speaker_map`, `speaker_map_verified` only |
| `m.d._bianca/source_docs/job_config.json` | 2026-04-26 22:23 (earlier) | **31** | `cause_number`, `plaintiff_name`, `defendant_name`, `case_style`, `court_caption`, `court_type`, `county`, `state`, `judicial_district`, `depo_type`, `depo_date`, `witness_name`, `defense_counsel`, `reporter_*`, `ordering_*`, `filing_*`, `copy_attorneys`, `csr_required` (~30 keys) |

The `m.d._bianca/source_docs/job_config.json` contains the **fully-extracted AI intake output**, with 31 high-quality confirmed_spellings:

```
'Biana Caram'                    -> 'Bianca Caram, M.D.'
'Marynell Maloney'               -> 'Marynell Maloney Law Firm, PLLC'
'Past witness'                   -> 'Pass the witness.'
'cop number'                     -> 'Cause Number'
'cost number'                    -> 'Cause Number'
'Injection form'                 -> 'Objection.  Form.'
'Bleeding'                       -> 'Leading.'
'Steed Dunill Reynolds Bailey Stephenso' -> 'Steed Dunnill Reynolds Bailey Stephenson LLP'
... 23 more ...
```

These are exactly the proper-noun corrections needed to fix the `caram_dr/` transcript. They are sitting in an orphan folder.

ANOMALY: The folder name `m.d._bianca/` strongly suggests the witness's lastname field was filled with `M.D.` (the title) during initial intake — the case-folder builder produces `{lastname}_{firstname}` so `m.d._bianca` implies `lastname=M.D., firstname=Bianca`. The user evidently noticed the mistake, abandoned that intake, and re-ran under `caram_dr/` (`lastname=caram, firstname=dr`), but never re-ran the NOD upload in the new folder — so the AI extraction's results stayed orphaned in the abandoned path.

---

## Step 7 — Synthesis

### 1. Does an NOD ingestion path exist in the codebase?

**Yes — fully present and wired end-to-end.** The path is:

```
PDF file
  → ui/tab_transcribe.py upload button
  → _persist_source_doc copies into source_docs/
  → extract_case_info_from_pdf (pdf_extractor.py)
  → parse_intake_document AI extraction (intake_parser.py)
  → result.confirmed_spellings stored on tab instance
  → passed through run_transcription_job (job_runner.py)
  → merge_and_save writes to job_config.json (job_config_manager.py)
  → read by correction_runner.py during Pass 1
  → applied by spec_engine/nod_corrections.py
  → also injected into AI Correct prompt by spec_engine/ai_corrector.py (Pass 2)
```

The path has tests on at least the parser end (`test_intake_parser.py`) and the application end (`test_nod_corrections.py`).

### 2. If it exists, did it run for Caram?

**No — not for the active `caram_dr/` folder. Yes — for the abandoned `m.d._bianca/` folder.**

Evidence: the abandoned folder's `job_config.json` contains 31 high-quality `confirmed_spellings` entries plus ~30 populated UFM fields, all consistent with successful AI intake of the Maloney NOD. The active folder's `job_config.json` has no `confirmed_spellings` key and only the post-transcription speaker_map populated.

The user almost certainly clicked Upload NOD/PDF once — under the wrong witness name (`M.D., Bianca`) — extraction succeeded, then the user noticed the folder was wrong, started over under `caram_dr/`, and never re-ran the upload.

### 3. If it ran, did it work correctly?

**Yes** — for the abandoned folder, the AI intake produced exactly the right output. 31 confirmed_spellings entries that include the witness name garble (`Biana → Bianca Caram, M.D.`), the law firm (`Marynell Maloney → Marynell Maloney Law Firm, PLLC`), and a useful set of objection/legal-vocabulary garbles (`Injection form → Objection. Form.`, `Past witness → Pass the witness.`, `cop number → Cause Number`). UFM fields are populated coherently with the case data the NOD describes.

The path is not broken. It produced the right output.

### 4. What's the gap between what James expected and what exists?

The expectation was that uploading the NOD would populate the active case's `confirmed_spellings`. The reality is that the upload did populate `confirmed_spellings` — but for an *earlier intake instance* of the same case (in folder `m.d._bianca/`), which the user then abandoned by switching the lastname/firstname fields and re-running the case under `caram_dr/`. The 31 extracted entries live in the orphan folder and never reach the active case because:

- the witness-name fields drive the case folder path via `core/file_manager.build_case_path()`,
- changing those fields creates a new case folder,
- `_confirmed_spellings` is held only on the tab instance and is reset to `{}` by `_reset_case_state()` (called when the audio file changes — which it didn't here, but which means the value isn't case-stable in general), and
- nothing in the UI flow detects "you have an existing intake for the same cause-number / NOD elsewhere" and offers to migrate it.

Independently, line 355 of `core/job_runner.py` (`confirmed_spellings=confirmed_spellings if confirmed_spellings else None`) means an empty `_confirmed_spellings` dict won't even *replace* an existing populated one — but if the field was never set in the new folder's `job_config.json`, "preserve existing" preserves nothing and the field stays absent.

This is fundamentally a **session continuity / folder migration gap**, not a broken NOD ingestion feature. The feature works. The user's workflow exposed an edge case where mid-intake folder renaming silently abandons extracted data.

---

## Files inventory

| File | Lines | Bytes |
|---|---|---|
| `training_corpus/caram_2026_04_09/case_id.txt` | 1 | 13 |
| `training_corpus/caram_2026_04_09/ground_truth.txt` | (matches pipeline_output) | 143,176 |
| `training_corpus/caram_2026_04_09/job_config.json` | (JSON) | 66,372 |
| `training_corpus/caram_2026_04_09/notes.md` | ~30 | 1,323 |
| `training_corpus/caram_2026_04_09/pipeline_output_pass1_2026-04-26.txt` | (transcript) | 143,176 |
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/caram_dr/source_docs/job_config.json` | (JSON) | (66,372 — copied to corpus) |
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/m.d._bianca/source_docs/job_config.json` | (JSON) | (~28KB) |
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/caram_dr/source_docs/04-09-26 @ 8am - Marynell Maloney Law Firm (1).pdf` | n/a | (PDF binary) |
| `C:/Users/james/Depositions/2026/Apr/DC-25-13430/m.d._bianca/source_docs/04-09-26 @ 8am - Marynell Maloney Law Firm (1).pdf` | n/a | (duplicate PDF) |
| `core/intake_parser.py` | (source) | (read) |
| `core/pdf_extractor.py` | (source) | (read) |
| `core/case_vocab.py` | (source) | (read first 100 lines) |
| `core/job_runner.py` | (source) | (read relevant sections) |
| `core/job_config_manager.py` | (source) | (read relevant sections) |
| `ui/tab_transcribe.py` | (source) | (read sections 1960-2080, 2255-2275) |
| `spec_engine/nod_corrections.py` | (source) | (read first 30 lines) |

Sizes for case-folder PDFs not measured precisely; sizes for source files not measured (only relevant excerpts read).
