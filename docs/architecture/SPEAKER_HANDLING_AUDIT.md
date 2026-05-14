# Speaker Handling Audit

**Scope:** every active-path location where speaker attribution is read, smoothed, remapped, labeled, or derived. Read-only.
**Companion:** `TRANSCRIPT_MUTATION_POINTS.md`.

The legal-record fidelity contract for this app is: **the witness's words must remain attributed to the witness**, the attorney's questions must remain attributed to the attorney. Every place a speaker ID changes is a place that legal record could become wrong. This document enumerates them all.

---

## Speaker data flow on the active path

```
Deepgram response (HTTP)
   │
   │  Per-word: results.channels[0].alternatives[0].words[i].speaker  (int)
   │  Per-utterance: results.utterances[i].speaker  (int)
   │
   ▼
pipeline/transcriber.py::_transcribe_direct
   ├─► extracts per-word speaker ints into a flat list (line ~715-720)
   ├─► extracts per-utterance speaker int (line ~726-742)
   ├─► [A1] smooth_speakers  (line 222)              ← MUTATION
   ├─► [A2] merge_utterances (per-chunk)             ← gap-based; uses speaker int as merge gate
   └─► returns dict with int speaker IDs intact (raw_utterances) AND merged version
       │
       ▼
pipeline/assembler.py::reassemble_chunks
   ├─► [B1] _build_speaker_remap (cross-chunk)       ← MUTATION (rewrites integer IDs)
   ├─► [B2] applies remap to words AND utterances    (lines 617-626, 641-646)
   ├─► [B3] _merge_adjacent_same_speaker_overlap     ← drops candidates (speaker-aware)
   ├─► [B4] merge_utterances (cross-chunk)           ← gap-based; uses speaker int as merge gate
   └─► [B5] _attach_speaker_labels                   ← DERIVES a string label per utterance
       │
       ▼
output: <case>/Deepgram/raw_deepgram.{txt,json}
   ├─► `utterances[i].speaker`        — integer (post-remap, post-merge)
   ├─► `utterances[i].speaker_label`  — string (derived heuristic)
   ├─► `raw_utterances[i].speaker`    — integer (pre-cross-chunk-merge; post per-chunk smooth)
   └─► `words[i].speaker`             — integer (post-remap)
       │
       ▼
clean_format/speaker_turn_repair.py::repair_transcript_blocks
   ├─► parses ``<label>: <text>`` blocks from raw_deepgram.txt
   ├─► splits some blocks (Rules A-D) but INHERITS the same speaker label
   │       — does NOT invent new speakers
   └─► output: same label structure, more paragraphs
       │
       ▼
clean_format/formatter.py::format_transcript → Anthropic
   ├─► Anthropic sees ``Speaker N: text`` blocks
   ├─► Anthropic prompt instructs: "convert examination into Q./A. lines once witness is sworn"
   ├─► Anthropic may re-attribute on its own (model-driven, non-deterministic)
   └─► output: Q./A. + speaker-label blocks (now text, no speaker integers)
       │
       ▼
clean_format/formatter.py::_postprocess_formatted_text
   ├─► [C1] COURT REPORTER:\t → THE REPORTER:\t
   ├─► [C2] VIDEOGRAPHER:\t → THE VIDEOGRAPHER:\t
   └─► [C3] DUNNELL_RE pattern → MR. DUNNELL: (Cavazos-specific; case-sensitive)
       │
       ▼
clean_format/docx_writer.py → DOCX paragraphs with speaker labels
```

---

## Mutation points by stage

### [A1] `pipeline/transcriber.py::smooth_speakers` — lines 222-268

**What it does:** in a window of 3 utterances (prev, current, next), if speaker(prev) == speaker(next) and speaker(current) is different, AND current is short, AND gaps on both sides are small, **rewrites current.speaker to match prev/next**.

**Guards in place:**
- `_is_short_glitch` further constrains by duration (`SHORT_GLITCH_MAX_DURATION_SECONDS = 0.2`) and short-answer whitelist (`SHORT_ANSWER_WHITELIST` = canonical witness responses: yes, no, yeah, nope, correct, right, sure, okay, ok, true, false, uh-huh, mm-hmm, …)
- Short-answer whitelist is intended to PROTECT witness "Yes." / "No." from being smoothed.

**Risk:**
- If the witness responds with anything NOT in the whitelist (e.g. a 4-word answer "I do not recall"), and the duration is < 0.2 s, smoothing rewrites them as the attorney. Silent.
- If Deepgram emits a witness response with the same speaker number as the attorney (the upstream-diarization failure documented at length in `MERGE_THRESHOLD_FINAL_REPORT.md`), this stage cannot help because it's only same-speaker-flip detection.

**Signal in logs:** `logger.debug("Smoothing speaker glitch index=%s …")` — DEBUG, not visible at default INFO level.

### [B1] `pipeline/assembler.py::_build_speaker_remap` — lines 605-614

**What it does:** when reassembling adjacent chunks, builds a `{int_speaker_id_in_new_chunk: int_speaker_id_to_remap_to}` map so cross-chunk speaker identity stays consistent.

**Mechanism (read of `_build_speaker_remap` is implied by the call site — function lives elsewhere in assembler.py):**
- Overlap word window is computed (`max(0.0, chunk_start_offsets[i] - CHUNK_OVERLAP_SECONDS)`)
- Words / utterances in the overlap window are compared between chunks
- Speaker integers that appear to be the same human get mapped to a common ID

**Risk:**
- Heuristic-driven. If chunk 1 ended on speaker 0 (attorney) and chunk 2 starts on speaker 0 (a DIFFERENT person who happens to share an integer assigned by Deepgram-the-chunk-2-call), they'd be unified into a single speaker. Silent rewrite of which human was speaking.
- No audit log entry today.

### [B2] Remap application — `assembler.py:617-626, 641-646`

The remap result is applied to every word in `all_words[-words_added_count:]` and every utterance in `source_utterances` from the new chunk. The original integers are not preserved alongside the remapped ones.

### [B3] `_merge_adjacent_same_speaker_overlap` — `assembler.py:654`

Drops candidate utterances entirely when they overlap (by time) the prior accepted utterance and share the same speaker integer. Different speakers are never merged.

**Risk:** if `_build_speaker_remap` mis-unified two different people, this stage will now collapse one of them silently.

### [B4] `merge_utterances` (cross-chunk) — `assembler.py:663`

Same-speaker-only merge with `gap_threshold_seconds = 1.25` default. **Cannot cross speakers.** Documented in `MERGE_THRESHOLD_FINAL_REPORT.md`.

### [B5] `_attach_speaker_labels` — `assembler.py:376`

**What it does:** builds a `role_map: {int_id: string_label}` and stamps each utterance with `speaker_label`. The role_map is heuristic — first speaker to ask a question becomes `"EXAMINING ATTORNEY"`, etc. (driven by `ROLE_SEQUENCE`).

**Risk:**
- Heuristic. On a deposition where a defense attorney enters mid-deposition, the role label can mis-attribute. This is layered semantic interpretation — the assembler is asserting "this integer means this role".
- Downstream code reads `speaker_label`, not the integer. So a mis-labeled utterance carries the wrong human identity throughout the rest of the pipeline.

### Anthropic — `clean_format/formatter.py::format_transcript`

The model receives `"Speaker N: text"` blocks (or `"THE REPORTER: text"`, etc., after `_attach_speaker_labels` produced role labels) and outputs `Q.`/`A.` lines + speaker labels. The model's attribution is non-deterministic.

**Risk:** the legal-record-relevant content (who said what) is now in the hands of a language model whose output varies per run. The Anthropic prompt is strict-verbatim but does not pin speaker identity; the model uses context.

### [C1-C3] Post-Anthropic regex — `clean_format/formatter.py::_postprocess_formatted_text`

Static substitutions on speaker labels: `COURT REPORTER` → `THE REPORTER`, `VIDEOGRAPHER` → `THE VIDEOGRAPHER`, and a Cavazos-specific Dunnell pattern.

**Risk:** low — these are purely cosmetic relabeling, no re-attribution.

---

## Where silent speaker corruption can enter

In descending order of concern:

1. **`smooth_speakers` (A1)** — rewrites speaker integers based on short-glitch heuristics. No log entry at INFO level. No "this changed" output anywhere.
2. **`_build_speaker_remap` (B1)** — rewrites speaker integers based on overlap heuristics. No audit trail of which original ID became which new ID.
3. **`_attach_speaker_labels` (B5)** — turns integer speaker IDs into role strings via heuristic. The integer→role mapping is not persisted.
4. **Anthropic cleanup** — the model re-attributes Q./A. The Anthropic system prompt does not strictly pin speaker ID to integer; it does it from context.
5. **`raw_deepgram.{txt,json}` overwrite on re-run** — the canonical source-of-truth is destroyed each time. Any human review against the prior file becomes impossible after a re-run.

**Today the system has zero audit records of which speaker ID changed where.** The Phase-2+ plan's "speaker_validation" layer (Phase G) addresses this with an explicit `speaker_changes.json`.

---

## Where speaker truth is NOT mutated (verified)

- `clean_format/speaker_turn_repair.py` — splits blocks but inherits speaker labels exactly. Provenance preserved in `SpeakerTurnRepairResult`.
- `clean_format/low_confidence_markers.py` — annotates words; never touches speaker.
- `clean_format/docx_writer.py` — pure layout; reads `speaker_label` as-is.

These are the parts of the pipeline that are already legally clean.

---

## Recommendations distilled (for the plan, not for action here)

The Phase-2+ plan's risk gates should treat the following as **VERY HIGH** until they have:

- a persisted audit trail of every speaker change (what was, what is, why)
- a saved ground-truth comparison fixture (e.g. a known-good Cavazos run) to regression-test against

The components that fail this test today and therefore must not be refactored before the audit framework exists:

- `pipeline/transcriber.py::smooth_speakers`
- `pipeline/assembler.py::_build_speaker_remap`
- `pipeline/assembler.py::_attach_speaker_labels`
- the Anthropic cleanup speaker-attribution behavior in `clean_format/formatter.py::format_transcript`
