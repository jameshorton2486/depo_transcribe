# Golden Transcript Tests

Each golden test is a triplet of files:

| File | Purpose |
|---|---|
| `{name}_input.docx` | Deepgram-format DOCX used as pipeline input |
| `{name}_job_config.json` | Saved JobConfig with `speaker_map_verified=True` |
| `{name}_expected.txt` | Expected block-by-block output (`BLOCKTYPE: text`) |

## How to add a new golden test

1. Run Spec Process on the deposition normally and verify the output is correct.
2. Copy the source DOCX to `spec_engine/tests/golden/{name}_input.docx`.
3. Copy the saved job config to `{name}_job_config.json`.
4. Generate the expected output:

```powershell
.venv\Scripts\python.exe tools\generate_golden_expected.py `
    spec_engine\tests\golden\{name}_input.docx `
    spec_engine\tests\golden\{name}_job_config.json `
    spec_engine\tests\golden\{name}_expected.txt
```

5. Review `{name}_expected.txt`.
6. Commit all three files together.

## First golden test

Suggested first fixture:
- `coger_input.docx`
- `coger_job_config.json`
- `coger_expected.txt`

Until those files exist, the golden test skips automatically.
