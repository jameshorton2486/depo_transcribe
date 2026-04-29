# Depo-Pro Transcribe

## Purpose

Depo-Pro Transcribe is a Windows desktop app that turns deposition audio into a
clean reading-copy Word document.

Current flow:

1. Audio/video file enters the `pipeline/` layer.
2. Deepgram produces diarized raw transcript output.
3. `clean_format/` sends the raw transcript plus case metadata to Anthropic.
4. `clean_format/` writes a Texas-style deposition `.docx`.

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

The visible UI is the Transcribe tab only.

Responsibilities:

- collect source file + case metadata
- run the transcription job
- trigger clean-format generation
- report progress and open the output folder

## Key Files

### Entry points

- `app.py` — launches the desktop app
- `config.py` — runtime config, output dirs, env loading
- `app_logging.py` — logging setup

### Active packages

- `pipeline/` — audio preprocessing, Deepgram transcription, assembly
- `clean_format/` — Anthropic cleanup + DOCX writer
- `ui/app_window.py` — single-tab app shell
- `ui/tab_transcribe.py` — active user workflow
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

## Claude Cleanup Pass

`clean_format/formatter.py` is the full transcript cleanup pipeline.

It:

- loads the Anthropic API key from env
- uses `core.config.AI_MODEL`
- chunks raw transcript text around speaker-block boundaries
- sends each chunk with case metadata
- concatenates the returned clean text

The cleanup prompt is intentionally narrow:

- remove filler and stutters when non-substantive
- preserve substantive meaning
- identify speaker roles from metadata and context
- convert examination into `Q.` / `A.` lines
- keep other speakers as labeled blocks

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
2. Keep `clean_format/` focused on cleanup + DOCX only.
3. Do not reintroduce a second correction subsystem.
4. Prefer additive, direct fixes over framework churn.
5. Run compile/tests for files you touch.

## Safe Change Checklist

- Did the change stay within the correct layer?
- If UI changed, does the Transcribe tab still run end-to-end?
- If cleanup changed, do `clean_format/tests` still pass?
- If output paths changed, are case files still written inside the case folder?
- Did you avoid adding a dependency unless the code imports it?
