# Step B.1 — Word-Object Carry Through qa_fixer and speaker_mapper

Half two of Step B from `verbatim_punctuation_plan_2026-05-12.md`.
B.0 added the optional `TranscriptWord` + `TranscriptBlock.words` data
model and populated it at the block_builder / classifier / corrections
layer. B.1 threads `words` through the eleven reconstruction sites in
`qa_fixer.py` and `speaker_mapper.py`.

## Site categorization

Eleven `TranscriptBlock(...)` reconstruction sites were touched. Each
falls into one of three categories with a distinct policy.

### qa_fixer.py (9 sites)

| Site context | Category | Policy |
|---|---|---|
| `enforce_qa_sequence` — answer re-type | normalize | `words=block.words` (same list object) |
| `enforce_qa_sequence` — question re-type | normalize | `words=block.words` |
| `enforce_qa_sequence` — back-merge into prior question | merge | `words=_concat_words(previous.words, normalized.words)` |
| `enforce_structure` — directive branch | normalize | `words=block.words` |
| `enforce_structure` — same-speaker Q merge (pass 1) | merge | `words=_concat_words(pending_question.words, block.words)` |
| `enforce_structure` — question branch | normalize | `words=block.words` |
| `enforce_structure` — answer branch | normalize | `words=block.words` |
| `enforce_structure` — fallthrough (other types) | normalize | `words=block.words` |
| `enforce_structure` — same-speaker Q merge (pass 2) | merge | `words=_concat_words(pending_question.words, block.words)` |

### speaker_mapper.py (2 sites)

| Site context | Category | Policy |
|---|---|---|
| `smooth_speaker_sequence` — A→B→A reassignment | speaker reassign | `words=_propagate_speaker_to_words(current.words, previous.speaker)` |
| `normalize_speakers` — speaker label normalization | speaker reassign | `words=_propagate_speaker_to_words(block.words, normalized_speaker)` |

## Policy contracts

### Merge — `_concat_words(a, b)` (qa_fixer module helper)

When two blocks `a` and `b` are combined into one merged block:

- If both `a.words` and `b.words` are non-None → `merged.words = a.words + b.words` (a new list; inputs are not mutated).
- If either is None → `merged.words = None`. Honest "couldn't preserve full word coverage" signal rather than a partial array that would mislead Step C/D.

The joined word text will not byte-equal the merged block's text after corrections have inserted punctuation; that's expected. Step C/D reconciliation aligns what it can and renders unmatched cleanup tokens unmarked.

### Split — character-offset accumulator (policy only; no current sites)

No qa_fixer site currently splits a block into two children. If a future site does, the policy is:

- Walk `block.words` in order. After consuming `w_0..w_i`, the accumulator equals `sum(len(w.text) for w in w_0..w_i) + i` (one joining space between consumed words, matching `" ".join(w.text for w in words)`).
- If the accumulator equals the split character offset `k` exactly → partition: first child gets `w_0..w_i`, second child gets the rest.
- If no exact boundary exists (cleanup inserted whitespace, punctuation, or otherwise edited the joined form) → both children get `words=None`. Symmetric honesty; neither child gets a partial / fabricated alignment.

### Speaker reassignment — `_propagate_speaker_to_words(words, new_speaker)` (speaker_mapper module helper)

When `block.speaker` is reassigned, the per-word `speaker` field is propagated so downstream consumers see the post-correction speaker, not Deepgram's pre-correction guess. Uses `dataclasses.replace(w, speaker=new_speaker)` for each word — matches the rebuild-not-mutate convention used elsewhere in spec_engine. Original `TranscriptWord` instances are not mutated.

If `block.words is None`, the helper returns `None`.

## Backward compatibility

- Existing `TranscriptBlock(...)` construction sites in tests and elsewhere that do not pass `words` remain valid (default `None`).
- Normalize sites preserve `words` list identity — when no semantic change to the word array applies, the new block's `.words is old.words` evaluates True.
- Correction output text is byte-identical to pre-B.1.

## Authority

- `docs/plans/verbatim_punctuation_plan_2026-05-12.md`
- `docs/plans/step_b0_word_carry_2026-05-12.md`
