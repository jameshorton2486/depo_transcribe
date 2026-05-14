# Utterance Configuration Audit — 2026-05-13

**Scope:** READ-ONLY. No production code was modified during this audit.

**Trigger:** Operational observation that a 83-minute deposition produced
~340 utterances on the active Start-Transcription path, behavior more
consistent with `utt_split ≈ 0.9–1.2` than with the documented
`utt_split = 0.8`.

**TL;DR (one-line conclusion):**
`utt_split = 0.8` **IS** being sent to Deepgram on every active-path
request. The "behaves like utt_split ≈ 1.2" observation is real, but
it is caused by **two local utterance-merge passes** that run
downstream of the Deepgram response, not by a wrong Deepgram setting.
Deepgram returned **1,107** utterances on the audited case; the local
merge stack collapsed them to **340** before they were ever written to
`raw_deepgram.json` as `utterances`. The Deepgram-native count is
preserved in the same file as `raw_utterances` (1,107).

---

## Section 1 — Active Production Path

### Runtime call chain (Start Transcription)

```
ui/tab_transcribe.py::TranscribeTab._start_transcription
    └─► core/job_runner.py::run_job             (background thread)
            └─► pipeline/transcriber.py::transcribe_chunk      (× chunks)
                    └─► pipeline/transcriber.py::_transcribe_direct
                            • builds params dict
                            • normalize_params(...)
                            • enforce_required_deepgram_flags(...)
                            • validate_deepgram_params(...)
                            • urlencode → POST https://api.deepgram.com/v1/listen
                            • parses JSON response
                            • smooth_speakers(raw_utterances)
                            • merge_utterances(raw_utterances, 0.6s gap)     ← LOCAL MERGE #1
            ◄── returns per-chunk {utterances, raw_utterances, words, ...}
            └─► pipeline/assembler.py::reassemble_chunks(chunk_results, offsets)
                    • timestamp adjustment + cross-chunk word dedup
                    • merge_utterances(all_raw_utterances, 1.25s gap)        ← LOCAL MERGE #2
            ◄── returns assembled {utterances, raw_utterances, words, ...}
            • writes Deepgram/raw_deepgram.{txt,json}
            • writes raw_deepgram.txt from assembled raw_utterances
```

### Where utt_split enters the payload

Two source sites, both in `pipeline/transcriber.py`:

1. **`REQUIRED_DEEPGRAM_FLAGS`** dict at `pipeline/transcriber.py:87-95`:
   ```python
   REQUIRED_DEEPGRAM_FLAGS = {
       "utterances": "true",
       "diarize": "true",
       "paragraphs": "true",
       "punctuate": "true",
       "smart_format": "true",
       "numerals": "true",
       "utt_split": "0.8",
   }
   ```
2. **Per-request defaults** inside `_transcribe_direct` at
   `pipeline/transcriber.py:583-596`:
   ```python
   params = normalize_params(
       {
           "model": model,
           "language": "en",
           "smart_format": True,
           "diarize": True,
           "punctuate": True,
           "paragraphs": True,
           "utterances": True,
           "utt_split": "0.8",
           "filler_words": True,
           "numerals": True,
       }
   )
   params = enforce_required_deepgram_flags(params)
   params = validate_deepgram_params(params)
   ```

Both values agree (`"0.8"`). Both are stringified booleans/values for
the urlencoded query string. The `enforce_required_deepgram_flags`
step is the final arbiter — it `update`s the params with
`REQUIRED_DEEPGRAM_FLAGS`, so any caller-injected value would be
silently overridden. This is asserted by
`pipeline/tests/test_transcriber.py:211-228`
(`test_enforce_required_deepgram_flags_overrides_invalid_values`).

### Where the value cannot change downstream

There is no mutation between
`enforce_required_deepgram_flags(params)` and the HTTP send. The
intermediate `validate_deepgram_params` only **rejects** invalid
TitleCase booleans; it does not rewrite values. The final URL is
constructed at `pipeline/transcriber.py:602-604`:

```python
query = _parse.urlencode(params, doseq=True)
url = f"https://api.deepgram.com/v1/listen?{query}"
```

The value Deepgram receives is `utt_split=0.8`. Confirmed.

---

## Section 2 — All References

### `utt_split` references

| Location | Type | Active? | Value | Notes |
|---|---|---|---|---|
| `pipeline/transcriber.py:94` | Production constant (`REQUIRED_DEEPGRAM_FLAGS`) | **Active** | `"0.8"` | Authoritative — final override before request |
| `pipeline/transcriber.py:592` | Production default (per-request dict) | **Active** | `"0.8"` | Initial value; redundant with #1 |
| `pipeline/transcriber.py:83` | Comment | n/a | n/a | Documentation referencing 0.8 + paragraphs=true as Playground parity |
| `pipeline/transcriber.py:573` | Comment | n/a | n/a | Notes prior value was 0.5; bumped to 0.8 |
| `pipeline/tests/test_transcriber.py:63` | Test assertion | Test only | `"0.8"` | `test_transcribe_chunk_sends_default_utt_split_to_deepgram` |
| `pipeline/tests/test_transcriber.py:121` | Test assertion | Test only | `"0.8"` | `test_transcribe_chunk_uses_requested_defaults` |
| `pipeline/tests/test_transcriber.py:219` | Test input | Test only | `"1.2"` | Crafted bad input |
| `pipeline/tests/test_transcriber.py:228` | Test assertion | Test only | `"0.8"` | Confirms `enforce_required_deepgram_flags` overrides "1.2" → "0.8" |

There are **no other** `utt_split` references in the repo (no
config files, no env-var reads, no UI controls).

### `utterances` (Deepgram option) references

| Location | Type | Active? | Value |
|---|---|---|---|
| `pipeline/transcriber.py:88` | `REQUIRED_DEEPGRAM_FLAGS` | **Active** | `"true"` |
| `pipeline/transcriber.py:591` | Per-request default | **Active** | `True` |

### `endpointing` / `vad_events`

**Zero matches** in the entire codebase. Neither option is configured.
(These are Deepgram streaming-only options; this app uses the prerecorded
HTTP endpoint, so absence is correct — but worth recording for the audit
trail.)

### `paragraphs` (Deepgram option) references

| Location | Type | Active? | Value |
|---|---|---|---|
| `pipeline/transcriber.py:90` | `REQUIRED_DEEPGRAM_FLAGS` | **Active** | `"true"` |
| `pipeline/transcriber.py:590` | Per-request default | **Active** | `True` |

`spec_engine/block_builder.py:72-91` prefers paragraph-based parsing
when present. **HOWEVER:** the Etminan `raw_deepgram.json` did not
contain a top-level `paragraphs` key (verified at audit time:
`'has paragraphs at top level: False'`). Deepgram returns
paragraphs nested inside `results.channels[0].alternatives[0].paragraphs`,
but the assembler currently flattens only `utterances` and `words`
into the saved JSON. Investigation of why paragraphs do not survive
into block_builder is **out of scope** for this audit but recorded
here as a related observation.

### Diarization

| Location | Type | Active? | Value |
|---|---|---|---|
| `pipeline/transcriber.py:89` | `REQUIRED_DEEPGRAM_FLAGS` | **Active** | `"true"` |
| `pipeline/transcriber.py:588` | Per-request default | **Active** | `True` |

### Local segmentation / merge constants (downstream of Deepgram)

These are **not** Deepgram options — they govern post-response merging
performed in this codebase. They are the principal cause of the
observed coarse utterance grouping.

| Location | Constant | Value | Used in |
|---|---|---|---|
| `pipeline/transcriber.py:33` | `MERGE_GAP_THRESHOLD_SECONDS` | `0.6` | `merge_utterances` per chunk |
| `pipeline/transcriber.py:34` (vicinity) | `MERGE_MIN_WORD_COUNT` | (see file) | `merge_utterances` per chunk |
| `pipeline/transcriber.py` | `SHORT_GLITCH_MAX_DURATION_SECONDS` | (see file) | `smooth_speakers`, `merge_utterances` |
| `pipeline/transcriber.py` | `STRICT_MERGE` | (see file) | `merge_utterances` gate |
| `pipeline/assembler.py:31` | `GAP_THRESHOLD_SECONDS` | **`1.25`** | `merge_utterances` across chunks |
| `pipeline/assembler.py:32` | `SHORT_GAP_THRESHOLD_SECONDS` | `0.6` | `merge_utterances` short-utterance gate |
| `pipeline/assembler.py:33` | `MIN_UTTERANCE_WORDS` | `2` | `merge_utterances` gate |
| `pipeline/assembler.py:34` | `SPEAKER_GLITCH_DURATION_SECONDS` | `0.5` | `_is_speaker_flip_glitch` |

`pipeline/assembler.py:31` (`GAP_THRESHOLD_SECONDS = 1.25`) is the
single most consequential value for the observed coarse grouping —
see Section 6.

---

## Section 3 — Actual Production Value Reaching Deepgram

**The real value Deepgram is receiving on every chunk request is:**

```
utt_split=0.8
```

This is verifiable by reading the source code along the call chain
(Sections 1 and 2). No environment variable, no config file, no UI
control, no saved preference can change it. `enforce_required_deepgram_flags`
is the final stop and it pins `utt_split` to `"0.8"`.

**No conflicting `utt_split` values exist in production code.** The
only `"1.2"` reference is the deliberately-bad test input at
`pipeline/tests/test_transcriber.py:219`.

**No omission risk.** `utt_split` is in both `REQUIRED_DEEPGRAM_FLAGS`
and the per-request defaults; one would have to actively delete keys
from a dict via subclassing to bypass it, which no caller does.

---

## Section 4 — Transcription Configuration Flow

```
                                            +-----------------------------+
                                            | config.py (env loading)     |
                                            |   DEEPGRAM_API_KEY only     |
                                            +--------------+--------------+
                                                           |
                                                           v
+-----------------------------+    creates    +------------+------------+
| ui/tab_transcribe.py        |-------------> | core/job_runner.run_job |
|   model (str)               |  invoke as    +------------+------------+
|   merged_keyterms (list)    |  thread args               |
+-----------------------------+                            v
                                            +-------------+-------------+
                                            | pipeline/transcriber.py   |
                                            |   transcribe_chunk(       |
                                            |     audio_file_path,      |
                                            |     model=...,            |
                                            |     keyterms=...,         |
                                            |   )                       |
                                            +-------------+-------------+
                                                          |
                                                          v
                                            +-------------+-------------+
                                            | _transcribe_direct        |
                                            |   1. build params dict    |
                                            |   2. normalize_params     |
                                            |   3. enforce_required_*   |  <-- utt_split locked to 0.8 here
                                            |   4. validate_*           |
                                            |   5. urlencode + POST     |
                                            +-------------+-------------+
                                                          |
                                              Deepgram response (JSON)
                                                          |
                                                          v
                                            +-------------+-------------+
                                            | _transcribe_direct        |
                                            |   - extract words         |
                                            |   - extract raw_utterances|
                                            |   - _annotate_confidence  |
                                            |   - smooth_speakers       |
                                            |   - merge_utterances      |  <-- LOCAL MERGE #1 (0.6s)
                                            +-------------+-------------+
                                                          |
                                                          v
                                            +-------------+-------------+
                                            | assembler.reassemble_     |
                                            | chunks                    |
                                            |   - timestamp adjust      |
                                            |   - cross-chunk dedup     |
                                            |   - merge_utterances      |  <-- LOCAL MERGE #2 (1.25s)
                                            +-------------+-------------+
                                                          |
                                                          v
                                            +-------------+-------------+
                                            | job_runner writes         |
                                            |   raw_deepgram.{txt,json} |
                                            +---------------------------+
```

### Inputs that can vary per run

- **Model**: caller-supplied (`"nova-3"` default, `"nova-3-medical"`
  optional). Validated against `ALLOWED_MODELS` at line 858.
- **Keyterms**: caller-supplied list, normalized by
  `trim_keyterms_for_deepgram` (line 467). Empty list is fine.
- **Audio file path**: caller-supplied.

### Inputs that are immutable per run

- Every other Deepgram option (`utt_split`, `diarize`, `paragraphs`,
  `punctuate`, `utterances`, `smart_format`, `numerals`, `filler_words`,
  `language=en`). Hard-coded in source. No external override mechanism.

### Mutation points

- `enforce_required_deepgram_flags` (`pipeline/transcriber.py:432`) is
  the **only** point where a caller-supplied value can be silently
  rewritten. Currently it pins seven Deepgram flags + `utt_split`.
- `validate_deepgram_params` (line 438) **rejects** stale TitleCase
  values; does not mutate.
- `normalize_params` (line 425) lowercases boolean string
  representations; does not change semantic value.

---

## Section 5 — Stale / Duplicate Config

### Duplication: `utt_split = "0.8"` exists in two places in transcriber.py

- `pipeline/transcriber.py:94` (`REQUIRED_DEEPGRAM_FLAGS`)
- `pipeline/transcriber.py:592` (per-request defaults dict)

Both agree. The duplication is intentional per the comment at
`pipeline/transcriber.py:84-86`:

> "paragraphs=true and utt_split=0.8 are Playground-parity defaults —
> keep them aligned with the per-request dict in `_transcribe_direct`
> so the documentation visible to a reader matches the enforced reality."

Functionally redundant because `enforce_required_deepgram_flags` always
overrides; documentation-wise informative. **Not a bug**, but worth
recording as a duplication source — if one is changed without the
other, the source code becomes misleading.

### Duplication: `merge_utterances` exists in two modules

There are **two distinct** functions named `merge_utterances`, with
different signatures and different default thresholds:

- `pipeline/transcriber.py:271` — `gap_threshold_seconds = 0.6` (default)
- `pipeline/assembler.py:162` — `gap_threshold_seconds = 1.25` (default)

Both are imported and used on the active path. They are **not** the
same function and **not** a refactor candidate within the scope of
this audit, but their coexistence + similar names + different defaults
is the principal source of confusion about what the application is
actually doing to utterance boundaries.

The transcriber.py version handles within-chunk merge; the
assembler.py version handles across-chunk merge. Neither has a
docstring that names the other; a reader chasing one will not
automatically know the other exists.

### `pipeline/exporter.py` — dead in production

Per `docs/reports/dead_module_hygiene_audit_2026-05-15.md:76`, the
only inbound import is from `pipeline/tests/test_exporter.py`. No
production module references it. Out of scope for this audit but
recorded for completeness.

### `pipeline/pyannote_diarizer.py` — alternate diarization path

Reads `HF_TOKEN` from env. Not called from `core/job_runner.py`. This
is an inactive alternate diarization path. Out of scope — has no
bearing on `utt_split`.

### `core/utterance_splitter_runner.py` — offline splitter

This is the AI-based utterance splitter wired to the offline
Run-Corrections path (`spec_engine/utterance_splitter.py`). It runs
on saved JSON, not on the active Start-Transcription path. Mentioned
here because the name overlaps thematically with `utt_split`; the
two are unrelated. CLAUDE.md confirms this lives outside the active
path.

### No stale env-var-driven config

`grep -r "getenv\|os.environ"` across `pipeline/` and
`core/job_runner.py` returns only `DEEPGRAM_API_KEY` (and an
unrelated `HF_TOKEN` in the inactive pyannote module). There is
**no** environment-variable mechanism to override `utt_split` or any
other Deepgram option in production code paths.

### No alternative HTTP/SDK path

The repo references the Deepgram URL exactly once:
`pipeline/transcriber.py:604`. No `DeepgramClient`, no
`PrerecordedOptions`, no SDK import anywhere. All traffic flows
through `_transcribe_direct`. No second-path risk.

---

## Section 6 — Observed Behavior Correlation

The user observed:
- ~348 utterances on a ~83-minute deposition
- merged Q/A blocks
- merged attorney/witness turns
- "behavior consistent with utt_split ≈ 0.9–1.2"

**Etminan case data (audited at the time of writing):**

| Stage | Field | Count |
|---|---|---|
| Deepgram response (post per-chunk merge) | `raw_utterances` in raw_deepgram.json | **1,107** |
| After `assembler.reassemble_chunks` cross-chunk merge | `utterances` in raw_deepgram.json | **340** |
| Chunks transcribed | `chunk_count` | 9 |
| Model | `model` | `nova-3` |
| Audio tier | `audio_tier` | `ENHANCED` |

**Reconciliation:**

- Deepgram at `utt_split=0.8` produced **~1,107 utterances** — fine-grained
  and consistent with the requested value.
- The two-stage local merge stack collapsed those to **340** before
  they reached the formatter, the spec_engine, or any downstream
  visibility.
- The user's "behaves like utt_split=1.2" intuition is **directionally
  correct about the symptom** but **misattributed about the cause**.
  The application IS clustering utterances about as aggressively as a
  hypothetical utt_split=1.25 would — because
  `pipeline/assembler.py:31` literally uses
  `GAP_THRESHOLD_SECONDS = 1.25` as the same-speaker merge gap when
  re-assembling chunk output.

**Why merged Q/A blocks?** Because `assembler.merge_utterances`
(`pipeline/assembler.py:162`) merges adjacent same-speaker utterances
with gap ≤ 1.25 s. When an attorney pauses ≤ 1.25 s between two
questions, those questions become one utterance regardless of
Deepgram's original split.

**Why combined attorney/witness turns?** That should not happen
through this path — both merge functions guard on
`current.speaker != next.speaker`. If turns are actually being
combined across speakers, the cause is either:
1. Deepgram diarization assigning the same speaker number to two
   different people in a chunk (a diarization issue, not a merge
   issue), OR
2. Cross-chunk speaker remapping (`_build_speaker_remap` at
   `pipeline/assembler.py:608`) collapsing distinct speakers when their
   numeric IDs collide across chunks.

Verifying which of those is responsible is **out of scope** for this
audit but is the right next investigation if the observation
reproduces.

**Why ~340 utterances on 83 minutes?** Median 14.6-second utterances
on average — consistent with a 1.25-s same-speaker merge gap clustering
a Q-A-Q-A sequence into ~3-utterance chunks for sustained back-and-forth
exchanges.

---

## Section 7 — Recommendations (NO IMPLEMENTATION)

### 1. The Deepgram-config story is fine; the merge-config story is not

`utt_split=0.8` reaches Deepgram cleanly. There is no need to relocate,
centralize, or environment-variable-ize Deepgram options — the
existing `REQUIRED_DEEPGRAM_FLAGS` pattern already prevents drift.

The **local merge constants** in `pipeline/transcriber.py` and
`pipeline/assembler.py` are where centralization would pay off. They
are currently:

- spread across two modules
- named with two different constant names for nearly the same concept
- not surfaced anywhere a user (or even a developer reading
  `_transcribe_direct`) can see at a glance

A future centralization could expose a single
`UTTERANCE_MERGE_PROFILE = {"in_chunk_gap": 0.6, "cross_chunk_gap": 1.25, "min_words": 2}`
in `core/config.py` or a new `pipeline/merge_config.py`. **Do not
implement now** — first decide whether the observed merge aggressiveness
is desired or excessive.

### 2. Adaptive utterance tuning is premature

Before adding adaptive logic, run a baseline experiment:

- Re-run Etminan with `GAP_THRESHOLD_SECONDS` temporarily lowered to
  `0.6` in `pipeline/assembler.py:31` and compare utterance count +
  Q/A separation against the current run.
- If the lower value materially improves Q/A separation without
  introducing speaker-flip glitches, the fix is a constant change,
  not adaptive tuning.

Adaptive logic adds state, branching, and tests. The current data
suggests the gap is simply too lenient for deposition material, where
short attorney follow-ups and back-and-forth Q/A are the norm.

### 3. Runtime logging — already partial, could be tightened

`pipeline/transcriber.py:607-608` already logs the params dict:

```python
logger.info("Deepgram direct HTTP call chunk=%s params=%s", chunk_name, params)
print(REQUEST_DEBUG_PREFIX, params)
```

This means every chunk request's flags **are** captured in
`logs/pipeline.log` and stdout. The information is already there; what
is missing is post-merge accounting. A worthwhile addition (not
implemented here) would be a single log line per chunk after
`merge_utterances` runs:

```
[TRANSCRIBE] chunk=N raw_utterances=X merged=Y gap_threshold=0.6s
```

…and a single log line per case after `reassemble_chunks`:

```
[ASSEMBLE] chunks=N raw_utterances=X merged=Y gap_threshold=1.25s
```

This would make the two-stage compression visible without needing to
diff `raw_utterances` vs `utterances` in the saved JSON.

### 4. Persisted request payload — already present, useful as-is

The saved `raw_deepgram.json` already includes `model`,
`deepgram_keyterms_used`, `chunk_count`, and `audio_tier`. The set of
Deepgram flags actually sent is **not** persisted, because the source
code itself is the authority (and they are static). For audit
robustness, persisting the final `params` dict alongside
`deepgram_keyterms_used` would let a future debugger reconstruct exactly
what the request looked like without re-reading the source. This is a
small addition and would not change behavior; recording the
recommendation only.

---

## Audit Footnotes

- **Verified at:** 2026-05-13.
- **Working tree state:** clean (no production changes during audit).
- **Verification evidence:** Etminan `raw_deepgram.json`
  (`raw_utterances=1107`, `utterances=340`, `chunk_count=9`,
  `model=nova-3`, `audio_tier=ENHANCED`).
- **Sources of truth cited:** `pipeline/transcriber.py:87-95, 552-602,
  271-391, 432-461`; `pipeline/assembler.py:31-34, 162-219, 513-663`;
  `core/job_runner.py:113-303`.
- **Out-of-scope for this audit (recorded as follow-ups):**
  1. Why paragraphs do not flow from Deepgram response into
     `block_builder` (the saved JSON lacks a top-level `paragraphs`
     field).
  2. Whether cross-chunk speaker remapping
     (`_build_speaker_remap` at `pipeline/assembler.py:608`) ever
     collapses distinct speakers.
  3. Whether `MERGE_GAP_THRESHOLD_SECONDS = 0.6` and
     `GAP_THRESHOLD_SECONDS = 1.25` are the right values for
     deposition material.
