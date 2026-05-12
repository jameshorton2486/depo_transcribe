# Depo-Pro Transcribe

## Purpose

Depo-Pro Transcribe is a Windows desktop app that turns deposition audio into a
clean reading-copy Word document.

Current flow:

1. Audio/video file enters the `pipeline/` layer.
2. Deepgram produces diarized raw transcript output with word-level
   confidence scores.
3. `clean_format/` sends the raw transcript plus case metadata to
   Anthropic. Tokens whose Deepgram confidence falls below
   `LOW_CONFIDENCE_THRESHOLD` are wrapped with `‹LC:...›` markers
   before the call; the system prompt instructs the model to preserve
   them verbatim.
4. `clean_format/` writes a Texas-style deposition `.docx` with marked
   tokens rendered as yellow-highlighted runs for scopist review.

This app does **not** produce a UFM-certified verbatim record. The output is a
cleaned reading copy intended for downstream human review.

## Architecture

### Layer 1: `pipeline/`

Responsibilities:

- normalize audio
- chunk audio when needed
- call Deepgram
- merge chunk output
- write raw transcript / JSON files

Non-responsibilities:

- no legal transcript correction subsystem
- no DOCX layout
- no case-style cleanup rules

### Layer 2: `clean_format/`

Responsibilities:

- prepare the Anthropic system prompt
- chunk raw transcript text for model limits
- send a single cleanup pass per chunk
- assemble clean plain-text output
- write the deposition Word document

Non-responsibilities:

- no audio processing
- no Deepgram API work

### UI

The visible UI has two tabs:

- **Transcribe** (`ui/tab_transcribe.py`) — the primary user-facing
  workflow. Collects source file + case metadata, runs the
  transcription job, triggers clean-format generation, reports
  progress, and opens the output folder.
- **Templates** (`ui/tab_templates.py`) — UFM template generation.
  Loads case data and calls `ufm_engine/` to populate court-form
  templates (witness index, certification pages, exhibit index, etc.).

## Key Files

### Entry points

- `app.py` — launches the desktop app
- `config.py` — runtime config, output dirs, env loading
- `app_logging.py` — logging setup

### Active packages

Primary production flow (audio → transcript → DOCX):

- `pipeline/` — audio preprocessing, Deepgram transcription, assembly
- `clean_format/` — Anthropic cleanup pass + DOCX writer.
  Includes `low_confidence_markers.py` (Step C marker injection /
  validation), prompt at `clean_format/prompt.py` is strict-verbatim
  with low-confidence preservation instructions.
- `ui/app_window.py` — two-tab app shell
- `ui/tab_transcribe.py` — Transcribe tab workflow
- `ui/tab_templates.py` — Templates tab workflow
- `ui/dialog_combine_audio.py` — multi-file combine dialog
- `ui/_components.py` — shared UI constants/components
- `core/file_manager.py` — case folder creation
- `core/job_runner.py` — background transcription orchestration
- `core/job_config_manager.py` — read/write `job_config.json`
- `core/pdf_extractor.py` — PDF text extraction + intake handoff
- `core/intake_parser.py` — Anthropic-assisted intake parsing
- `core/keyterm_extractor.py` — Deepgram keyterm extraction
- `core/ufm_field_mapper.py` — maps intake data into saved case fields
- `core/vlc_player.py` — VLC wrapper

Parallel utility / offline pathways (not in the primary transcribe path):

- `spec_engine/` — deterministic structural enforcement for transcript
  blocks (classifier, Q/A enforcement, speaker normalization,
  corrections). Carries Deepgram word-level metadata through its data
  model via `TranscriptBlock.words`. Reachable from
  `core/corrections_runner.py` and `core/utterance_splitter_runner.py`
  — diagnostic/correction utilities, NOT called by `core/job_runner.py`.
- `ufm_engine/` — UFM template generation. `generator/`,
  `populator/`, `post_processor/`. Called from the Templates tab.
- `core/corrections_runner.py` — CLI entry into the spec_engine
  correction pipeline for offline re-processing of captured transcripts.
- `core/utterance_splitter_runner.py` — CLI entry into the spec_engine
  utterance splitter for offline transcript restructuring.

## Claude Cleanup Pass

`clean_format/formatter.py` is the full transcript cleanup pipeline.

It:

- loads the Anthropic API key from env
- uses `core.config.AI_MODEL`
- chunks raw transcript text around speaker-block boundaries
- sends each chunk with case metadata
- concatenates the returned clean text

The cleanup prompt is strict-verbatim. It instructs the model to:

- preserve filler words, stutters, false starts, and hedges exactly as
  spoken (legal-record fidelity, not narrative readability)
- preserve interruption markers (` -- `) and ellipses
- never reword, paraphrase, or "improve" testimony
- identify speaker roles from metadata and context
- convert examination into `Q.` / `A.` lines once the witness is sworn
- keep other speakers as labeled blocks
- preserve `‹LC:...›` low-confidence markers exactly (Step C); marked
  tokens are not reworded or re-cased

Full prompt at `clean_format/prompt.py`. Authority for the verbatim
posture: `docs/plans/verbatim_punctuation_plan_2026-05-12.md` and
Morson's English Guide for Court Reporters.

## Runtime Paths

Case folders are created under the configured base directory with:

- `{year}/{month}/{cause_number}/{last_first}/`
- `source_docs/`
- `Deepgram/`

Important outputs:

- `Deepgram/<timestamp>.txt`
- `Deepgram/<timestamp>.json`
- `Deepgram/raw_deepgram.txt`
- `Deepgram/raw_deepgram.json`
- `<case_root>/case_meta.json`
- `<case_root>/*_Deposition_YYYY-MM-DD.docx`

## Environment Variables

- `DEEPGRAM_API_KEY`
- `ANTHROPIC_API_KEY`

They are loaded from `.env` by `config.py`.

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

For targeted work:

```powershell
.\.venv\Scripts\python.exe -m pytest clean_format/tests -q
.\.venv\Scripts\python.exe -m py_compile app.py ui\app_window.py ui\tab_transcribe.py
```

## Tech Stack

| Area | Tool |
|---|---|
| Desktop UI | CustomTkinter |
| Speech-to-text | Deepgram via `httpx` |
| Cleanup model | Anthropic Claude |
| DOCX output | `python-docx` |
| PDF intake | `pdfplumber` |
| Config | `python-dotenv` |
| Media playback helper | `python-vlc` |
| Tests | `pytest` |

## Change Rules

1. Keep `pipeline/` focused on audio + Deepgram only.
2. Keep `clean_format/` focused on Anthropic cleanup + DOCX only. This
   is the primary production correction path.
3. Keep `spec_engine/` separate from the primary path. It's a parallel
   offline correction utility reachable through the `core/*_runner.py`
   scripts. Do not call into `spec_engine/` from `core/job_runner.py`
   or the UI's `_run_clean_format_job`. Do not merge `spec_engine/`
   concerns into `clean_format/`.
4. Prefer additive, direct fixes over framework churn.
5. Run compile/tests for files you touch.

## Safe Change Checklist

- Did the change stay within the correct layer?
- If UI changed, does the Transcribe tab still run end-to-end?
- If cleanup changed, do `clean_format/tests` still pass?
- If output paths changed, are case files still written inside the case folder?
- Did you avoid adding a dependency unless the code imports it?
