# Transcript Mutation Points

**Scope:** every active-path location that modifies transcript text, words, utterances, speaker IDs, or timings on the journey from Deepgram response → DOCX. Read-only.
**Companion:** `CURRENT_PIPELINE_TRACE.md`, `SPEAKER_HANDLING_AUDIT.md`.

Each row is scored on the **refactor-risk class** that the Phase-2+ plan uses for sequencing.

| Risk class | Definition |
|---|---|
| **LOW** | Pure addition / annotation; reversible without behavior loss. |
| **MEDIUM** | Modifies wording, punctuation, or formatting but does not change speaker attribution or word identity. |
| **HIGH** | Modifies speaker attribution, drops words, merges/splits utterances, or changes timings. |
| **VERY HIGH** | Modifies the legal record of who said what. Removal/change requires a saved ground-truth comparison. |

---

## Table of mutation points (active path)

| Step | File:line | What it mutates | Mutates speaker? | Mutates word identity? | Mutates timing? | Risk |
|---|---|---|:---:|:---:|:---:|:---:|
| Pre-Deepgram audio normalize | `pipeline/preprocessor.py::normalize_audio` (line 358) | Audio sample data (highpass + loudnorm) | — | — | — | MEDIUM (changes Deepgram input) |
| Pre-Deepgram VAD trim | `pipeline/vad_trimmer.py::trim_silence` | Audio segment selection (silence removed) | — | — | YES (introduces offset; Deepgram operates on trimmed audio) | **HIGH** (timestamps in Deepgram response are relative to trimmed input — see Playground divergence) |
| Pre-Deepgram chunking | `pipeline/chunker.py::chunk_audio` | Splits audio into 600 s chunks with 20 s overlap | — | — | YES (chunk-relative timestamps; offset added in assembler) | MEDIUM (overlap dedup is later) |
| Per-chunk smoothing | `pipeline/transcriber.py::smooth_speakers` (line 222) | Re-labels short single-utterance speaker flips on detected glitches | **YES — silent** | — | — | **VERY HIGH** |
| Per-chunk merge | `pipeline/transcriber.py::merge_utterances` (line 271) | Combines adjacent same-speaker utterances with gap ≤ 0.6 s | — | — | YES (start/end of merged utterance widens) | HIGH |
| Cross-chunk word dedup | `pipeline/assembler.py::reassemble_chunks` (line 583-595) | Drops words whose start ≤ previous chunk's last `end` and whose lowercased text matches | — | YES (drops words) | — | HIGH |
| Cross-chunk speaker remap | `pipeline/assembler.py::_build_speaker_remap` (line 605-614) | Rewrites integer speaker IDs of newly-arrived words/utterances when they overlap by content with the previous chunk | **YES — silent** | — | — | **VERY HIGH** |
| Adjacent overlap-window merge | `pipeline/assembler.py::_merge_adjacent_same_speaker_overlap` (line 654) | Drops candidate utterances that overlap the prior utterance with same speaker | — | YES (drops candidate utterance entirely) | — | HIGH |
| Cross-chunk merge | `pipeline/assembler.py::merge_utterances` (line 663) | Combines adjacent same-speaker utterances with gap ≤ 1.25 s | — | — | YES | HIGH |
| Speaker label inference | `pipeline/assembler.py::_attach_speaker_labels` (line 376) | Assigns string `speaker_label` (e.g. `"THE WITNESS"`, `"EXAMINING ATTORNEY"`) via role heuristic | **YES — derived label** | — | — | **HIGH** (downstream uses this string) |
| Transcript text assembly | `core/job_runner.py::_build_transcript_from_utterances` (line 20) | Joins utterances into `"<speaker_label>: <text>\n\n"` blocks | — | — | — | LOW |
| Save raw outputs | `core/job_runner.py:340-379` | Writes canonical `raw_deepgram.{txt,json}` (overwrites each run) | — | — | — | **VERY HIGH** (canonical is overwritten — see plan's Phase A) |
| Speaker-turn repair | `clean_format/speaker_turn_repair.py::repair_transcript_blocks` (called from `clean_format/formatter.py::format_transcript`) | Splits single Deepgram blocks containing fused Q/A into separate paragraphs; speaker label is inherited (no new speaker invented) | NO (inherits) | — | — | LOW (deterministic, conservative; provenance preserved) |
| Low-confidence markers | `clean_format/low_confidence_markers.py::inject_markers` | Wraps below-threshold words with `‹LC:...›` | — | — | — | LOW (annotation only; markers stripped at render time) |
| Anthropic cleanup | `clean_format/formatter.py::format_transcript` Anthropic POST | Rewrites text content per `clean_format/prompt.py` strict-verbatim rules; converts examination to `Q.`/`A.` lines | **YES — model-driven** | YES (model may reword filler), guarded by prompt | — | **VERY HIGH** (this is the load-bearing AI step) |
| Post-Anthropic regex | `clean_format/formatter.py::_postprocess_formatted_text` | Speaker-label normalization (`COURT REPORTER` → `THE REPORTER` etc.), title spacing (`Dr. `/`Mr. `/`Ms. `), em-dash normalization, sentence double-space | **YES — name-substitution** | YES (cosmetic) | — | MEDIUM |
| DOCX render | `clean_format/docx_writer.py::write_deposition_docx` | Layout only — marker boundaries informing yellow runs | — | — | — | LOW |

## Where transcript truth is duplicated

| Form on disk | Source-of-truth?  | Notes |
|---|:---:|---|
| `<case>/Deepgram/<base>_<stamp>.json` (timestamped per-run raw response after assembler) | YES — frozen at run time | Never overwritten |
| `<case>/Deepgram/<base>_<stamp>_raw.json` (pre-cross-chunk-merge per-run output) | YES — frozen at run time | Never overwritten |
| `<case>/Deepgram/<base>_<stamp>.txt` | derived | Built from `_build_transcript_from_utterances` |
| `<case>/Deepgram/<base>_<stamp>_raw.txt` | derived | Built from raw_utterances |
| `<case>/Deepgram/raw_deepgram.json` | **canonical, but OVERWRITTEN each run** | This is the file every other tool reads. Phase-2 plan moves true canonicality to a write-once file. |
| `<case>/Deepgram/raw_deepgram.txt` | **canonical, but OVERWRITTEN each run** | Same risk. |
| `<case>/case_meta.json` | snapshot | Written into the Anthropic context |
| `<case>/<Witness>_Deposition_<date>.docx` | terminal artifact | The user-visible record |
| `<case>/source_docs/job_config.json` | persisted prep state | Reloaded by `_auto_detect_source_docs` |

**The single most concerning duplication** is that `raw_deepgram.{txt,json}` are the de-facto canonical files but they are **overwritten on every run**. A re-run of the same case (which the user did today for Etminan) destroys the prior canonical. The timestamped `_<stamp>` files survive but no downstream tool reads them.

---

## Where "transcript truth" first becomes ambiguous

Looking at the table above, transcript truth is unambiguous **only between Deepgram's HTTP response body and the saved per-chunk timestamped JSON**. From that point forward:

- `smooth_speakers` silently re-labels short single-utterance "glitches". If a witness's "Yes." appears mid-attorney-block, it gets reclassified as the attorney.
- `merge_utterances` (per chunk) widens utterance time spans.
- `_build_speaker_remap` reassigns integer speaker IDs across chunk boundaries to enforce continuity — if Deepgram's chunk-2 speaker 0 is the same human as chunk-1's speaker 1, our remap rewrites it. Silent.
- `merge_utterances` (cross chunk) widens further.
- `_attach_speaker_labels` derives a role label (`"THE WITNESS"`, `"EXAMINING ATTORNEY"`) via heuristics on the labeled utterance.
- `raw_deepgram.{txt,json}` are written AFTER all of the above.

So the "raw" file on disk today is actually **post-mutation**. The refactor's Phase A (raw immutability) needs to draw a new boundary: an untouched copy of the Deepgram response saved BEFORE `_annotate_confidence`, `smooth_speakers`, `merge_utterances`, and `reassemble_chunks` run.

---

## Risk-class summary (for sequencing the refactor plan)

| Risk | Count of mutation points |
|---|---:|
| LOW | 4 (text assembly, speaker_turn_repair, marker injection, DOCX render) |
| MEDIUM | 3 (normalize, chunking, post-Anthropic regex) |
| HIGH | 5 (VAD trim, per-chunk merge, cross-chunk dedup, adjacent overlap merge, cross-chunk merge, _attach_speaker_labels) |
| VERY HIGH | 4 (smooth_speakers, _build_speaker_remap, raw file overwrite, Anthropic cleanup) |

The VERY HIGH set is where the legal-record risk concentrates. The plan's risk gates target these directly: nothing in the VERY HIGH set is touched until raw immutability + parity testing infrastructure exist.
