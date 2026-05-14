# Keyterm Request Audit — Phase 1

**Scope:** READ-ONLY. No production code changed during this audit.
**Trigger:** Production transcription failed with `Deepgram HTTP 400 Bad Request` during request construction (not transcription). The request carried noisy keyterms (single uppercase tokens, OCR fragments, duplicates).
**Goal:** Map every active-path location where keyterms are produced, mutated, merged, filtered, and injected into the Deepgram request, so a focused sanitization fix (Phase 2+) can target the right entry point without redesigning the pipeline.

---

## TL;DR

The Deepgram-keyterm contract on the active Start-Transcription path is:

```
Intake PDF/DOCX
   ├─ Primary:  core/intake_parser.py::parse_intake_document   (AI, structured JSON)
   │    └─ raw → core/intake_parser.py::hard_filter_keyterms
   │
   └─ Fallback: core/case_vocab.py::build_case_vocab_from_text (regex, no filter applied)
                                                                    │
                                                                    ▼
                                              (sometimes returned directly,
                                                bypassing hard_filter)
   │
   ▼
ui/tab_transcribe.py::_build_keyterms_from_intake
   • union of intake.all_proper_nouns
                ∪ intake.vocabulary_terms[].term
                ∪ intake.confirmed_spellings.values()
   • dedup, min-len 3, cap 100
   • no all-caps single-word filter at this point
   │
   ▼
ui/tab_transcribe.py::self._pdf_keyterms (persisted)
        ⊕  ui/tab_transcribe.py::self._source_docs_keyterms
   │
   ▼
core/keyterm_extractor.py::merge_keyterms(pdf_terms, reporter_terms)
   • clean_keyterms (filter+dedup+prioritize)
   • split_compound_terms (re-explodes addresses)
   • clean_keyterms (again)
   • cap MAX_KEYTERMS=100, fill from reporter
   │
   ▼
ui/tab_transcribe.py → core/job_runner.py::run_transcription_job(keyterms=...)
   │
   ▼
core/job_runner.py:143:  merged_keyterms = list(dict.fromkeys((keyterms or []) + DEFAULT_KEYTERMS))
   • appends config.DEFAULT_KEYTERMS (7 SA-Legal-Solutions standing keyterms)
   • simple dedup; no re-filter
   │
   ▼
pipeline/transcriber.py::trim_keyterms_for_deepgram (last line of defense)
   • per-entry char cap 100
   • token budget 450 (config.DEEPGRAM_MAX_KEYTERM_TOKENS)
   • drops oversize entries; trims to fit budget
   • NO content sanitization at this point — char cap and budget only
   │
   ▼
pipeline/transcriber.py::_transcribe_direct
   • params.setdefault("keyterm", []).extend(normalized_keyterms)
   • urlencode(params, doseq=True)
   • POST https://api.deepgram.com/v1/listen?...
```

**Hot-spot finding:** the active path has filters at the **head** (intake AI) and **tail** (transcriber token-budget), but the **middle** lets material slip through. Specifically, `ui/tab_transcribe.py::_build_keyterms_from_intake` (line 2314) re-unions `all_proper_nouns` with `vocabulary_terms[].term` and `confirmed_spellings.values()` but applies only a minimum-length-3 filter; the all-caps single-word rule from `hard_filter_keyterms` is not re-run. If the regex fallback path (`core/case_vocab.py`) is the source — or if AI returns `vocabulary_terms[].term` strings that aren't in `all_proper_nouns` — noisy items can reach `merge_keyterms` already accepted.

---

## Section 1 — All active-path keyterm files

| File | Role | Reads | Writes |
|---|---|---|---|
| `core/intake_parser.py` | AI structured intake parser | PDF/DOCX text | `IntakeParsedResult.all_proper_nouns`, `vocabulary_terms`, `confirmed_spellings` |
| `core/pdf_extractor.py` | AI-first wrapper with regex fallback | PDF text | `intake.all_proper_nouns` OR `case_vocab.build_case_vocab_from_text()["deepgram_keyterms"]` |
| `core/source_docs_extractor.py` | Multi-file text extractor (PDF/DOCX/TXT) | source_docs/ files | concatenated text → consumed by intake_parser |
| `core/case_vocab.py` | Regex-based fallback when AI fails | text | `{"deepgram_keyterms": [...]}` |
| `core/keyterm_extractor.py` | Cleaning + merging utilities | raw term lists | filtered/deduplicated/prioritized list |
| `ui/tab_transcribe.py` | UI orchestration; holds the final list | intake results, job_config | `self._pdf_keyterms`, `self._source_docs_keyterms`, passed into `run_transcription_job` |
| `core/job_runner.py` | Adds defaults + runs final trim | UI-supplied keyterms | `merged_keyterms` passed per chunk to `transcribe_chunk` |
| `pipeline/transcriber.py` | Last filter + request construction | per-chunk keyterms | `keyterm=...` URL params in the Deepgram POST |
| `config.py` | Constants only | (none at runtime beyond import) | `DEFAULT_KEYTERMS`, `DEEPGRAM_MAX_KEYTERM_TOKENS=450` |
| `core/config.py` | Constants only | (none at runtime beyond import) | `MAX_KEYTERMS=100`, `MIN_TERM_LENGTH=3` |

---

## Section 2 — Generation: where keyterms originate

### 2.1 Primary path: AI intake parser

**Site:** `core/intake_parser.py::parse_intake_document` (line ~700s).

The parser sends extracted PDF text to Claude and asks for a structured JSON response. Of interest:

- `all_proper_nouns: list[str]` — the master term list (line 244, 61).
- `vocabulary_terms: list[dict]` — `{term, term_type, field_name, reason}` for select entries (line 489-513).
- `confirmed_spellings: dict[str,str]` — wrong→right name corrections (line 463).

Post-AI, the parser calls `hard_filter_keyterms(raw)` on the AI's `all_proper_nouns` (line 794) before storing in the result. The filter:

| Drop rule | Source |
|---|---|
| length < 4 chars | `core/intake_parser.py:402` |
| single word starting lowercase AND no digit | `core/intake_parser.py:407` |
| in `NOISE_WORDS` lexicon (a 80-word legal-boilerplate blacklist) | `core/intake_parser.py:409` |
| all-digit | `core/intake_parser.py:411` |
| **single-word ALL-CAPS pure-alpha** | `core/intake_parser.py:413` |
| case-insensitive duplicate | `core/intake_parser.py:415` |
| cap at MAX_KEYTERMS=100 | `core/intake_parser.py:421` |

Crucially the all-caps single-word rule **only applies inside this filter**. Subsequent re-ingestion of AI fields (vocabulary_terms[].term, confirmed_spellings.values()) does not re-apply it.

### 2.2 Fallback path: regex case-vocab

**Site:** `core/case_vocab.py::build_case_vocab_from_text`, reached from `core/pdf_extractor.py:34-43,52-55` when the AI parse returns `None` or raises.

The regex fallback emits a `{"deepgram_keyterms": [...]}` dict. Critically:

> `return list(fallback["deepgram_keyterms"])` — `pdf_extractor.py:43, 55`

The fallback list is returned **directly to the UI** without passing through `hard_filter_keyterms`. The UI then writes this into `self._pdf_keyterms` and persists it to `job_config.json`.

**Implication:** If the AI ever fails, the fallback path bypasses the most aggressive sanitization in the codebase. The single-word all-caps rule, the NOISE_WORDS lexicon, and the 4-char minimum never run on fallback output unless `core/case_vocab.py` enforces equivalent rules internally. (Worth checking in Phase 2.)

### 2.3 Source-docs supplementary path

**Site:** `core/keyterm_extractor.py::extract_keyterms_from_text` invoked from the source-docs upload flow.

This path extracts proper-name phrases, firm-name patterns (PLLC/LLP/...), case-number patterns, and addresses via regex (`NAME_PATTERN`, `CASE_NUMBER_PATTERN`, `FIRM_PATTERN`, `ADDRESS_PATTERN` at lines 41-53). The output is sent through `clean_keyterms` which applies:

- `_strip_boundary_noise` (BOUNDARY_NOISE_WORDS — 70+ tokens)
- `_is_valid_term` (STOPWORDS, STRUCTURE_BLACKLIST, MIN_TERM_LENGTH)
- `_deduplicate`
- `_prioritize` (full names > legal caps > multi-word > rest)

**This is the most thorough sanitizer in the codebase**, but it runs only on the source-docs / reporter-notes path — not on the primary AI-intake path.

---

## Section 3 — Where the noise actually came from on Etminan

Reading `<case>/source_docs/job_config.json["deepgram_keyterms"]` directly:

- **Count:** 96 keyterms
- **Length distribution:** 44 single-word / 26 two-word / 16 three-word / 5 four-word / 4 five-word / 1 six-plus
- **Single-word uppercase entries:** `PLLC`, `C-5722-24-L`, **`CAUSE`, `ROCIO`, `LAURA`, `DISTRICT`, `COURT`, `JUDICIAL`, `LEONARDO`, `ISAIAS`, `SANDY`, `DEAN`, `STANDING`, `SEAM`, `SPECIALTY`, `COMPANY`, `HIDALGO`, `COUNTY`, `PLAINTIFF`, `NOTICE`**, and more.
- **OCR-fragment phrases:** `Marco Crawford Law Original Standard`, `Trans Rush Due`, `Reyna Original Standard`, `Original Standard`.

The single-word ALL-CAPS legal headers (`CAUSE`, `DISTRICT`, `COURT`, etc.) are exactly the class that `hard_filter_keyterms` line 413 was written to drop. Yet they survived. Three possible vectors:

1. **The vocabulary_terms / confirmed_spellings union in `_build_keyterms_from_intake`** (`ui/tab_transcribe.py:2314-2344`) re-introduces them. `confirmed_spellings.values()` could contain ALL-CAPS targets if the AI proposed `"cause" → "CAUSE"` as a correction; same for any case-style transformation. No re-filter runs here.
2. **The regex fallback** in `core/case_vocab.py` — if the AI returned `None` or raised, the fallback may have produced the ALL-CAPS tokens directly. Need to read that module to confirm.
3. **A prior intake run** persisted the list to `job_config.json` and a later run reloaded it via `_auto_detect_source_docs` (lines 2358-2386). Reload happens with **zero re-validation** of the persisted list.

The remaining "OCR fragment" phrases (`Marco Crawford Law Original Standard`, `Trans Rush Due`, `Reyna Original Standard`) look like the kind of multi-word concatenations that would survive `_is_valid_term` because they contain capitalized words — the filter has no semantic check for "is this a coherent entity name vs. a stitched-together OCR run". They presumably came from the AI's `all_proper_nouns` and bypassed hard_filter because they don't trip any of its individual rules (not all-caps single-word, length ≥ 4, not in NOISE_WORDS, not pure-digit).

---

## Section 4 — Mutation, expansion, deduplication

### 4.1 `_build_keyterms_from_intake` (UI) — `ui/tab_transcribe.py:2314`

- Inputs: three fields off the `IntakeParsedResult`.
- Filter: minimum length 3.
- Dedup: via `set`.
- Cap: `sorted(terms)[:100]`.
- **No content sanitization beyond min-length.**

### 4.2 `merge_keyterms` — `core/keyterm_extractor.py:463`

- Inputs: pdf_terms + reporter_terms.
- Pipeline: `clean_keyterms` → `split_compound_terms` → `clean_keyterms` again.
- Important: `split_compound_terms` (line 327) **explodes** comma/semicolon-joined entries into pieces. An address like `"123 Main St, Suite 200, San Antonio, TX 78230"` becomes `["123 Main St", "Suite 200", "San Antonio"]` — useful, but if the input contains stitched OCR runs like `"Marco Crawford Law Original Standard"`, the splitter leaves them intact because no comma is present.
- Cap: MAX_KEYTERMS=100 on primary, fill from reporter to reach 100.

### 4.3 `job_runner` merge with defaults — `core/job_runner.py:143`

```python
merged_keyterms = list(dict.fromkeys((keyterms or []) + DEFAULT_KEYTERMS))
```

- Appends `config.DEFAULT_KEYTERMS = ["Miah Bardot", "Bardot", "CSR 12129", "SA Legal Solutions", "San Antonio", "objection form", "pass the witness"]`.
- Dedups via `dict.fromkeys` (case-sensitive — `"Court"` and `"court"` both pass).
- **No content sanitization.** The total count can exceed 100 here; the next stage trims.

### 4.4 `trim_keyterms_for_deepgram` — `pipeline/transcriber.py:528`

- Per-entry char cap: 100 (drops any single keyterm > 100 chars).
- Token budget: 450 tokens (Nova-3's documented 500 minus 50 safety margin).
- Greedy fill: walks the list and adds until budget exhausted.
- **No content sanitization beyond size cap.** Garbage that fits the budget passes through.

---

## Section 5 — Validation and request construction

### 5.1 The actual HTTP request

`pipeline/transcriber.py::_transcribe_direct:583-604`:

```python
params = normalize_params({...flags...})
params = enforce_required_deepgram_flags(params)
params = validate_deepgram_params(params)
if normalized_keyterms:
    params.setdefault("keyterm", []).extend(normalized_keyterms)
query = _parse.urlencode(params, doseq=True)
url = f"https://api.deepgram.com/v1/listen?{query}"
```

- `validate_deepgram_params` (line 438) only rejects TitleCase boolean strings. It does **not** inspect keyterms.
- `urlencode(params, doseq=True)` emits one `keyterm=...` query-string entry per list item.
- The HTTP POST request URL becomes the concatenation of every keyterm. **There is no upper bound on URL length on our side**; Deepgram's HTTP 400 likely reflects a server-side limit on either:
  - request-URL length (typical limits: 8 KB on most reverse proxies; Deepgram is unclear),
  - per-keyterm token-cap (500-token combined budget is documented), or
  - keyterm character-set rules (Deepgram has not publicly documented permitted characters).

### 5.2 What we suspect tripped the 400

With 96 keyterms after `trim_keyterms_for_deepgram` reporting "~448/450 tokens used", we are saturating Deepgram's documented budget on the client side. The on-the-wire URL is:

```
https://api.deepgram.com/v1/listen?model=nova-3&language=en&...&keyterm=...&keyterm=...&keyterm=...  (×96)
```

With single-word entries like `CAUSE`, `ROCIO`, etc. each producing one `keyterm=...` parameter, the URL grew large. Deepgram returned 400 — but the **immediate cause is opaque** because the error message in our logs only said `400 Bad Request`. Server-side reasons that could trigger 400:

1. URL exceeded a proxy length limit.
2. A specific keyterm contained a character Deepgram's parser rejected (uncommon but possible — e.g. trailing punctuation, dash-only tokens).
3. Tokenizer drift: our `(len + 3) // 4 + 1` estimate was off and the request actually exceeded 500 tokens server-side.
4. Duplicate keyterm bytes (URL-encoded variants of the same string).

The audit cannot disambiguate these from the current code; the request URL is not currently persisted on disk. (Section 8 records this as the highest-value forward investigation.)

---

## Section 6 — Persistence and reload semantics

### 6.1 Where keyterms are saved

- `<case>/source_docs/job_config.json["deepgram_keyterms"]` is the canonical persisted list. Written by `core/job_config_manager.merge_and_save` from the UI (`tab_transcribe.py:3181`).
- `<case>/case_meta.json["deepgram_keyterms"]` is a snapshot written into the Anthropic-cleanup prompt's context (`tab_transcribe.py:3608`).
- `<case>/Deepgram/raw_deepgram.json["deepgram_keyterms_used"]` is the final list actually sent on this run (written by job_runner.py:366).

### 6.2 Reload risk

`_auto_detect_source_docs` (line 2358) loads the persisted `job_config.json` and assigns:

```python
self._pdf_keyterms = list(existing_config.get("deepgram_keyterms", []) or [])
```

**No re-filtering.** A bad list saved to disk in a prior session will be reused intact next session. This is the most likely path by which a single bad intake parse contaminates subsequent runs of the same case.

---

## Section 7 — Filter overlap and gaps

| Filter | Where | Drops single-word ALL-CAPS pure-alpha | Drops NOISE_WORDS | Length min | Dedup | Token budget |
|---|---|:---:|:---:|---:|:---:|:---:|
| `intake_parser.hard_filter_keyterms` | post-AI, intake | ✅ line 413 | ✅ line 409 (80 words) | 4 | ✅ | — |
| `_build_keyterms_from_intake` (UI) | UI assembly | ❌ | ❌ | 3 | ✅ | — |
| `keyterm_extractor.clean_keyterms` | source-docs path | partial via STOPWORDS | partial via STRUCTURE_BLACKLIST | `MIN_TERM_LENGTH=3` | ✅ | — |
| `job_runner` dict.fromkeys merge | active-path tail | ❌ | ❌ | — | ✅ | — |
| `trim_keyterms_for_deepgram` | last hop | ❌ | ❌ | — | partial | ✅ |

**The gap is the UI assembly stage.** `_build_keyterms_from_intake` is the **only point** that unions three AI fields, and it applies the weakest filter (length ≥ 3 + dedup). Single-word ALL-CAPS tokens entering from `vocabulary_terms[].term` or `confirmed_spellings.values()` survive this stage and pass through every subsequent stage unchallenged.

---

## Section 8 — Observations / candidate Phase-2 targets

Recorded as observations, not implementation directives.

1. **Re-apply `hard_filter_keyterms` at the assembly seam.** `_build_keyterms_from_intake` would benefit from passing its union through `core.intake_parser.hard_filter_keyterms` before returning. That single line would catch every single-word ALL-CAPS token regardless of which AI field it came from.
2. **Fallback path bypasses the filter entirely.** `core/pdf_extractor.py:43` and `:55` return `case_vocab` results unfiltered. A one-line wrap with `hard_filter_keyterms` here would close the second seam.
3. **Persistence reload doesn't re-validate.** `_auto_detect_source_docs` should ideally re-run the filter on the loaded list so a polluted job_config from a prior session is sanitized on reuse. (Not strictly necessary if seams 1 and 2 are closed.)
4. **Save the final request URL** (or just the final keyterm list and the response body) when Deepgram returns 4xx. The current code only logs the status code; without the actual list the user can't tell which keyterm tripped the parser. The recommendation is to dump `raw_deepgram_failed_<timestamp>.json` with `{request_keyterms, status_code, response_body}` alongside `raw_deepgram.json`.
5. **The "OCR fragment" phrases** (`Marco Crawford Law Original Standard`, `Trans Rush Due`, etc.) are a separate class of problem from the single-word ALL-CAPS noise. They look phrase-like and would pass every existing filter. Either:
   - The AI intake prompt needs to be hardened to reject form-template stitching, OR
   - A length-vs-entropy heuristic (high-entropy multi-token strings with no dictionary words flagged) might catch them — but that risks false positives on legitimate company names.

   Phase 2 should probably defer this class until the simpler noise is gone and we can measure whether it's still a meaningful share of the keyterms.
6. **DEFAULT_KEYTERMS is appended unconditionally.** `core/job_runner.py:143` adds 7 SA-Legal-Solutions standing keyterms to every run. On a case with 96 noisy keyterms already, those 7 add ~28 tokens. Not the culprit but worth knowing.

---

## Section 9 — Active-path keyterm flow diagram (canonical)

```
PDF/DOCX from <case>/source_docs/
       │
       ▼
core/source_docs_extractor.py::extract_text_from_files
       │ (concatenated text)
       ▼
core/pdf_extractor.py::_extract_keyterms_from_pdf_text
       │
       ├── (success) core/intake_parser.py::parse_intake_document   ── AI
       │       │                                                     │
       │       └── intake.all_proper_nouns ← hard_filter_keyterms ←──┘
       │
       └── (failure) core/case_vocab.py::build_case_vocab_from_text  ── regex
                       │
                       └── deepgram_keyterms (NOT re-filtered)        ◀── SEAM A
       │
       ▼
ui/tab_transcribe.py::_build_keyterms_from_intake
       │
       │  unions:  all_proper_nouns ∪ vocabulary_terms[].term ∪ confirmed_spellings.values()
       │  filters: min-length=3, dedup, cap=100
       │  (does NOT re-run hard_filter)                              ◀── SEAM B
       │
       ▼
ui/tab_transcribe.py::self._pdf_keyterms
       │     ⊕  self._source_docs_keyterms
       │
       ▼
core/keyterm_extractor.py::merge_keyterms
       │  (clean → split_compound → clean → cap 100)
       │
       ▼
core/job_runner.py::run_transcription_job(keyterms=...)
       │
       │  merged_keyterms = list(dict.fromkeys(keyterms + DEFAULT_KEYTERMS))
       │  (no re-filter, just dedup)                                 ◀── SEAM C
       │
       ▼
pipeline/transcriber.py::trim_keyterms_for_deepgram
       │  (char-cap + token-budget; no content rules)                ◀── SEAM D
       │
       ▼
pipeline/transcriber.py::_transcribe_direct
       │  params["keyterm"].extend(normalized_keyterms)
       │  urlencode + POST
       │
       ▼
https://api.deepgram.com/v1/listen?…&keyterm=…&keyterm=…&keyterm=… (×N)
```

**Seams (in order of expected Phase-2 value):**

- **Seam B** — UI assembly. Highest leverage; lowest risk. Re-apply `hard_filter_keyterms` here and every single-word ALL-CAPS token disappears regardless of upstream origin.
- **Seam A** — fallback bypass. Wrap the fallback return in `hard_filter_keyterms` to close the regex path's hole.
- **Seam C** — final merge. Optional; if A and B are closed, this becomes redundant.
- **Seam D** — content rules at the request-construction layer. Probably overkill if A and B are closed, but a final defensive pass is cheap.

---

## Audit footnotes

- **Verified at:** 2026-05-13.
- **Working tree state:** clean (`git status` shows no production-code modifications from this audit).
- **Evidence sources cited:**
  - `core/intake_parser.py:262-343,392-426,543-575,789-855`
  - `core/keyterm_extractor.py:24-176,257-405,463-522`
  - `core/pdf_extractor.py:21-55`
  - `core/source_docs_extractor.py:28-60`
  - `ui/tab_transcribe.py:2314-2345,3155-3185,3428-3489`
  - `core/job_runner.py:141-166`
  - `pipeline/transcriber.py:525-581,583-612`
  - `config.py:35-70`
  - `core/config.py:28-32`
  - Etminan `source_docs/job_config.json["deepgram_keyterms"]` (96 entries).
- **Not investigated in this audit (recorded as forward work):** the internal behavior of `core/case_vocab.py::build_case_vocab_from_text` (Seam A's upstream side), and whether it independently enforces the single-word-ALL-CAPS rule. If it does, Seam A may already be safer than it looks; if it doesn't, Seam A is a real hole.
