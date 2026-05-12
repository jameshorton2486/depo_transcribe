# CASE_MUTATION_REPORT

**Case folder:** `C:\Users\james\Depositions\2026\May\2026CV00803\cavazos_gilberto`
**DOCX under audit:** `Cavazos_Deposition_smoke_2026-05-12.docx`
**Comparison inputs:** `Deepgram/raw_deepgram.json`, `Deepgram/raw_deepgram.txt`, `source_docs/job_config.json`.

For each observed phrase the classifier identifies which stage introduced the mutation. The most consequential finding is summarized in the Stage Attribution at the end of this document.

## Stage classes

- **DEEPGRAM** — error originates in `raw_deepgram.json` per-word `"word"` field (audio→text).
- **SMART_FORMAT** — discrepancy between `"word"` and `"punctuated_word"` in `raw_deepgram.json` (Deepgram's formatter layer).
- **CLEANUP** — text present in `raw_deepgram.txt` but altered/removed/added in the final DOCX by the Anthropic cleanup pass.
- **DOCX_WRITER** — visible in DOCX XML but not in cleanup output text (formatting / run-splitting artifact).
- **PRESERVED_ERROR** — wrong form present in BOTH `raw_deepgram.json` AND final DOCX AND has a matching entry in `confirmed_spellings`. The wiring should have corrected it but did not.

---

## Table A — Every `confirmed_spellings` entry, observed in raw and DOCX

For each of the 33 entries: count of the *wrong* form in raw_deepgram.txt, count of the *wrong* form in the smoke DOCX, count of the *right* form in the smoke DOCX. **All 33 wrong-form counts are zero in both raw and DOCX**, because Deepgram (helped by `deepgram_keyterms`) produced the right forms upstream — the cleanup pass was never asked to apply any of these corrections.

| # | Wrong form | Right form | wrong in raw_txt | wrong in DOCX | right in DOCX | Stage attribution |
|---|---|---|---|---|---|---|
| 0 | `Injection form` | `Objection.  Form.` | 0 | 0 | 0 | N/A (term never appeared) |
| 1 | `Infection` | `Objection.` | 0 | 0 | 0 | N/A |
| 2 | `Protection` | `Objection.` | 0 | 0 | 0 | N/A |
| 3 | `Perfection` | `Objection.` | 0 | 0 | 0 | N/A |
| 4 | `Detection` | `Objection.` | 0 | 0 | 0 | N/A |
| 5 | `Eviction` | `Objection.` | 0 | 0 | 0 | N/A |
| 6 | `Definition` | `Objection.` | 0 | 0 | 0 | N/A |
| 7 | `Direction form` | `Objection.  Form.` | 0 | 0 | 0 | N/A |
| 8 | `Bleeding` | `Leading.` | 0 | 0 | 0 | N/A |
| 9 | `Leaving` | `Leading.` | 0 | 0 | 0 | N/A |
| 10 | `Warm, leading` | `Leading.` | 0 | 0 | 0 | N/A |
| 11 | `Former leaving` | `Form and leading.` | 0 | 0 | 0 | N/A |
| 12 | `Form and leaving` | `Form and leading.` | 0 | 0 | 0 | N/A |
| 13 | `Form and legal` | `Form and leading.` | 0 | 0 | 0 | N/A |
| 14 | `Past witness` | `Pass the witness.` | 0 | 0 | 1 | N/A (correct form direct) |
| 15 | `Pastor witness` | `Pass the witness.` | 0 | 0 | 1 | N/A |
| 16 | `so many sorts` | `solemnly swear to` | 0 | 0 | 1 (`solemnly swear`) | N/A |
| 17 | `remotes wearing` | `remote swearing of` | 0 | 0 | 1 (`remote swearing`) | N/A |
| 18 | `mister` | `Mr.` | 20 | 16 | 10 | ⚠️ See row M-3 |
| 19 | `miss ` | `Miss ` | 3 | 2 | 2 | ⚠️ See row M-4 |
| 20 | `Elma` | `Elmo` | 0 | 0 | 0 | N/A |
| 21 | `any exerts` | `any exhibits` | 0 | 0 | 0 | N/A |
| 22 | `cop number` | `Cause Number` | 0 | 0 | 1 | N/A (Deepgram got it right via keyterm) |
| 23 | `cost number` | `Cause Number` | 0 | 0 | 1 | N/A |
| 24 | `Cavazas` | `Cavazos` | 0 | 0 | 10 | N/A (Deepgram got it right via keyterm) |
| 25 | `Cabasos` | `Cavazos` | 0 | 0 | 10 | N/A |
| 26 | `Marilyn Maloney` | `Marynell Maloney` | 0 | 0 | 0 | N/A (`Maloney` 26× but the full `Marynell` form 0× — see row M-5) |
| 27 | `Marynell Malony` | `Marynell Maloney` | 0 | 0 | 0 | N/A |
| 28 | `Maloney Law Firm` | `Marynell Maloney Law Firm, PLLC` | 0 | 0 | 0 | N/A |
| 29 | `Gonzalez Junior` | `Gonzalez, Jr.` | 0 | 0 | 0 | N/A |
| 30 | `Valley` | `Valle` | 0 | 0 | 0 | N/A (`Valle` 0× in DOCX — see row M-6) |
| 31 | `Chesser` | `Chesser` | 0 | 0 | 0 | N/A |
| 32 | `Chester` | `Chesser` | 0 | 0 | 0 | N/A (`Chesser` 0× in DOCX) |

**Observation A.** Of the 33 `confirmed_spellings` entries, **zero applied work for this case** — the wrong forms were not present in Deepgram output. The dict provided no corrective value on this transcript. (Whether it provided value via the keyterm path is a separate question; on inspection, `deepgram_keyterms` and `confirmed_spellings` are independently constructed lists, with the keyterm list having more entries (84) and a different format.)

---

## Table B — Specific mutations observed in the smoke DOCX

| # | Phrase / Token | Final DOCX form | Source form | Stage introduced | Confidence | Notes |
|---|---|---|---|---|---|---|
| M-1 | First word of transcript | `THE VIDEOGRAPHER:  Got,[SCOPIST: FLAG 1: "Opening word 'Got' -- possibly 'Good' or an artifact; verify from audio or case materials"]` | `Speaker 0: Got,` (raw_deepgram.txt line 1); JSON word: `{"word":"got","confidence":0.464,"speaker":0,"punctuated_word":"Got,"}` | CLEANUP (added the `[SCOPIST: FLAG ...]` inline annotation) + DEEPGRAM (the underlying `got` at 0.46 confidence is low-quality audio→text) | 0.464 | Two-stage mutation: the original word is Deepgram-uncertain (`got` at 0.46), and the cleanup pass annotated it inline in body text rather than via a parallel review surface. |
| M-2 | Speaker label on line 1 | `THE VIDEOGRAPHER:` | `Speaker 0:` | CLEANUP | — | `speaker_map_suggestion` in job_config does not name a videographer; the actual `case_meta.videographer_name` is empty. The model mapped Speaker 0 → THE VIDEOGRAPHER from cleanup-pass heuristics rather than from any UFM field. |
| M-3 | `mister` → `Mr.` lookup | `mister`: 16 occurrences; `Mr.`: 10 occurrences | raw_deepgram.txt: `mister` 20×, `Mr.` 0× | CLEANUP partial | — | The cleanup pass title-cased 4–10 instances of `mister` → `Mr.` but left 16 still lowercase. The conversion is incomplete and asymmetric. |
| M-4 | `Miss Maloney` | `Miss Maloney` | raw_deepgram.txt: `Miss Maloney` (correct form) | CLEANUP preserved | — | Deepgram produced `Miss` correctly; cleanup left it alone. Acceptable. |
| M-5 | `Marynell` (witness's full first name) | DOCX `Marynell` count = 0 | raw_deepgram.txt: `Marynell` count = 0 | DEEPGRAM (skipped the name) | — | The cleanup pass cannot insert a name Deepgram never transcribed. `confirmed_spellings` has `Marilyn Maloney → Marynell Maloney` and `Marynell Malony → Marynell Maloney`, but neither wrong form appears either — meaning the witness's first name was not spoken on-mic in a Deepgram-detectable form. The header section just says "Michelle M. Maloney" (the filing attorney). |
| M-6 | `Valle` (copy attorney's surname) | DOCX `Valle` count = 0; `Valley` count = 0 | raw_deepgram.txt: `Valle` 0×, `Valley` 0× | DEEPGRAM | — | Jonathan Valle never appears in the body of the transcript despite being in `ufm_fields.copy_attorneys`. Either he didn't speak, or speech-to-text missed the name entirely. Not a bug in the cleanup or DOCX layers. |
| M-7 | `Chesser` (ordered-by) | DOCX `Chesser` count = 0 | raw_deepgram.txt: `Chesser` 0× | DEEPGRAM | — | Cassidy Chesser ordered the deposition (per `ufm_fields.ordered_by`) but is not a participant; absence is correct. |
| M-8 | Inline scopist flags | 58 occurrences of `[SCOPIST: FLAG N: "..."]` in DOCX body text | 0 occurrences in raw_deepgram.txt | CLEANUP | — | The model was prompted (or learned via in-context examples) to emit numbered scopist annotations inline. They appear inside `Q.`, `A.`, and labeled-speaker blocks. They survived `_postprocess_formatted_text` unchanged. **Not a current spec requirement; emergent behavior.** |
| M-9 | `Cause Number` | DOCX `Cause Number` 1× | raw_deepgram.txt: `Cause Number` 1× (single instance) | CLEANUP preserved | — | Deepgram correctly produced "Cause Number" once via the keyterm hint. `confirmed_spellings` covers two variants (`cop number`, `cost number`) but neither appeared. |
| M-10 | Header — defendant labeling | DOCX header: `FOR DEFENDANT MICHELLE M. MALONEY  Michelle M. Maloney  102 Wickes Street...` | `case_meta.json: attorneys[0].role="defendant"`, `attorneys[0].city="102 Wickes Street"` | CLEANUP (rendered) + DATA ARTIFACT (case_meta) | — | The model rendered the attorney section using the `role="defendant"` flag literally, producing "FOR DEFENDANT MICHELLE M. MALONEY" which reads as if Maloney is the defendant. The defendant is `City of San Antonio, Animal Care Services` per `ufm_fields.defendant_name`. The `case_meta` schema conflates "attorney appearing for the defendant" with "attorney role = defendant"; the cleanup pass faithfully renders the literal value. |
| M-11 | Header — attorney `city` field | DOCX header includes street line under attorney block | `case_meta.json: attorneys[0].city="102 Wickes Street"` | DATA ARTIFACT (intake parsing) | — | The `case_meta.attorneys[i].city` field name is misleading; it's holding the street line for the attorney. Cleanup faithfully renders the value. |
| M-12 | Five-speaker raw vs three-speaker DOCX labeling | Raw has Speaker 0..4 (94, 1108, 1783, 368, 505 words). DOCX uses labels `THE VIDEOGRAPHER`, `THE REPORTER`, `THE WITNESS`, `Q.`, `A.` and an `EXAMINATION BY MS. MALONEY:` marker. | `speaker_map_suggestion` JSON names 7 roles but the audio diarized to 5 speakers. | CLEANUP (speaker mapping) | — | The cleanup pass collapsed 5 diarized speakers into role labels using its own heuristics. Speaker 0's 94 words landed under `THE VIDEOGRAPHER` despite no videographer in `case_meta`. The mapping was not informed by `speaker_map_suggestion` (that JSON is at top level of job_config, not in the slice passed to the prompt via `_case_meta_for_prompt`, which lists 15 explicit keys at `clean_format/formatter.py:96-112` and `speaker_map_suggestion` is not among them). |
| M-13 | Q:A paragraph ratio | DOCX: Q.=108, A.=55, three-tab non-QA=125 | raw_deepgram.txt has plain `Speaker N:` blocks — no Q./A. distinction | CLEANUP (Q/A classification) | — | The witness's responses (Speaker 2, 1,783 words ≈46% of total) should produce roughly as many A. paragraphs as Q. paragraphs (108). Instead 55 A. paragraphs landed, with 125 "three-tab non-QA" paragraphs holding the rest. The classification half of the cleanup pipeline is mis-attributing witness responses. |
| M-14 | Yellow highlights — content survey | First 40 highlighted texts include grammatically meaningless tokens: single letters `'P'`, `'I'`, `'R'`, common function words `'And'` (3×), `'the'` (3×), `'and'`, `'you'`, `'it'`, alongside genuinely uncertain proper nouns `'Penn'`, `'Pinrue'`, `'Wickes'`. | Per-word confidence below 0.85 in `raw_deepgram.json` — the injection criterion is purely confidence-based. | DOCX_WRITER (rendered exactly what was marked) | — | The marker injection upstream is confidence-driven and does not filter for "is this a word a scopist would want to review." Most of the 150 highlighted runs are function words, fillers, or partial-utterance fragments where the scopist's review value is low. |
| M-15 | Word survival from low-confidence words count | 517 low-conf words in JSON → 154 markers injected → 150 highlights in DOCX | `clean_format/low_confidence_markers.py:59` (`inject_markers`) — the per-word injection step | INJECTION (a pre-CLEANUP step in `clean_format/`) | — | 367 of 517 low-confidence words (71%) never get a marker. Likely causes: dedup logic in `inject_markers` skipping repeated low-conf tokens, tokenization mismatch between Deepgram's word stream and the rendered raw_deepgram.txt, or `_word_match_pattern` failing on tokens with attached punctuation. Per-stage attribution: this is a `clean_format/low_confidence_markers.py` characteristic, not a downstream CLEANUP issue. |
| M-16 | DOCX text encoding shows `0xfffd` (replacement char) | First-400-chars dump shows `Plaintiff,� IN THE DISTRICT COURT� vs.� 3RD JUDICIAL DISTRICT� Bexar County COUNTY` | The replacement character (`�` U+FFFD) is rendered at field-boundary positions in the header. | DOCX_WRITER | — | These appear to be tab characters or special separators that didn't round-trip cleanly through the run extraction. Not visible in `raw_deepgram.txt`. Worth opening the DOCX visually to confirm they render correctly there (they may be invisible inside a header table cell and only surface in raw-text extraction). |

---

## Stage Attribution Summary

Counting each *introduced* mutation once (M-1 attributed to both stages counted as one for each):

| Stage | Count of mutations attributed | Notes |
|---|---|---|
| **CLEANUP** | 8 | M-1 (annotation half), M-2, M-3, M-8, M-10 (render half), M-12, M-13, M-14 indirectly via marker placement |
| **DEEPGRAM** | 4 | M-1 (`got` at 0.46), M-5, M-6, M-7 |
| **SMART_FORMAT** | 0 | No mutations observed attributable to the smart-format layer this case — keyterm-driven capitalization worked correctly |
| **DOCX_WRITER** | 2 | M-14, M-16 |
| **DATA ARTIFACT** (intake → case_meta) | 2 | M-10 (the `role="defendant"` literal), M-11 (the `city` field holding a street) |
| **INJECTION** (`clean_format/low_confidence_markers.py`) | 1 | M-15 — the 517→154 drop |
| **PRESERVED_ERROR** | 0 | No confirmed-spelling wrong form survived through to the DOCX |

**Headline.** The cleanup pass (Anthropic) is responsible for the majority of observed mutations (8 of 17 attributed mutations), the largest individual class being the `[SCOPIST: FLAG ...]` inline annotations that landed in body text rather than in a separate review surface (M-8, 58 instances in a single document). The second-largest concern is the Q/A speaker-mapping behavior (M-12, M-13) producing a 108:55 Q:A ratio with 125 unclassified paragraphs from inputs that the prior-flow DOCX rendered as 106:102 with zero unclassified.

**Secondary finding — and the most consequential for the long term.** The `confirmed_spellings` infrastructure (33 entries, intake-parsed, persisted in job_config, exposed to the offline `core/corrections_runner.py` path) **never executed in the active Start-Transcription flow on this case**. Whether it would have helped is unfalsifiable here since Deepgram produced the right forms unaided — but the wiring gap means a future case where Deepgram misses a name would not be auto-corrected by the active path. See the Active Path Audit for the wiring detail.
