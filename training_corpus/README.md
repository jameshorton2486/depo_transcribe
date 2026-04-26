# Training Corpus

Local-only collection of real deposition outputs used as evidence for
pipeline rule promotion. **Real depositions contain PII** — case folders
are gitignored and never get committed. Only this README and the
`.gitkeep` are tracked, so the directory exists in the repo while
client data stays local.

If you cloned this repo on a new machine, the corpus is empty by
design. Populate it from your local depositions; nothing here syncs
across machines.

## Directory layout

```
training_corpus/
├── README.md                                      (tracked)
├── .gitkeep                                       (tracked)
├── {case_slug}/                                   (gitignored)
│   ├── case_id.txt                                — single line: cause number
│   ├── pipeline_output_pass1_{YYYY-MM-DD}.txt     — deterministic output
│   ├── pipeline_output_pass2_{YYYY-MM-DD}.txt     — after AI Correct (optional)
│   ├── ground_truth.txt                           — version you'd certify
│   ├── job_config.json                            — copy of the case's job config
│   └── notes.md                                   — context, certification, date trail
└── _diffs/                                        (gitignored, auto-generated)
    ├── {case_slug}.text.diff.md                   — homophones, proper nouns, words
    └── {case_slug}.speakers.diff.md               — speaker-label re-attributions
```

`{case_slug}` convention: `lastname_YYYY_MM_DD`, lowercase. Match the
**deposition** date, not the date you processed it. Example:
`singh_2026_04_23`.

## Files per case

Required + optional. **Don't add anything else** outside this layout —
the tooling assumes it.

| File | Required | Source |
|---|---|---|
| `case_id.txt` | yes | one line, the cause number, no header |
| `pipeline_output_pass1_{YYYY-MM-DD}.txt` | yes | copy of the `_corrected.txt` your pipeline produced |
| `pipeline_output_pass2_{YYYY-MM-DD}.txt` | when AI Correct has run | copy of the `_ai_corrected.txt` |
| `ground_truth.txt` | yes | hand-corrected version you'd certify and deliver |
| `job_config.json` | yes | full copy of `{case}/source_docs/job_config.json` |
| `notes.md` | strongly recommended | who certified, what was hard, anything weird |

The `{YYYY-MM-DD}` suffix on `pipeline_output_*` is the date the
pipeline run produced that file. **Don't overwrite a Pass 1 from a
prior pipeline version when re-processing** — keep the older one as
evidence of what changed. See "Versioning" below.

## Versioning

Pipeline outputs are date-versioned because every code change to
`corrections.py`, `block_builder.py`, the chunker, or AI Correct
prompt-pack means a new run produces different text. The corpus is
the audit trail of those changes.

**Workflow when you re-process a case after a pipeline change:**

1. Run the case again through Tab 1 → Create Transcript → Run Corrections
2. Copy the new `_corrected.txt` to
   `pipeline_output_pass1_{today}.txt`
3. If you ran AI Correct, copy the new `_ai_corrected.txt` to
   `pipeline_output_pass2_{today}.txt`
4. Don't touch the older dated outputs — they document the prior
   pipeline state
5. Run the diff tool against the most recent dated outputs by default;
   it can target any date for historical comparison

**Ground truth doesn't get a date suffix.** It's the canonical correct
version. If you re-correct ground truth (e.g., spotted a typo months
later), git-style: just edit `ground_truth.txt` in place. The notes.md
should record when ground truth was last edited and why.

## Two diffs per case

When the diff tool eventually exists, it produces two separate
artifacts so the two failure modes don't get mixed together:

- **`{case_slug}.text.diff.md`** — homophones, proper-noun spellings,
  punctuation, capitalization, formatting. Drives candidates for
  `MULTIWORD_CORRECTIONS`, `confirmed_spellings`, AI Correct prompt
  iteration.
- **`{case_slug}.speakers.diff.md`** — speaker-label re-attributions
  ("this `MR. PENA:` line should be `A.`"). Drives investigation in
  `block_builder.py`, `classifier.py`, chunking config, Deepgram
  parameters.

Mixing the two in one diff makes it hard to triage. Keeping them
separate tells you immediately whether your next priority is structural
(speakers) or textual (words).

## Pre-applied confirmed_spellings

The diff tool **pre-applies the case's `confirmed_spellings` to the
pipeline output before computing the diff** against ground truth.
Reason: a case where `confirmed_spellings` was populated up front
would have those phonetic variants resolved during AI Correct anyway,
so showing them as "needed fixes" in a Pass 1 diff is noise that
obscures real new patterns.

If a case had **no `confirmed_spellings` populated when the transcript
was processed** (which is realistic — most early-pipeline runs won't
be fully populated), the diff tool will note that and you can decide
whether to:
- Add the missing entries to `job_config.json` and re-run, OR
- Leave them in the diff so the corpus surfaces them as candidates
  for the Bexar County / Texas legal seed file

## Rule of three

A pattern only graduates from a corpus diff into shipped pipeline code
(`MULTIWORD_CORRECTIONS`, `clean_block` rules) when it appears in
**three or more cases** AND has zero false-positive matches across the
rest of the corpus. The promotion tool will enforce this; until then,
hold rule additions to the same standard manually.

## What does NOT belong here

- Code. Use the regular project layout.
- Test fixtures. Those go under `*/tests/`.
- Audio files. Even with a clean filename they're enormous and we have
  the JSON sidecar.
- Anything that has to be merged across machines.

## PII and external sharing

`job_config.json` contains attorney emails, phone numbers, and
addresses. The whole `training_corpus/` directory is gitignored
specifically because of this — nothing here ever reaches GitHub.

**If a corpus entry needs to be shared externally** (e.g., for
off-machine analysis or vendor diff review), **sanitize at the point
of sharing — don't pre-sanitize the local copy.** Sanitizing the
local file would lose data the rest of the workflow depends on
(`witness_name`, `defense_counsel`, `confirmed_spellings`, etc.).

Suggested sanitize-on-share procedure:

1. Copy the corpus entry to a `share_{case_slug}/` scratch dir
2. Strip the PII fields from the copied `job_config.json`:
   - `defense_counsel[*].email`, `phone`, `address`
   - `plaintiff_counsel[*].email`, `phone`, `address`
   - `copy_attorneys[*].email`, `phone`, `address`
   - `reporter_name` if the reporter is the same as you (no need to
     share your own contact info externally)
3. Diff the testimony for any verbatim mentions of phone numbers,
   addresses, or email addresses spoken on the record; redact to
   `[REDACTED]`
4. Send the scratch dir; delete it afterwards

Don't make redaction routine. Most analysis happens locally; redaction
only matters at the share boundary.

## Tooling (deferred)

The plan calls for two tools to land **after** there are 3+ cases in
the corpus, because the structure of what to build only becomes clear
once a few cases have been categorized by hand:

- `tools/corpus_diff.py` — reads `pipeline_output_pass1_{date}.txt`
  and/or `pipeline_output_pass2_{date}.txt`, applies the case's
  `confirmed_spellings` to the pipeline output, then produces two
  separate categorized diffs against `ground_truth.txt` (text + speakers).
- `tools/corpus_promote.py` — given a candidate pattern, searches the
  whole corpus for support and false-positive risk, blocks promotion
  unless it appears in 3+ cases with zero false positives, generates
  the regression test.

Don't build these until there are actual cases to design against.

## Cleanup

Removing a corpus entry: `rm -rf training_corpus/{case_slug}`. Nothing
in the rest of the codebase has a hard reference to corpus entries,
so removing one is always safe.
