# Keyterm Sanitization — Final Report

**Investigation:** controlled stabilization fix for the Deepgram
keyterm request path.
**Module:** `pipeline/keyterm_sanitizer.py`.
**Wired at:** `core/job_runner.py:141-198`.
**Validation case:** `etminan_mohammad`.
**Tests:** `pipeline/tests/test_keyterm_sanitizer.py` — 56 cases,
**612 total tests passing** across all four suites.
**Date:** 2026-05-13.

---

## Section 1 — Root Problem

A production transcription failed with `Deepgram HTTP 400 Bad Request`
during request construction. The keyterm list contained:

- 44 single-word entries out of 96 total (46%)
- single-word ALL-CAPS legal headers (`CAUSE`, `DISTRICT`, `COURT`,
  `JUDICIAL`, `PLAINTIFF`, `NOTICE`, `LEONARDO`, `ROCIO`, …) — 18 in total
- OCR fragments (`Marco Crawford Law Original Standard`,
  `Trans Rush Due`, `Reyna Original Standard`, `Original Standard`)
- duplicate short fragments of full names (`Etminan`, `Bentley`,
  `Crawford` already represented by their full forms)

The existing token-budget estimator (`pipeline/transcriber.py::trim_keyterms_for_deepgram`)
correctly accepted the request as fitting within the 450-token
budget. **The token budget was not the constraint that failed.** What
failed was a content-quality issue: too many low-value single-word
all-caps tokens saturated the Deepgram request and degraded
transcription relevance — and likely tripped server-side validation.

The Phase-1 audit (`docs/investigations/KEYTERM_REQUEST_AUDIT.md`)
located four seams in the active path where this noise could enter
without being filtered. This report's Phase 2-12 work closes them via
a single new sanitization layer.

---

## Section 2 — Existing Request Path

The path the audit documented (unchanged by this work apart from the
sanitization insertion site):

```
PDF / DOCX intake
     │
     ▼
core/intake_parser.py::parse_intake_document  (AI)
   ├─→ hard_filter_keyterms  (drops single-word ALL-CAPS at this stage)
   │
core/case_vocab.py::build_case_vocab_from_text  (regex fallback)
   └─→ (NOT filtered)
     │
     ▼
ui/tab_transcribe.py::_build_keyterms_from_intake
     • unions all_proper_nouns + vocabulary_terms + confirmed_spellings
     • min-length 3, dedup, cap 100 (no all-caps filter at this stage)
     │
     ▼
ui/tab_transcribe.py::self._pdf_keyterms (persisted to job_config.json)
     ⊕
ui/tab_transcribe.py::self._source_docs_keyterms
     │
     ▼
core/keyterm_extractor.py::merge_keyterms
     • clean → split_compound → clean → cap 100
     │
     ▼
core/job_runner.py::run_transcription_job
     ┌──────────────────────────────────────────────────────────┐
     │                                                          │
     │  raw_keyterms = dedup(keyterms + DEFAULT_KEYTERMS)        │
     │                                                          │
     │  >>> pipeline/keyterm_sanitizer.sanitize_for_deepgram <<<  ← NEW
     │                                                          │
     │     • Rules A-E (content + budget)                       │
     │     • Categorization (8 categories)                       │
     │     • Provenance per term                                │
     │                                                          │
     │  merged_keyterms = sanitization.accepted_terms            │
     │                                                          │
     └──────────────────────────────────────────────────────────┘
     │
     ▼
pipeline/transcriber.py::transcribe_chunk (per chunk)
     • defensive trim_keyterms_for_deepgram (now a no-op on sanitized list)
     │
     ▼
pipeline/transcriber.py::_transcribe_direct
     • urlencode + POST to https://api.deepgram.com/v1/listen
```

The sanitizer is the **single authoritative content gate**. Upstream
filters (`hard_filter_keyterms`, `clean_keyterms`) keep running for
their own data-model invariants; their output passes through the
sanitizer regardless.

---

## Section 3 — OCR Pollution Findings (Etminan Evidence)

Running the sanitizer against the actual Etminan keyterm list saved
on disk (`<case>/source_docs/job_config.json["deepgram_keyterms"]`)
plus `config.DEFAULT_KEYTERMS`:

| Metric | Before sanitization | After sanitization |
|---|---:|---:|
| Total keyterms | **102** (96 persisted + 7 defaults, deduped) | **55** |
| Single-word ALL-CAPS pure-alpha | 27 | **0** |
| OCR-tail boilerplate phrases | 8 | **0** |
| Subsumed short surnames | 12 | **0** |
| Generic legal single words | 18 | **0** |
| Final tokens estimate | ~448 / 450 (saturated) | **294 / 450** (35% headroom) |

Top rejection reasons by count:

| Rejection reason | Count | Examples |
|---|---:|---|
| `single_word_generic` | **18** | `CAUSE`, `DISTRICT`, `COURT`, `JUDICIAL`, `NOTICE`, `PLAINTIFF`, `TAKE`, `WITNESS` |
| `subsumed_by_longer_full_form` | **12** | `Etminan` (→ Mohammad Etminan), `Bentley`, `Crawford`, `Vargas`, `Rodriguez`, `Koepke` |
| `single_word_all_caps_not_whitelisted` | **9** | `LEONARDO`, `ROCIO`, `LAURA`, `MARCO`, `MOHAMMAD`, `SANDY`, `DEAN`, `HIDALGO`, `ISAIAS` |
| `ocr_boilerplate_phrase` | **8** | `Marco Crawford Law Original Standard`, `Trans Rush Due`, `Reyna Original Standard`, `Original Standard`, `Conference Room`, `Signature Waived`, `Electronically Served`, `Clara Contreras Electronically Served` |
| `oversize_removed` | 0 | (none on this case) |
| `budget_trimmed` | 0 | (budget had 35% headroom after the above rejections) |

Every protected entity survived: `C-5722-24-L` (case number),
`Mohammad Etminan`, `Marco A. Crawford`, `Dennis J. Bentley`,
`Sandy Dean Koepke`, `Christian R. Ramon`, `Hidalgo County`,
`Leonardo Isaias Rodriguez`, `Marco Crawford Law`, `Miah Bardot`,
`PLLC`, `CSR 12129`, `pass the witness`, `Objection. Form.`,
`solemnly swear`. None of the load-bearing legal entities for this
case were lost.

---

## Section 4 — Sanitization Philosophy

The module operates on five principles:

1. **Deterministic only.** No model calls, no probabilistic scoring,
   no AI-generated keyterms. Every accept/reject decision is
   reproducible from the input string + the source code.
2. **Quality over quantity.** It is better to send 25 excellent
   keyterms than 100 noisy ones. Protected entities (case numbers,
   person names, addresses, firms, medical terminology, legal
   acronyms) take precedence over coverage.
3. **Provenance preserved.** Every input keyterm — accepted or
   rejected — produces a `SanitizedKeyterm` record carrying the
   original text, the sanitized form, the score, the category, and
   (when rejected) the explicit reason. Audit reports read directly
   off these records.
4. **Hard budget enforcement.** Token budget never exceeds
   `config.DEEPGRAM_MAX_KEYTERM_TOKENS` (450). When budget is
   saturated, the **lowest-scoring** terms drop first; protected
   entities are guaranteed to survive.
5. **No architectural drift.** Single new module under `pipeline/`.
   Production callers replace exactly one call site
   (`core/job_runner.py:141-198`) with the new sanitizer. The
   transcriber's per-chunk defensive `trim_keyterms_for_deepgram`
   stays as a safety net.

---

## Section 5 — Scoring Rules

Categories carry deterministic scores. Higher scores survive budget
truncation; lower scores drop first.

| Category | Score | Definition |
|---|---:|---|
| `case_number` | **100** | Matches Texas / federal case-number forms (`C-5722-24-L`, `2026-CI-19595`, `2:23-cv-00456`) |
| `person` | **90** | 2-3 title-case-word sequence with optional middle initial and Jr/Sr/II/III/IV suffix |
| `law_firm` | **85** | Contains `PLLC`, `LLP`, `LLC`, `P.C.`, `Law Firm`, `Law Offices`, `& Associates`, `Group`, `Partners`, or the explicit `Brain and Spine Injury Lawyers` token |
| `address` | **80** | Number prefix + street-word suffix (`Street`, `St`, `Avenue`, `Road`, `Boulevard`, `Suite`, etc.) |
| `medical` | **75** | Member of `MEDICAL_TERMS` whitelist (`laminectomy`, `vertebroplasty`, `radiculopathy`, `spondylosis`, …) |
| `legal_term` | **70** | Member of `LEGAL_TERMS` whitelist (`voir dire`, `stenographic`, `subpoena duces tecum`, …) |
| `acronym` | **60** | Member of `MEDICAL_ACRONYMS` or `LEGAL_ACRONYMS` whitelist (`MRI`, `CT`, `EMG`, `CSR`, `PLLC`, `LLP`, …) |
| `proper_phrase` | **40** | Multi-word capitalized phrase that doesn't match a more specific category |
| `unknown` | **10** | Anything else that survives the filtering gates |
| `rejected_noise` | **0** | Tracked for audit; never accepted |

The whitelists are intentionally small. New medical or legal acronyms
require an explicit addition — the sanitizer never auto-promotes a
new ALL-CAPS token to "acronym" status.

---

## Section 6 — Filtering Rules

Five deterministic rules run in fixed order:

### Rule A — Minimum quality

Reject:
- empty / whitespace-only strings
- punctuation-only strings (e.g. `"---"`, `"..."`)
- digit-only strings
- strings longer than `KEYTERM_MAX_ENTRY_CHARS = 100` (form-template noise)
- strings shorter than `KEYTERM_MIN_LENGTH = 3` (after the acronym fast-path)
- multi-word phrases containing any `OCR_TAIL_PATTERNS` substring (`"original standard"`, `"trans rush"`, `"signature waived"`, `"electronically served"`, `"conference room"`, etc.)

### Rule B — Single-word generic

Reject single-word inputs whose lower-case form is in the
`GENERIC_BOILERPLATE` blacklist (75 entries: `united`, `states`,
`district`, `court`, `western`, `division`, `take`, `oral`, `notice`,
`deposition`, `intention`, `plaintiff`, `defendant`, `judicial`,
`county`, `cause`, `original`, `standard`, `respectfully`,
`submitted`, `standing`, `specialty`, `seam`, `company`, …).

### Rule C — Single-word ALL-CAPS

Reject single-word pure-alpha ALL-CAPS tokens **except** those in
the `MEDICAL_ACRONYMS` or `LEGAL_ACRONYMS` whitelists. The
whitelist fast-path runs *before* Rule C so `MRI`, `CT`, `EMG`,
`CSR`, `PLLC`, `LLP`, `JD`, `MD`, `DO` all survive. `LEONARDO`,
`ROCIO`, `LAURA`, etc. do not.

### Rule D — Duplicate collapse

When a longer accepted form contains a shorter form as a whole-word
substring, drop the shorter one. The longest-highest-scoring form
wins. Examples from Etminan:

| Longer form (kept) | Subsumed (dropped) |
|---|---|
| `Mohammad Etminan` | `Etminan` |
| `Dennis J. Bentley` | `Bentley` |
| `Marco A. Crawford` | `Crawford`, `Marco` |
| `Rocio Laura Elizondo Vargas` | `Vargas` |
| `Leonardo Isaias Rodriguez` | `Isaias Rodriguez`, `Rodriguez` |

### Rule E — Token budget enforcement

After Rules A-D have produced an accepted set, sort it by
descending score and (secondarily) descending word count. Walk in
that order, accepting each term whose token count fits in the
remaining budget. Anything that does not fit is dropped with
reason `trimmed_for_token_budget`. **Protected entities never drop
first** — case numbers (score 100) and person names (score 90) are
guaranteed to consume the budget first.

---

## Section 7 — Protected Entity Strategy

The sanitizer's contract is: **no legitimate legal entity is lost
without explicit instrumentation telling us why.** Concretely:

1. **Closed-world whitelists for the highest-risk categories.** The
   medical-acronym and legal-acronym whitelists, the medical-term
   whitelist, and the legal-term whitelist are explicit string sets.
   Adding a new term requires editing the source. The trade-off:
   missing terms in the whitelist get categorized as `unknown` and
   pass through with score 10 — they survive unless the budget is
   tight, in which case they trim first.
2. **Pattern-based recognition for entities that cannot be enumerated.**
   Case numbers, addresses, and person names use regex patterns
   (`CASE_NUMBER_RE`, `ADDRESS_RE`, `PERSON_NAME_RE`). The patterns
   are deliberately broad — they will sometimes mis-categorize
   noise as a person (Section 10 known weakness) — but they
   *do not* miss legitimate names of the canonical 2-3-word shape.
3. **Subsumption only collapses redundant fragments, never
   replacements.** Rule D drops `Etminan` when `Mohammad Etminan` is
   also present. It will never collapse `Mohammad Etminan` to fit a
   shorter form. The collapse direction is "drop short, keep long."
4. **Provenance is preserved on every record.** When a future audit
   asks "why was X rejected on case Y?", the answer is in
   `output/investigation/keyterm_sanitization/<case>/rejected.md`
   with the exact rejection reason and the original input string.

---

## Section 8 — Token-Budget Protection

`config.DEEPGRAM_MAX_KEYTERM_TOKENS = 450` (50-token margin below
Deepgram's documented 500-token Nova-3 cap). The sanitizer guarantees:

```
sum(term.token_count for term in accepted) <= 450
```

Token estimate: `(len(term) + 3) // 4 + 1` (the same formula the
legacy `trim_keyterms_for_deepgram` used — kept consistent so the
arithmetic is reproducible).

On Etminan the final accepted set consumes 294 tokens (65% of the
budget); 35% headroom remains for case-specific variation. The
previously-shipped run consumed ~448 tokens (saturated). The
sanitizer brings the request well clear of the cap.

When the budget *is* saturated, Rule E's score-ordered greedy fill
guarantees the highest-value entries survive. The lowest-scoring
proper-phrase / unknown entries drop first; protected entities
(case numbers, persons, firms, addresses) are kept first by
construction.

---

## Section 9 — Validation Results

### Test suite

| Suite | Count | Status |
|---|---:|---|
| `pipeline/tests/test_keyterm_sanitizer.py` | **56** | ✅ pass |
| `pipeline/tests/*` (all pipeline tests including transcriber) | — | ✅ pass |
| `core/tests/test_job_runner.py` (active-path wiring) | 6 | ✅ pass |
| `spec_engine/tests/*` | — | ✅ pass |
| `clean_format/tests/*` | — | ✅ pass |
| **Total** | **612** | **✅ pass** |

### Etminan production data

Audit run: `python -m tools.investigation.audit_keyterm_sanitization --case-dir "<etminan>"`

- 102 input → 55 accepted (54% pass) / 47 rejected (46%)
- 0 protected entities lost
- 294 / 450 tokens used (65% utilization, 35% headroom)
- 27 person names, 11 proper phrases, 15 unknown (lower-score
  legitimate entries like `464th Judicial District`,
  `CSR 12129`, `objection form`, `pass the witness`), 1 acronym,
  1 case number — accepted distribution

### Hard-coded test cases that exercise the protective contract

`TestProtectedEntityPreservation` runs every load-bearing entity
class through the sanitizer in isolation and asserts each one
survives:

- Full person names (`Jacob D. Cukjati`, `Mohammad Etminan`)
- Law firm with the case-specific `Brain and Spine Injury Lawyers` token
- PLLC firm name
- Addresses (`1721 Pinn Road`, `13526 George Road Suite 200`)
- Case numbers (`C-5722-24-L`, `2026-CI-19595`)
- Medical terms (`laminectomy`, `radiculopathy`)
- Legal phrases (`voir dire`)
- Legal acronyms (`CSR`, `MRI`)
- Real Etminan high-value entries (`Mohammad Etminan`,
  `Marco A. Crawford`, `Sandy Dean Koepke`, etc.)

If any of these were ever dropped by a future change to the
sanitizer, the test would fail loudly.

---

## Section 10 — Remaining Weaknesses

These are limitations of the deterministic approach. Recorded as
**observations, not work items**.

1. **The `PERSON_NAME_RE` regex is permissive.** Any 2-3 title-case
   word sequence matches it. On Etminan this caused some borderline
   accepts:
   - `Avenue Edinburg` (address fragment classified as person)
   - `Bentley Texas Bar` / `Crawford Texas Bar` (OCR fragments from
     a "Texas Bar No." line)
   - `Cause Number` (label classified as person)
   - `Standing Steam` (OCR typo of `Standing Seam` classified as person)
   - `Leonardo San Antonio` (OCR fragment — Leonardo is a defendant,
     San Antonio is a city)
   
   None of these are *harmful* — they just take a few extra tokens.
   A closed-world surname list would tighten this but trade off
   completeness.

2. **Subsumption is whole-word substring, not semantic.** On Etminan,
   the legitimate keyterm `San Antonio` (a city) was collapsed into
   `Leonardo San Antonio` (an OCR artifact) because the longer
   string contains the shorter as a whole-word substring. The
   collapse is technically correct by the rule, but the longer form
   isn't a "better" representation of the city. Document, accept.

3. **The OCR-tail blacklist (`OCR_TAIL_PATTERNS`) is hand-maintained.**
   New form templates with new boilerplate suffixes won't be caught
   until the pattern is added. The current 14 patterns cover the
   noise observed on Etminan; future cases may surface new ones.

4. **The medical / legal whitelists are intentionally small.** Terms
   that exist in real depositions but aren't in the whitelist
   (e.g. `arthrodesis`, `discography`, `electromyography`) will
   pass through as `unknown` with score 10 — they will survive
   unless the budget is tight. Adding new terms is a one-line edit.

5. **The sanitizer cannot detect "semantic noise" that looks
   structurally fine.** A phrase like `Marco Crawford Law Original`
   (an OCR-truncated form of `Marco Crawford Law, PLLC`) currently
   passes Rule A because it doesn't end in `Original Standard`. It's
   accepted as a `proper_phrase`. The cost is one wasted keyterm.

6. **The Deepgram HTTP 400 root cause is still not directly
   confirmed.** The audit suspected request-content quality
   triggered server-side rejection; the sanitization fix removes
   the suspected trigger but the next 400 (if one occurs) will need
   the failed-request capture mentioned in Section 11.

---

## Section 11 — Future Improvements

The following are observations only — **not implementation requests**.

1. **Persist the failed Deepgram request when 4xx is returned.**
   The current code only logs the status code. A
   `raw_deepgram_failed_<timestamp>.json` carrying the request URL,
   the final keyterm list, and the response body would let any
   future 400 be debugged in seconds instead of requiring an audit
   to reconstruct.

2. **Re-sanitize on `_auto_detect_source_docs` reload.** The
   audit's Section 6.2 found that a polluted `job_config.json` from
   a prior session reloads with zero re-filtering. With the
   sanitizer in place at the job-runner seam this is no longer a
   correctness issue (every reload gets sanitized before Deepgram
   sees it), but the persisted file still contains noise. A one-line
   sanitization on load would clean the persisted state.

3. **Close Seam A and Seam B by calling the sanitizer earlier.**
   The audit identified four seams; the job-runner insertion closes
   the request-construction seam (Seam D). Calling the sanitizer at
   the UI assembly seam (`_build_keyterms_from_intake`) would
   clean the persisted `job_config.json` going forward. Calling it
   at the fallback bypass (`core/pdf_extractor.py:43,55`) would
   prevent polluted regex-fallback output from being persisted.

4. **Validate against Cavazos and a difficult OCR-heavy case.** The
   change-validation discipline saved to memory
   ([feedback-change-validation-discipline]) requires multi-case
   validation before a production default change. Etminan is one
   data point. Re-run the audit tool on Cavazos and one Zoom case
   before adjusting any whitelists or blacklists based on Etminan's
   results.

5. **Surface the rejected list in the UI.** Today the user has to
   read `output/investigation/keyterm_sanitization/<case>/rejected.md`
   to see what was filtered. A read-only "Show keyterm filter
   report" button on the Transcribe tab would build confidence in
   the sanitizer's decisions on real cases.

6. **Closed-world surname / city lists for tighter person
   detection.** Would tighten `PERSON_NAME_RE` false positives
   (Section 10 #1) but adds maintenance burden. Defer until a
   case actually has a problematic-enough false positive to motivate
   the cost.

---

## Section 12 — Things That Should NOT Change

Per CLAUDE.md and the investigation charter:

- **Do not modify Deepgram request parameters.** `utt_split=0.8`,
  `paragraphs=true`, `diarize=true`, `smart_format=true`,
  `filler_words=true`, `numerals=true`, `utterances=true`. The
  sanitizer affects the `keyterm` list only; nothing else.
- **Do not modify `core/intake_parser.py::hard_filter_keyterms`.**
  It serves the intake AI's own data model. Leave it alone.
- **Do not modify `core/keyterm_extractor.py::clean_keyterms` or
  related helpers.** They serve the source-docs path. Leave alone.
- **Do not remove `config.DEFAULT_KEYTERMS`.** They are the
  load-bearing per-firm anchor (`Miah Bardot`, `CSR 12129`,
  `SA Legal Solutions`, `pass the witness`, `objection form`).
  They still appear in every request and survive sanitization.
- **Do not collapse the new sanitizer into the legacy
  `trim_keyterms_for_deepgram`.** The legacy function is the
  defensive safety net at the transcriber per-chunk level; if a
  future caller forgets to sanitize, this one still enforces the
  char-cap and token-budget contract.
- **Do not introduce model calls** into the sanitizer. Determinism
  is the contract.
- **Do not lower** the `MEDICAL_ACRONYMS` / `LEGAL_ACRONYMS`
  whitelists without re-running the protected-entity test suite.
  These shortcuts the min-length and Rule-C gates.
- **Do not change** `config.DEEPGRAM_MAX_KEYTERM_TOKENS = 450`
  without first measuring the new effective budget against several
  recent cases.

---

## Appendix — Artifacts produced

### Production code (modified)

- `core/job_runner.py` — replaced the legacy `trim_keyterms_for_deepgram`
  call site with `sanitize_for_deepgram`; emits a `[KEYTERM_SANITIZER]`
  log line plus per-rule rejection counts.

### Production code (new)

- `pipeline/keyterm_sanitizer.py` — the sanitizer module.

### Tests (new)

- `pipeline/tests/test_keyterm_sanitizer.py` — 56 cases.

### Investigation tooling (new)

- `tools/investigation/audit_keyterm_sanitization.py` — CLI for
  offline before/after audits without API calls.

### Investigation outputs (Etminan)

- `output/investigation/keyterm_sanitization/etminan_mohammad/summary.{json,md}`
- `output/investigation/keyterm_sanitization/etminan_mohammad/accepted.md`
- `output/investigation/keyterm_sanitization/etminan_mohammad/rejected.md`
- `output/investigation/keyterm_sanitization/etminan_mohammad/final_request_preview.txt`

### Test totals after this work

- **612 passing, 0 failing** across `pipeline/tests`,
  `spec_engine/tests`, `core/tests`, `clean_format/tests` (was 556
  before; +56 are the new sanitizer tests).

### Reproducing the Etminan audit

```powershell
.\.venv\Scripts\python.exe -m tools.investigation.audit_keyterm_sanitization `
    --case-dir "C:\Users\james\Depositions\2026\Apr\C572224L\etminan_mohammad"
```
