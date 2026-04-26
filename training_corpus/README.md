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
├── README.md                       (tracked)
├── .gitkeep                        (tracked, keeps the dir in git)
├── {case_slug}/                    (per-case, gitignored)
│   ├── case_id.txt                 — single line: cause number
│   ├── pipeline_output.txt         — what your pipeline produced
│   ├── ground_truth.txt            — the version you'd certify
│   ├── job_config.json             — copy of the case's job config
│   └── notes.md                    — optional context
└── _diffs/                         (auto-generated, gitignored)
    └── {case_slug}.diff.md
```

`{case_slug}` convention: `lastname_YYYY_MM_DD`, lowercase, e.g.
`singh_2026_04_23`. Match the deposition date, not the date you
processed it.

## Files per case

Four required + one optional. **Don't add anything else** — the tooling
will assume the layout is fixed.

| File | Required | Source |
|---|---|---|
| `case_id.txt` | yes | one line, the cause number, no header |
| `pipeline_output.txt` | yes | copy of the `_corrected.txt` your pipeline produced |
| `ground_truth.txt` | yes | hand-corrected version you'd certify and deliver |
| `job_config.json` | yes | copy of `{case}/source_docs/job_config.json` |
| `notes.md` | optional | who certified, what was hard, anything weird |

## Workflow

1. **Process a deposition normally** through the app. The pipeline
   writes `_corrected.txt` to the case's `Deepgram/` folder.
2. **Create a corpus entry** when you've finished hand-correcting:
   - `mkdir training_corpus/{case_slug}`
   - Copy `_corrected.txt` → `pipeline_output.txt`
   - Save the hand-corrected version → `ground_truth.txt`
   - Copy `job_config.json` from the case's `source_docs/`
   - Write the cause number into `case_id.txt`
3. **Run the diff tool** (when it exists — see "Tooling" below).

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

## Tooling (deferred)

The plan calls for two tools to land **after** there are 3+ cases in
the corpus, because the structure of what to build only becomes clear
once a few cases have been categorized by hand:

- `tools/corpus_diff.py` — reads `pipeline_output.txt` and
  `ground_truth.txt`, produces a categorized line-by-line diff into
  `_diffs/{case_slug}.diff.md`.
- `tools/corpus_promote.py` — given a candidate pattern, searches the
  whole corpus for support and false-positive risk, blocks promotion
  unless it appears in 3+ cases, generates the regression test.

Don't build these until there are actual cases to design against.

## PII notes

`job_config.json` contains attorney emails, phone numbers, addresses.
That's why the directory is gitignored. If you ever need to share a
corpus entry externally (e.g. with a vendor), strip PII first by
copying just `case_style`, `cause_number`, `speaker_map`, and
`confirmed_spellings`.

## Cleanup

Removing a corpus entry: `rm -rf training_corpus/{case_slug}`. Nothing
in the rest of the codebase has a hard reference to corpus entries,
so removing one is always safe.
