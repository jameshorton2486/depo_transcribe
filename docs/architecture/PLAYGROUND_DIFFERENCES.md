# Differences from Deepgram Playground

**Scope:** the concrete points where the production active path diverges from "what Deepgram Playground would do" on the same source audio file. Read-only.
**Companion:** `DEEPGRAM_FLOW_AUDIT.md`, `TRANSCRIPT_MUTATION_POINTS.md`.

Deepgram Playground (web UI at `playground.deepgram.com`) does the simplest possible thing: takes the file the user uploads, sends it once to the API with whatever flags are toggled in the Playground UI, displays the response. The application's production path is more complex than that. This document enumerates every concrete divergence so the Phase-3 "True Playground Mode" implementation knows exactly what to bypass.

---

## Divergence 1 — audio normalization (FFmpeg highpass + loudnorm)

| | Playground | Production |
|---|---|---|
| What the user sends | Original file bytes | FFmpeg-processed WAV (highpass 80 Hz + loudnorm) |
| Source code | n/a | `pipeline/preprocessor.py::normalize_audio` |
| Why production does it | Loudness-normalized audio improves Deepgram accuracy on quiet recordings | — |
| Current PLAYGROUND_MODE behavior | n/a | **Already bypassed** (`pipeline/preprocessor.py:367-375` returns the original path when `PLAYGROUND_MODE=True`) |

---

## Divergence 2 — VAD silence trimming (Silero)

| | Playground | Production |
|---|---|---|
| What the user sends | Original duration | Trimmed audio with silent gaps removed |
| Source code | n/a | `pipeline/vad_trimmer.py::trim_silence` |
| Why production does it | Reduces processing cost and may help Deepgram diarization on long silences | — |
| Effect on response | Playground timestamps align with original audio | Production response timestamps align with the *trimmed* audio; mapping back to original requires the VAD segment table |
| Current PLAYGROUND_MODE behavior | n/a | **NOT bypassed today** — `job_runner.py:271-284` still calls `trim_silence` |

This is a **silent timestamp divergence**. Even with PLAYGROUND_MODE on, the Deepgram timestamps are NOT directly comparable to Playground timestamps unless VAD is also bypassed.

---

## Divergence 3 — Zoom dual-mono single-channel extraction

| | Playground | Production |
|---|---|---|
| What the user sends | Full stereo file | Single channel (left, when Zoom dual-mono detected) |
| Source code | n/a | `pipeline/audio_quality.py::analyze_audio` + `pipeline/preprocessor.py::_select_channel_strategy` |
| Why production does it | Zoom records both speakers into both channels; using one channel eliminates echo artifacts that confuse Deepgram diarization | — |
| Current PLAYGROUND_MODE behavior | n/a | **NOT bypassed today** — `analyze_audio` always runs |

---

## Divergence 4 — RESCUE-tier `noisereduce`

| | Playground | Production |
|---|---|---|
| What the user sends | Original | `noisereduce`-processed audio (only when RESCUE tier auto-detected) |
| Source code | n/a | `core/job_runner.py:260` |
| Why production does it | Helps Deepgram on phone-quality / very-noisy audio | — |
| Current PLAYGROUND_MODE behavior | n/a | **Already bypassed conditionally** — only fires on RESCUE tier; bypass requires forcing CLEAN tier or wiring an unconditional bypass |

---

## Divergence 5 — chunking (600 s with 20 s overlap)

| | Playground | Production |
|---|---|---|
| What the user sends | One request | N requests of 600 s each with 20 s overlap, then locally reassembled |
| Source code | n/a | `pipeline/chunker.py::chunk_audio` + `pipeline/assembler.py::reassemble_chunks` |
| Why production does it | Avoid Deepgram per-request size/duration limits; allow per-chunk progress reporting | — |
| Effect on response | Single contiguous response with one diarization pass | N diarization passes, then locally stitched. Cross-chunk speaker continuity requires `_build_speaker_remap` heuristic; word-level overlap dedup requires the overlap window logic |
| Current PLAYGROUND_MODE behavior | n/a | **Already bypassed** (`core/job_runner.py:288-303` wraps the audio in a single-AudioChunk when `PLAYGROUND_MODE=True`) |

A single Deepgram request with `PLAYGROUND_MODE=True` will fail on long depositions (>~10 minutes) — Deepgram's per-request size/timeout limits apply.

---

## Divergence 6 — per-chunk smoothing (`smooth_speakers`)

| | Playground | Production |
|---|---|---|
| What happens to short single-utterance speaker flips | Returned as-is | Rewritten to match surrounding speaker (`pipeline/transcriber.py::smooth_speakers`) |
| Current PLAYGROUND_MODE behavior | n/a | **NOT bypassed today** — runs unconditionally in `_transcribe_direct` |

---

## Divergence 7 — per-chunk `merge_utterances` (0.6 s gap)

| | Playground | Production |
|---|---|---|
| Utterance boundaries | At Deepgram's `utt_split=0.8` boundaries | Re-merged with 0.6 s same-speaker gap inside each chunk |
| Source | n/a | `pipeline/transcriber.py::merge_utterances` |
| Current PLAYGROUND_MODE behavior | n/a | **NOT bypassed today** |

---

## Divergence 8 — cross-chunk overlap dedup

| | Playground | Production |
|---|---|---|
| Word list | Single response, no overlap | Words in the overlap window are deduplicated by content+timestamp (`assembler.py:583-595`) |
| Current PLAYGROUND_MODE behavior | Skipped naturally because PLAYGROUND_MODE produces one chunk | n/a |

Caveat: when PLAYGROUND_MODE is True there is exactly one chunk, so `reassemble_chunks` takes the single-chunk branch at `assembler.py:539-552` which still calls `merge_utterances` (Divergence 10 below).

---

## Divergence 9 — cross-chunk speaker remap (`_build_speaker_remap`)

| | Playground | Production |
|---|---|---|
| Speaker integer continuity | Native (one diarization pass) | Heuristic remap across chunk boundaries |
| Current PLAYGROUND_MODE behavior | Skipped naturally because there's only one chunk | n/a |

---

## Divergence 10 — cross-chunk `merge_utterances` (1.25 s gap)

| | Playground | Production |
|---|---|---|
| Utterance boundaries | Deepgram's native | Re-merged with 1.25 s same-speaker gap across the entire reassembled output |
| Source | n/a | `pipeline/assembler.py::merge_utterances` (line 663) |
| Current PLAYGROUND_MODE behavior | n/a | **NOT bypassed today** — still runs even when there's only one chunk because `reassemble_chunks` always calls it |

This is one of the biggest behavioral divergences: even with PLAYGROUND_MODE on, the assembler's cross-chunk merge widens utterance time spans.

---

## Divergence 11 — `_attach_speaker_labels` derived role strings

| | Playground | Production |
|---|---|---|
| Speaker label format | Integer (`speaker: 0`) | String role label (`speaker_label: "THE WITNESS"`) via heuristic |
| Source | n/a | `pipeline/assembler.py::_attach_speaker_labels` |
| Current PLAYGROUND_MODE behavior | n/a | **NOT bypassed today** |

---

## Divergence 12 — clean_format / Anthropic / DOCX (post-transcription)

| | Playground | Production |
|---|---|---|
| Output format | JSON + plain-text transcript | DOCX with caption, appearances, Q./A. formatting, yellow LC highlights |
| Source | n/a | `clean_format/formatter.py`, `clean_format/speaker_turn_repair.py`, `clean_format/docx_writer.py` |
| Current PLAYGROUND_MODE behavior | n/a | These run regardless of PLAYGROUND_MODE; Anthropic is invoked, DOCX is produced |

For a pure Playground parity test, the user would want to STOP after the raw Deepgram response is saved and not run the cleanup / DOCX pass. Today there is no UI toggle to skip those stages.

---

## Summary — what True Playground Mode should bypass

For Phase-3 "True Playground Mode" to be honest about reproducing Playground output, it needs to bypass:

| # | Divergence | Currently bypassed by `PLAYGROUND_MODE=True`? |
|---|---|:---:|
| 1 | FFmpeg highpass + loudnorm | ✅ |
| 2 | VAD silence trim | ❌ |
| 3 | Zoom dual-mono extract_left | ❌ |
| 4 | RESCUE noisereduce | conditional only |
| 5 | Chunking | ✅ |
| 6 | Per-chunk `smooth_speakers` | ❌ |
| 7 | Per-chunk `merge_utterances` (0.6 s) | ❌ |
| 8 | Cross-chunk word dedup | n/a (single chunk) |
| 9 | Cross-chunk speaker remap | n/a (single chunk) |
| 10 | Cross-chunk `merge_utterances` (1.25 s) | ❌ — still fires with single chunk |
| 11 | `_attach_speaker_labels` role-string derivation | ❌ |
| 12 | clean_format / Anthropic / DOCX | ❌ — would require a UI toggle / config knob |

Today PLAYGROUND_MODE bypasses 2 of 12 divergences. To genuinely match Playground output, the toggle must extend to most of the rest. This is what the Phase-3 plan specifies.

The single biggest gap is **Divergence 10** (cross-chunk merge running on single-chunk runs). Closing that should be the first behavior to add to PLAYGROUND_MODE because it's a one-line guard at `pipeline/assembler.py:663` and removes the most surprising divergence.
