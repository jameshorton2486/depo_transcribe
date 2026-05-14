# Current Pipeline Trace

**Scope:** READ-ONLY. Captures the exact function-by-function execution of the active Start Transcription path as of 2026-05-13.
**Companion docs:** `TRANSCRIPT_MUTATION_POINTS.md`, `SPEAKER_HANDLING_AUDIT.md`, `DEEPGRAM_FLOW_AUDIT.md`, `PLAYGROUND_DIFFERENCES.md`, `docs/plans/RAW_IMMUTABILITY_AND_PLAYGROUND_MODE_PLAN.md`.
**Builds on:** `docs/audits/ACTIVE_PATH_AUDIT.md` (which is the module-level map; this doc is the function-level execution sequence).

---

## Top-level sequence

```
ui/tab_transcribe.py::TranscribeTab.start_transcription              (line 3329)
   └─► spawns daemon thread → ui/tab_transcribe.py::_run_job          (line 3427)
        └─► core/job_runner.py::run_transcription_job                 (line 73)
              │
              ├─[A] pipeline/preprocessor.py::check_ffmpeg             (called via job_runner:128)
              ├─[B] pipeline/preprocessor.py::validate_audio_file      (line 135)
              ├─[C] pipeline/keyterm_sanitizer.py::sanitize_for_deepgram  (job_runner:152 — added 2026-05-13)
              ├─[D] core/file_manager.py::resolve_or_create_case       (line 200)
              ├─[E] pipeline/audio_quality.py::analyze_audio           (line 215)
              ├─[F] pipeline/preprocessor.py::normalize_audio          (line 242)  ← FFmpeg highpass + loudnorm + optional afftdn/noisereduce
              ├─[G] (optional) noisereduce.reduce_noise                (job_runner:260) ← RESCUE tier only
              ├─[H] pipeline/vad_trimmer.py::trim_silence              (line 274) ← Silero VAD
              ├─[I] pipeline/chunker.py::chunk_audio                   (line 306, when PLAYGROUND_MODE=False)
              │     or single-AudioChunk wrap (job_runner:294-303 when PLAYGROUND_MODE=True)
              │
              ├─[J] for each chunk:
              │       pipeline/transcriber.py::transcribe_chunk         (line 320)
              │         └─► pipeline/transcriber.py::_transcribe_direct (line 552)
              │              ├─► trim_keyterms_for_deepgram             (line 581 — defensive)
              │              ├─► httpx.post to https://api.deepgram.com/v1/listen  (line 604)
              │              ├─► pipeline/transcriber.py::_annotate_confidence
              │              ├─► pipeline/transcriber.py::smooth_speakers          (line 748)
              │              ├─► pipeline/transcriber.py::merge_utterances         (line 749 — 0.6 s gap)
              │              └─► _annotate_confidence pass 2
              │
              ├─[K] pipeline/assembler.py::reassemble_chunks            (line 333)
              │       ├─► overlap-window word dedup
              │       ├─► cross-chunk speaker remap (_build_speaker_remap)
              │       ├─► _merge_adjacent_same_speaker_overlap
              │       └─► pipeline/assembler.py::merge_utterances       (line 663 — 1.25 s gap)
              │
              ├─[L] core/job_runner.py::_build_transcript_from_utterances (line 20)
              ├─[M] writes <case>/Deepgram/raw_deepgram.{txt,json}      (line 350 + 379)
              ├─[N] writes <case>/Deepgram/<base>_<stamp>.{txt,json}    (timestamped pair, line 335-336)
              ├─[O] core/job_config_manager.py::merge_and_save           (line 411)
              ├─[P] done_callback → _on_transcription_done in UI
              │
              ▼
              UI thread continues with clean-format:
ui/tab_transcribe.py::_start_clean_format                              (line 3611)
   └─► spawns daemon thread → _run_clean_format_job                    (line 3624)
        │
        ├─[Q] writes <case>/case_meta.json                              (line 3638)
        ├─[R] clean_format/formatter.py::load_deepgram_words_from_json  (line 3649)
        ├─[S] clean_format/formatter.py::format_transcript              (line 3652)
        │       ├─► clean_format/speaker_turn_repair.py::repair_transcript_blocks  (added 2026-05-13)
        │       ├─► clean_format/low_confidence_markers.py::inject_markers
        │       ├─► clean_format/formatter.py::split_transcript          (chunk for Anthropic)
        │       ├─► for each chunk: Anthropic API call                   (formatter.py:280)
        │       ├─► clean_format/low_confidence_markers.py::validate_marker_round_trip
        │       └─► clean_format/formatter.py::_postprocess_formatted_text
        │
        └─[T] clean_format/docx_writer.py::write_deposition_docx        (line 3669)
                ├─► build_caption_table
                ├─► render proceedings paragraphs
                └─► safe_save to <case>/<Witness>_Deposition_<date>.docx
```

## Inputs and outputs per stage

| Stage | Reads | Writes (file or in-memory) | Notes |
|---|---|---|---|
| A | `ffmpeg` on PATH | — | Validates FFmpeg available |
| B | source audio | duration / size dict | `validate_audio_file` |
| C | UI keyterms + `DEFAULT_KEYTERMS` | sanitized list (in-memory) | New since 2026-05-13 |
| D | folder paths | case folder + `source_docs/`, `Deepgram/` | `resolve_or_create_case` |
| E | source audio | `AudioAnalysis` (tier, stereo, zoom_dual_mono, SNR) | `analyze_audio` |
| F | source audio + tier config | `temp/normalized_<stem>_<tier>_<hash>.wav` | FFmpeg highpass + loudnorm; sample-rate normalized to `TARGET_SAMPLE_RATE = 24000` |
| G | normalized WAV | overwrites normalized WAV | RESCUE tier only; `noisereduce` library, `prop_decrease=0.5` |
| H | normalized WAV | `temp/<stem>_vad.wav` | Silero VAD silence trim |
| I | trimmed/normalized WAV | `temp/chunk_NNN.wav` × N | `CHUNK_DURATION_SECONDS=600`, `CHUNK_OVERLAP_SECONDS=20`; bypassed when `PLAYGROUND_MODE=True` |
| J | each chunk WAV | per-chunk dict `{words, utterances, raw_utterances, transcript, raw}` | Deepgram POST + in-chunk smoothing + 0.6 s merge |
| K | all per-chunk dicts | assembled dict `{words, utterances, raw_utterances, transcript, raw_chunks}` | Overlap dedup + 1.25 s cross-chunk merge |
| L | assembled utterances | `transcript_text` string | One `"Speaker N: text\n\n"` block per utterance |
| M | assembled + transcript_text | `Deepgram/raw_deepgram.{txt,json}` | Canonical; overwritten each run |
| N | same | `Deepgram/<base>_<stamp>.{txt,json}` | Timestamped; new each run |
| O | UFM fields + intake bits | `source_docs/job_config.json` | `merge_and_save` |
| P | result dict | UI state | done_callback |
| Q | UFM fields + spellings + keyterms | `case_meta.json` | Read by Anthropic prompt |
| R | `raw_deepgram.json` | word list (in-memory) | For low-confidence marker injection |
| S | raw transcript text | formatted text (in-memory) | Anthropic cleanup with speaker_turn_repair pre-pass |
| T | formatted text + case_meta | `<Witness>_Deposition_<date>.docx` | DOCX with yellow LC highlights |

## Files that are written during a single run

| Path | When | Contents |
|---|---|---|
| `temp/normalized_<stem>_<tier>_<hash>.wav` | stage F | FFmpeg output (per-tier deterministic name) |
| `temp/<stem>_vad.wav` | stage H | Silence-trimmed WAV |
| `temp/chunk_NNN.wav` | stage I | Per-chunk WAV pieces |
| `<case>/Deepgram/<base>_<stamp>.{txt,json}` | stage N | Timestamped raw outputs |
| `<case>/Deepgram/<base>_<stamp>_raw.{txt,json}` | stage N | Pre-merge raw outputs (transcribe_direct's `raw_utterances`) |
| `<case>/Deepgram/raw_deepgram.{txt,json}` | stage M | **Canonical** raw outputs — OVERWRITTEN every run |
| `<case>/source_docs/job_config.json` | stage O | UFM fields + spellings + keyterms |
| `<case>/case_meta.json` | stage Q | Anthropic prompt context |
| `<case>/<Witness>_Deposition_<date>.docx` | stage T | Final DOCX |

## Cross-references

- The full module-level inventory: `docs/audits/ACTIVE_PATH_AUDIT.md` (every file in the codebase categorized WIRED / OFFLINE / DEAD / DUPLICATED / BYPASSED).
- Per-mutation-point detail: `TRANSCRIPT_MUTATION_POINTS.md`.
- Speaker handling specifically: `SPEAKER_HANDLING_AUDIT.md`.
- Deepgram-flow specifically: `DEEPGRAM_FLOW_AUDIT.md`.
- Playground divergences: `PLAYGROUND_DIFFERENCES.md`.

## Notes on existing partial work

- **PLAYGROUND_MODE toggle already exists** at `config.py:97` (default `False`). It is partially wired:
  - Bypasses chunking → single-Deepgram-request mode (`core/job_runner.py:286-303`).
  - Bypasses `normalize_audio` (`pipeline/preprocessor.py:367-375`).
  - Does **not** bypass VAD trim (`pipeline/vad_trimmer.py::trim_silence` still runs at job_runner:274).
  - Does **not** bypass `smooth_speakers` or `merge_utterances` (still runs inside `_transcribe_direct`).
  - Does **not** bypass `assembler.reassemble_chunks` (still runs at job_runner:333).
  - Does **not** bypass `speaker_turn_repair` (clean_format-stage; still runs).
  - **Gap:** the toggle reproduces "no chunking" but does not reproduce "no post-Deepgram transformation".
- **Keyterm sanitizer** wired 2026-05-13; sits between UI keyterm assembly and Deepgram request construction.
- **speaker_turn_repair** wired 2026-05-13; sits at the top of `format_transcript`, before Anthropic.
- **merge_debug_config** override hook (uncommitted) lives at `pipeline/merge_debug_config.py`; defaults to no-op.

These are all "additive" — they don't replace earlier stages; they layer on top.
