# Deepgram Flow Audit

**Scope:** every active-path interaction with Deepgram. What we send, what we receive, what we transform on either side. Read-only.
**Companion docs:** `CURRENT_PIPELINE_TRACE.md`, `PLAYGROUND_DIFFERENCES.md`.

---

## Pre-Deepgram audio transformations

| Stage | Source code | Conditions | Effect on the audio Deepgram receives |
|---|---|---|---|
| FFmpeg highpass | `pipeline/preprocessor.py::_build_filter_chain` (CLEAN, ENHANCED, RESCUE configs) | Always (any tier), 80 Hz | Removes low-frequency rumble; Deepgram receives band-limited audio |
| FFmpeg loudnorm | same | Always (any tier) | EBU R128 loudness normalization; Deepgram receives a level-normalized signal |
| FFmpeg afftdn | same | OFF in all three production tiers | Not used in production |
| noisereduce | `core/job_runner.py:260` | RESCUE tier only (`prop_decrease=0.5`, `stationary=True`) | Spectral noise reduction; Deepgram receives a denoised signal |
| Sample-rate conversion | `pipeline/preprocessor.py` (target = `config.TARGET_SAMPLE_RATE = 24000`) | Always | Deepgram receives 24 kHz mono WAV (when stereo collapse is applied) |
| Stereo handling | `pipeline/audio_quality.py::analyze_audio` + preprocessor | When `zoom_dual_mono` detected → extract_left | Eliminates echo on Zoom recordings; Deepgram receives a single channel |
| VAD silence trim | `pipeline/vad_trimmer.py::trim_silence` | Always (Silero VAD) | Removes long silent gaps; Deepgram receives a shorter, denser audio; **timestamps in the response are relative to the trimmed input** |
| Chunking | `pipeline/chunker.py::chunk_audio` | When `PLAYGROUND_MODE=False` | Deepgram receives N separate 600 s chunks with 20 s overlap; per-chunk results are stitched in `assembler.reassemble_chunks` |

**Implication:** unless `PLAYGROUND_MODE=True`, the audio Deepgram receives is materially different from the audio the user uploaded. This is by design today but is the principal cause of the "diverges from Playground" complaint that the refactor charter calls out.

---

## Deepgram request parameters

All requests are built in `pipeline/transcriber.py::_transcribe_direct` (line 552-602). Two constraints govern the parameters:

1. The **per-request defaults dict** at line 583-595.
2. The **REQUIRED_DEEPGRAM_FLAGS** override dict at line 87-95 — `enforce_required_deepgram_flags` is called LAST and overwrites any caller-supplied value for the listed keys.

Effective sent parameters on every chunk:

| Parameter | Value | Source |
|---|---|---|
| `model` | `nova-3` (or `nova-3-medical` if caller specifies) | Per-request default + caller |
| `language` | `en` | Per-request default |
| `smart_format` | `true` | REQUIRED_DEEPGRAM_FLAGS |
| `diarize` | `true` | REQUIRED_DEEPGRAM_FLAGS |
| `punctuate` | `true` | REQUIRED_DEEPGRAM_FLAGS |
| `paragraphs` | `true` | REQUIRED_DEEPGRAM_FLAGS |
| `utterances` | `true` | REQUIRED_DEEPGRAM_FLAGS |
| `utt_split` | `0.8` | REQUIRED_DEEPGRAM_FLAGS |
| `filler_words` | `true` | Per-request default |
| `numerals` | `true` | Per-request default |
| `keyterm` | list (up to `MAX_KEYTERM_COUNT = 98`; pre-sanitized by `pipeline/keyterm_sanitizer.py`) | From job_runner |

Verified against `docs/audits/UTTERANCE_CONFIGURATION_AUDIT_2026-05-13.md`. **No env-var override exists** for any of these; they are source-code-pinned.

---

## Deepgram response shape (per chunk)

The HTTP body returned by `https://api.deepgram.com/v1/listen?...` has this shape (as parsed in `_transcribe_direct`):

```
{
  "results": {
    "channels": [
      {
        "alternatives": [
          {
            "transcript": "<full chunk transcript>",
            "words": [
              {
                "word": "...",
                "punctuated_word": "...",
                "start": <float>,
                "end": <float>,
                "confidence": <float>,
                "speaker": <int>,
                "type": "word"
              },
              ...
            ],
            "paragraphs": { "transcript": "...", "paragraphs": [ ... ] }   # NOT preserved through assembler
          }
        ]
      }
    ],
    "utterances": [
      {
        "transcript": "...",
        "start": <float>, "end": <float>,
        "speaker": <int>,
        "confidence": <float>,
        "words": [ ... per-utterance word list ... ],
        ...
      },
      ...
    ]
  },
  "metadata": { ... }
}
```

---

## Post-Deepgram transformations (per chunk, inside `_transcribe_direct`)

1. **`raw_utterances` extraction** (line ~726-742) — Deepgram's `utterances[]` is unpacked into a per-chunk list. The `words` array on each utterance is structurally reformatted into the app's preferred shape `{word, punctuated_word, start, end, speaker, confidence, type}`. **No content change** but the shape is normalized.
2. **`_annotate_confidence` pass 1** (line 747) — adds derived `low_confidence: bool` to each utterance based on `min(word.confidence)` vs `LOW_CONFIDENCE_THRESHOLD = 0.85`.
3. **`smooth_speakers`** (line 748) — see `SPEAKER_HANDLING_AUDIT.md::[A1]`.
4. **`merge_utterances` (per chunk, gap = 0.6 s)** (line 749).
5. **`_annotate_confidence` pass 2** (line 754) — reannotates after merge.

Return shape:

```python
{
    "words": [...],            # post-Deepgram, with speaker ints intact
    "utterances": [...],       # POST per-chunk merge (gap 0.6)
    "merged_utterances": [...], # alias of utterances
    "raw_utterances": [...],   # POST smooth_speakers, PRE per-chunk merge
    "transcript": "...",       # the per-chunk transcript text
    "raw": {...},              # the full original Deepgram response body
}
```

The `raw` key is the only field that carries the unmodified Deepgram response.

---

## Cross-chunk assembly (`pipeline/assembler.py::reassemble_chunks`)

See `TRANSCRIPT_MUTATION_POINTS.md` and `SPEAKER_HANDLING_AUDIT.md` for the per-step detail. Briefly:

1. **Timestamp adjustment** — each chunk's relative timestamps are offset by `chunk_start_offsets[i]` so they become absolute.
2. **Word-level dedup over the overlap window** — `assembler.py:583-595`.
3. **Cross-chunk speaker remap** — `assembler.py:605-614`.
4. **Adjacent overlap-same-speaker utterance drop** — `assembler.py:654`.
5. **Cross-chunk `merge_utterances` (gap = 1.25 s)** — `assembler.py:663`.
6. **`_attach_speaker_labels`** — derives `speaker_label` strings.

Output shape returned from `reassemble_chunks`:

```python
{
    "words": [...],            # offsets applied, deduplicated, speaker remap applied
    "utterances": [...],       # POST cross-chunk merge, with `speaker_label` attached
    "raw_utterances": [...],   # the per-chunk raw_utterances pooled together (PRE cross-chunk merge)
    "transcript": "...",       # built via build_transcript_text
    "raw_chunks": [...],       # the per-chunk Deepgram response bodies (the `raw` key from each)
}
```

The `raw_chunks` entry is the closest thing today to the immutable raw store — it's a list of the original Deepgram HTTP response bodies per chunk. But it's **only kept in memory**; it goes into `raw_deepgram.json` under the key `chunks` (`core/job_runner.py:370`) and then nothing further reads it on the production path. It's also subject to the same "overwritten on re-run" risk as the canonical file.

---

## What raw_deepgram.json on disk actually contains

Top-level keys after `core/job_runner.py:356-381` writes the file:

| Key | Source |
|---|---|
| `audio_file` | original source audio path |
| `model` | the Deepgram model used |
| `audio_quality` | string (`"ENHANCED (fair audio)"` etc.) |
| `audio_tier` | `analysis.tier` (CLEAN / ENHANCED / RESCUE) |
| `created_at` | run timestamp |
| `duration_sec` | source duration |
| `word_count`, `utterance_count`, `chunk_count` | counts |
| `deepgram_keyterms_used` | sanitized keyterm list |
| `transcript` | reconstructed transcript text |
| `chunk_summaries` | per-chunk metadata (file path, start_seconds, end_seconds) |
| `utterances` | **post-mutation** assembled utterances |
| `raw_utterances` | pre-cross-chunk-merge, post-per-chunk-smooth+merge |
| `words` | post-mutation flat word list |
| `chunks` | the per-chunk `raw` Deepgram response bodies |

**Misleading naming:** `raw_deepgram.json` is the *canonical artifact name*, but its top-level `utterances` and `words` keys are *post-mutation*. Only `chunks` carries the unmutated per-chunk response.

The Phase-2+ plan's Raw Immutability layer disambiguates this: a new `raw_store` writes the pristine Deepgram response separately as `Deepgram/raw_dg_response_<stamp>.json` and marks `raw_deepgram.json` as derived.

---

## Where Deepgram options can change at runtime today

- **Caller-supplied:** model (`nova-3` or `nova-3-medical`), keyterms.
- **Source-code-only:** every other flag.
- **No environment variables.**
- **No UI toggle** (Playground Mode bypasses preprocessing + chunking but does not toggle Deepgram parameters).
