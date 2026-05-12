# Step B.0 — Word-Object Metadata Carry

Half one of Step B from `verbatim_punctuation_plan_2026-05-12.md`.
B.0 carries Deepgram word-level metadata through the spec_engine data
model. B.1 (qa_fixer merge/split + speaker_mapper propagation) follows
in a separate commit.

## Scope

Files modified:

- `spec_engine/models.py` — added `TranscriptWord`, extended
  `TranscriptBlock` with `words: list[TranscriptWord] | None = None`.
- `spec_engine/block_builder.py` — populates `words` in each returned
  block dict (paragraph path partitions `alt["words"]` by paragraph
  time range; utterance fallback copies `utterance["words"]` directly).
- `spec_engine/classifier.py` — `_convert_word_dicts` converts raw word
  dicts to `TranscriptWord` instances; `classify_blocks` attaches them
  to each `TranscriptBlock`.
- `spec_engine/corrections.py` — `apply_corrections` reconstruction
  carries `words=block.words` through unchanged.

New file:

- `spec_engine/tests/test_word_carry.py` — 22 tests covering backward
  compatibility, `TranscriptWord` shape, paragraph populator,
  utterance populator, classifier conversion (including malformed
  inputs), and `apply_corrections` pass-through.

## Out of scope (B.1)

- `spec_engine/qa_fixer.py` — merge-concatenate, split-partition-or-None
- `spec_engine/speaker_mapper.py` — per-word speaker propagation

## Contracts

### TranscriptWord

```python
@dataclass(slots=True)
class TranscriptWord:
    text: str
    start: float
    end: float
    confidence: float
    speaker: str | int | None = None
    punctuated_word: str | None = None
```

Field shapes follow the documented Deepgram Nova-3 word object.
`punctuated_word` is populated by Deepgram when `smart_format=True`.

### TranscriptBlock backward compatibility

The 5-arg signature `TranscriptBlock(speaker, text, type, source_type,
examiner)` continues to work unchanged. `words` defaults to `None`.
The 14 existing construction sites in `qa_fixer`, `speaker_mapper`,
`corrections`, `emitter`, and tests remain valid without modification.

### Populator semantics

- **Paragraph path:** a word `w` belongs to paragraph `p` when
  `p["start"] <= w["start"]` and `w["end"] <= p["end"]`. When
  `alt["words"]` is empty/missing or the paragraph lacks `start`/`end`,
  the block's `words` field is `None`.
- **Utterance fallback path:** `utterance["words"]` is copied directly.
  Missing or empty → `None`.

### Classifier conversion

`_convert_word_dicts` is all-or-nothing. Any malformed word dict
(missing `word`/`start`/`end` keys, wrong types) causes the entire
`words` list for that block to be `None`. Step C/D treats `None` as
"no carried words, render plain."

### Corrections pass-through

`apply_corrections` does not alter word array contents. The reconstructed
block carries `words=block.words` through unchanged.

## Anchor corrections from the original B.0 draft

Two FIND anchors in the initial B.0 prompt did not match the live
files; both were corrected before execution:

1. `models.py` docstring is `"""Shared data structures for
   deterministic transcript enforcement."""`, not what the draft
   assumed. The B.0 commit preserves this docstring unchanged.
2. `corrections.py::apply_corrections` constructor uses
   `speaker=str(block.speaker or "").strip()` and a two-line nested
   `text=apply_morsons_rules(apply_proper_noun_corrections(...))`
   expression. The `words=block.words` addition is appended as the new
   last kwarg, preserving every other argument.

## Authority

- `docs/plans/verbatim_punctuation_plan_2026-05-12.md`
- Deepgram Nova-3 word object schema (documented; no real payload
  exists in this repo to capture).
