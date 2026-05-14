# Raw Layer Validation — Phase A persistence flow

**Purpose:** document the exact persistence flow that Phase A added, so the end-to-end validation run can be inspected against the documented contract.

---

## Where the raw store file is written

| Field | Value |
|---|---|
| Filesystem path | `<case_dir>/Deepgram/raw_dg_response_<stamp>.json` |
| `<stamp>` format | `YYYYMMDD_HHMMSS` (local time) |
| Read-only after write | YES — `os.chmod(0o444)` |
| Refuses to overwrite | YES — `FileExistsError` if the target already exists |

The plan originally proposed `output/raw/<case>/raw_dg_response_<stamp>.json`. I placed the file under `<case_dir>/Deepgram/` instead so the immutable raw lives next to the existing per-run timestamped files and travels with the case folder when archived.

## When the file is written — exact ordering

In `core/job_runner.py`, between the per-chunk transcribe loop and `reassemble_chunks`:

```
… for chunk in chunks:
        result = transcribe_chunk(chunk.file_path, model, keyterms, …)
        chunk_results.append(result)
        chunk_offsets.append(chunk.start_seconds)

# >>> raw_store writes HERE <<<
    pipeline.raw_store.save_raw_response(
        case_path,
        chunk_results=chunk_results,
        chunk_offsets=chunk_offsets,
        audio_file=audio_path,
        model=model,
    )

# >>> all mutation begins here <<<
reassemble_chunks(chunk_results, chunk_offsets)
   # · cross-chunk word dedup
   # · cross-chunk speaker remap
   # · cross-chunk merge_utterances (gap 1.25 s)
   # · _attach_speaker_labels role derivation
```

The raw store runs **before** any of the assembler mutation stages.

It runs **after** the per-chunk transcribe call, which itself currently performs:
- `_annotate_confidence` (annotation only — no content change)
- `smooth_speakers` (silent speaker rewrite — **a known mutation that runs BEFORE raw_store**)
- per-chunk `merge_utterances` (gap 0.6 s — **another mutation BEFORE raw_store**)

**Important caveat:** the saved file contains `chunk_results[i]["raw"]`, which is the **untouched Deepgram HTTP response body** for each chunk. The `smooth_speakers` and per-chunk `merge_utterances` mutations operate on a separate `utterances` field in the same dict — they do NOT modify the `raw` body. So even though `smooth_speakers` and per-chunk merge run before the raw_store call, the persisted `raw` body is unaffected by them.

The intent of Phase A is preserved: the on-disk JSON contains the literal Deepgram HTTP response per chunk.

## What gets persisted (schema_version 2)

```json
{
  "schema_version": 2,
  "saved_at_utc": "2026-05-13T15:52:27Z",
  "saved_at_local": "2026-05-13T10:52:27",
  "audio_file": "C:/Users/.../Audio.mp3",
  "model": "nova-3",
  "request_params": { /* post-validation Deepgram params actually sent */ },
  "keyterms_sent": [ /* post-sanitization keyterm list actually transmitted */ ],
  "chunk_count": N,
  "chunks": [
    {
      "index": 0,
      "start_seconds": 0.0,
      "deepgram_response": { …unmodified Deepgram HTTP body for chunk 0… }
    },
    …
  ]
}
```

The `deepgram_response` field is byte-identical to `chunk_results[i]["raw"]` at the time of write, which itself is the parsed JSON returned by the Deepgram HTTP API.

## What this layer does NOT do (Phase A boundaries)

- It does not bypass `smooth_speakers` or per-chunk `merge_utterances`. Those still run inside `_transcribe_direct` before the raw store sees the chunk. Bypassing them is Phase C work (true Playground Mode) and Phase G work (assembler refactor).
- It does not consume the saved file. No downstream reader exists yet. The file is a forensic safety net for later phases.
- It does not change `Deepgram/raw_deepgram.{txt,json}` behavior. Those files continue to be written exactly as before (post-mutation, overwritten on re-run).
- It does not change Anthropic / DOCX behavior.

## Validation markers added to the pipeline

To make the layer-boundary ordering visible in `logs/pipeline.log` during the validation run, these temporary markers were added:

| Marker | Where it logs from | When it fires |
|---|---|---|
| `[VALIDATION] [RAW RESPONSE SAVED]` | `core/job_runner.py` | Immediately after `raw_store.save_raw_response` succeeds |
| `[VALIDATION] [TRANSCRIPT MUTATION BEGINS]` | `core/job_runner.py` | Immediately before `reassemble_chunks` |
| `[VALIDATION] [STRUCTURED LAYER START]` | `clean_format/formatter.py::format_transcript` | At the top of the function, before `repair_transcript_blocks` |
| `[VALIDATION] [FORMATTING LAYER START]` | `clean_format/formatter.py::format_transcript` | After `repair_transcript_blocks`, before `inject_markers` + Anthropic |

These markers are temporary and will be removed once Phase A validation is complete and the validation reports are accepted.

## How to inspect a real run

After running a single case end-to-end with `WALKTHROUGH_CAPTURE` or via the UI Start Transcription button:

1. **Check the new file exists:**
   `Get-Item "<case_dir>/Deepgram/raw_dg_response_*.json"`
2. **Confirm read-only:**
   `Get-ChildItem "<case_dir>/Deepgram/raw_dg_response_*.json" | Select-Object IsReadOnly` → True.
3. **Confirm the JSON has the right shape:**
   `python -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['schema_version'], d['chunk_count'])"`
4. **Confirm ordering in `logs/pipeline.log`:** `[RAW RESPONSE SAVED]` must appear before `[TRANSCRIPT MUTATION BEGINS]`, which must appear before `[STRUCTURED LAYER START]` and `[FORMATTING LAYER START]`.
5. **Confirm the existing canonical files were also written:** `Deepgram/raw_deepgram.{txt,json}` and the timestamped pair under the same Deepgram/ directory.
