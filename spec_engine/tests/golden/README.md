# Golden Transcript Tests

The active golden system uses committed fixture folders under:

`spec_engine/tests/golden/{case_name}/`

Each case folder contains:

| File | Required | Purpose |
|---|---|---|
| `input.txt` | yes | Raw transcript input in `Speaker N:` format |
| `job_config.json` | yes | Full saved case config with `ufm_fields.speaker_map_verified=true` |
| `expected.txt` | yes | Human-verified corrected transcript output |
| `deepgram.json` | optional | Word-level Deepgram payload used by the correction runner |

## What the golden test locks

For every committed case, the test asserts that:

1. the fixture files are complete and non-empty
2. `speaker_map_verified` is `true`
3. the correction pipeline succeeds
4. `corrected_text` matches `expected.txt`
5. the written `_corrected.txt` file on disk matches `corrected_text`

This is the regression contract for the legal transcript pipeline.

## How to add a new golden case

1. Run the full correction pipeline on a real case and verify the output manually.
2. Create a new folder: `spec_engine/tests/golden/{case_name}/`
3. Copy in:
   - `input.txt`
   - `job_config.json`
   - `expected.txt`
   - `deepgram.json` if available
4. Ensure `job_config.json` includes:
   - `ufm_fields`
   - `confirmed_spellings` as needed
   - `ufm_fields.speaker_map_verified = true`
5. Run:

```powershell
.venv\Scripts\python.exe -m pytest spec_engine/tests/test_golden.py -v
```

6. Review any diff output carefully before committing.

## Current committed cases

- `case_001`
