# CLAUDE.md — Depo-Pro Transcribe (Clean-Format Architecture)

## Purpose
Depo-Pro Transcribe converts deposition audio/video into a **clean reading-copy** Word transcript.

Current flow:
1. Audio preprocessing + chunking
2. Deepgram transcription
3. `clean_format` Claude cleanup pass
4. DOCX generation

This is **not** a UFM-certified verbatim record pipeline. It is a readability-first transcript workflow.

---

## Architecture (2 Layers)

### 1) `pipeline/` — Audio + Deepgram only
Responsibilities:
- Validate input media
- Normalize audio
- Chunk long audio
- Send chunks to Deepgram
- Reassemble chunks
- Write raw Deepgram outputs

Do not add formatting/business logic here.

### 2) `clean_format/` — Cleanup + DOCX only
Responsibilities:
- Send raw Deepgram transcript + case metadata to Claude in one cleanup pass
- Convert model output into clean transcript blocks
- Generate DOCX deposition output

Do not add audio handling/transcription logic here.

---

## Claude Cleanup Call
`clean_format/formatter.py` performs the single model call path:
- Uses `Anthropic` client
- Model sourced from `core/config.py` (`AI_MODEL`)
- Uses `ANTHROPIC_API_KEY`
- Splits oversized transcript input into chunked calls when needed

---

## Run
```bash
python app.py
```

---

## Test
```bash
pytest
```

---

## Environment Variables
Required:
- `DEEPGRAM_API_KEY` — Deepgram transcription API
- `ANTHROPIC_API_KEY` — Claude cleanup API

Loaded from `.env` by `config.py`.

---

## Tech Stack
| Area | Technology |
|---|---|
| UI | CustomTkinter |
| Transcription | Deepgram HTTP API via `httpx` |
| AI cleanup | Anthropic Claude |
| DOCX | `python-docx` |
| PDF text intake | `pdfplumber` |
| Env/config | `python-dotenv` |
| Media | FFmpeg, python-vlc |
| Tests | pytest |

---

## Surviving File Map

### Entry points
- `app.py`
- `config.py`
- `app_logging.py`

### Core
- `core/config.py`
- `core/file_manager.py`
- `core/job_runner.py`
- `core/job_config_manager.py`
- `core/intake_parser.py`
- `core/pdf_extractor.py`
- `core/keyterm_extractor.py`
- `core/ufm_field_mapper.py`
- `core/field_mapping.py`
- `core/vlc_player.py`

### Pipeline
- `pipeline/preprocessor.py`
- `pipeline/chunker.py`
- `pipeline/transcriber.py`
- `pipeline/assembler.py`
- `pipeline/exporter.py`
- `pipeline/audio_quality.py`
- `pipeline/vad_trimmer.py`
- `pipeline/audio_combiner.py`
- `pipeline/pyannote_diarizer.py`
- `pipeline/processor.py` (legacy helper; avoid new dependencies)

### Clean formatting
- `clean_format/prompt.py`
- `clean_format/formatter.py`
- `clean_format/docx_writer.py`
- `clean_format/__main__.py`

### UI
- `ui/app_window.py`
- `ui/tab_transcribe.py`
- `ui/dialog_combine_audio.py`
- `ui/_components.py`

### Tests
- `clean_format/tests/*`
- `core/tests/*` (surviving)
- `pipeline/tests/*` (surviving)

---

## Change Guidelines
1. Keep changes scoped to one layer when possible.
2. Prefer additive changes unless explicitly deleting obsolete code.
3. Preserve API key handling in `config.py`.
4. Keep `clean_format` output deterministic in structure.
5. Ensure `pytest` passes before merge.

---

## Quick Verification Checklist
- App launches with `python app.py`
- Transcription runs and writes raw outputs
- Formatting step runs and writes DOCX
- `pytest` passes
