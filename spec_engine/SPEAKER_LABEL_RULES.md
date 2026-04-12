# Speaker Label Corrections — Depo-Pro Transcribe

## Why the pipeline cannot fully fix speaker label errors automatically

The deterministic corrections engine in
[corrections.py](./corrections.py)
works on the text inside transcript blocks. It does not decide who is
speaking. Speaker identity comes from diarization and the verified speaker map.

That means:
- phrase corrections belong in `corrections.py`
- Q/A and speaker-role recovery belong in `classifier.py` and `qa_fixer.py`
- objection speaker resolution belongs in `objections.py`

When diarization is wrong, the pipeline may still correct the words but attach
them to the wrong speaker unless the speaker map and the recovery heuristics
catch it.

## What to do when speaker labels are scrambled

The most reliable fix is to verify the speaker map before final processing.

In the application:
1. Load the case and review the speaker labels.
2. Map each numeric speaker to the real participant.
3. Ensure `speaker_map_verified` is true before final correction/export.
4. Then run the deterministic correction pipeline.

## Known diarization failure patterns

These patterns are common when Zoom audio overlaps, echoes, or collapses
multiple microphones into one diarized stream:

| Deepgram output | What it may actually be |
|---|---|
| `DR. DAVIS` | `MR. DAVIS` |
| `MR. CICCONE` on defense questions | `MR. DAVIS` |
| `THE REPORTER` for witness testimony | `THE WITNESS` / deponent |

## Where to edit what

- If the problem is a wrong word or phrase: edit `corrections.py`
- If the problem is Q/A reconstruction: edit `qa_fixer.py`
- If the problem is block type or speaker attribution: edit `classifier.py`
- If the problem is objection extraction/speaker selection: edit `objections.py`

## Why `objections.py` stays separate

`objections.py` is not just a pattern list. It also resolves the objection
speaker from `JobConfig`, `speaker_map`, and counsel metadata. That is why it
remains separate from `corrections.py` in the safe consolidation path.
