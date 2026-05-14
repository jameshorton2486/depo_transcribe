# Word Object Validation — Phase A real-run

**Case:** `etminan_mohammad`
**Run:** 2026-05-13 13:47:06

This document examines word-level integrity between the new immutable raw store and the existing canonical post-mutation outputs.

---

## Native word object shape (per-chunk, as Deepgram returned them)

Sample (first word of chunk 0):

```json
{
  "word": "good",
  "punctuated_word": "Good",
  "start": 0.05,
  "end": 0.34,
  "confidence": 0.99,
  "speaker": 0,
  "type": "word"
}
```

Required fields per the plan's word-object contract:

| Field | Present | Notes |
|---|:---:|---|
| `word` | ✅ | Deepgram-native (lowercase, no punctuation) |
| `punctuated_word` | ✅ | smart_format-cased |
| `start` | ✅ | seconds within the chunk |
| `end` | ✅ | seconds within the chunk |
| `confidence` | ✅ | 0.0–1.0 |
| `speaker` | ✅ | integer (Deepgram diarization output) |
| `type` | ✅ | `"word"` |

## Word-count integrity across the pipeline

| Stage | Where | Count |
|---|---|---:|
| Native Deepgram (pre-overlap-dedup) | Sum of `chunks[i].deepgram_response.results.channels[0].alternatives[0].words` from the immutable raw | **12,212** |
| After cross-chunk overlap dedup | `raw_deepgram.json["words"]` | 11,795 |
| Loss | — | **417 (3.4 %)** |

The 417-word delta is the cross-chunk overlap dedup at `pipeline/assembler.py:583-595`. Expected magnitude on this case (9 chunks × 20 s overlap × ~2.5 words/s ≈ 360-450) confirms the dedup is operating within the documented behavior.

## Per-word integrity (timestamp + confidence + speaker preservation)

Direct field-by-field comparison of the first 10 words in chunk 0 between the immutable raw and `raw_deepgram.json["chunks"][0]`:

| Word | start | end | confidence | speaker | Identical? |
|---|---:|---:|---:|---:|:---:|
| good | 0.05 | 0.34 | 0.99 | 0 | ✅ |
| afternoon | 0.34 | 0.84 | 0.99 | 0 | ✅ |
| we | … | … | … | … | (spot-checked; identical) |
| … | … | … | … | … | ✅ |

The `chunks` field inside `raw_deepgram.json` is byte-identical to the immutable raw's `chunks[i].deepgram_response`. Where word identity diverges (i.e. in the canonical's top-level `words` array) is exactly at the documented mutation points and nowhere else.

## Confidence value preservation

Sampled across 50 random words from chunk 0:

- 100 % of `confidence` values in `raw_deepgram.json["chunks"][0]` equal the immutable raw's chunk-0 confidence values (Python `==` on the float).
- No rounding, no normalization, no thresholding.

The `low_confidence: bool` annotation added by `transcriber._annotate_confidence` is a SEPARATE derived field on the utterance dict and does NOT modify the per-word `confidence` numeric value.

## Timestamp continuity

Native chunk timestamps are relative to the chunk start. After assembly, the chunk offsets are added in `reassemble_chunks` (`pipeline/assembler.py`) to produce absolute timestamps. The immutable raw preserves the chunk-relative values; the canonical's `words` array has them adjusted to absolute.

Spot check: word at the boundary between chunk 0 and chunk 1.

- Immutable raw chunk 1 word 0: `start=0.05` (chunk-relative)
- Canonical raw_deepgram.json word at the same boundary: `start=600.05` (absolute, 600 s = chunk-1 offset)

The adjustment is the documented chunk-offset addition. No corruption.

## Speaker ID preservation in the immutable raw

In the immutable raw:
- Chunk 0 speaker IDs: {0, 1, 2}
- Chunk 1 speaker IDs: {0, 1, 2, 3}
- … each chunk has its own native Deepgram speaker numbering ...

These integers are the Deepgram-side diarization output, **not** remapped across chunks. The cross-chunk speaker remap (`pipeline/assembler.py::_build_speaker_remap`) operates AFTER the raw store save. Therefore the native speaker IDs are preserved in the immutable raw and the remap can be inspected against them as a separate audit step.

## Required word-object integrity assertions (for tests/transcript_integrity/test_word_object_integrity.py)

Each of the following assertions has a corresponding fixture lookup point. The Phase-B test file uses these as its core contract.

1. **No timing corruption.** `start < end` for every word in every chunk.
2. **No dropped words at the source.** Sum of `len(chunks[i].deepgram_response.results.channels[0].alternatives[0].words)` equals the Deepgram-native word total.
3. **No confidence loss.** Every word has a numeric `confidence` in `[0.0, 1.0]`.
4. **No speaker corruption at the source.** Every word's `speaker` is an integer ≥ 0.
5. **Raw is immutable.** The file mode is `0o444`; attempting to open for writing without `chmod` first raises.

The fixture used by `test_word_object_integrity.py` is the canonical raw fixture captured at `tests/fixtures/canonical_raw_fixture/` (created in the next step of this validation cycle).
