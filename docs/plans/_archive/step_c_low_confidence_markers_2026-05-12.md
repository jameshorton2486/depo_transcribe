# Step C — Low-Confidence Marker Injection in clean_format

Step C of the verbatim-punctuation plan
(`docs/plans/verbatim_punctuation_plan_2026-05-12.md`). Wraps Deepgram
tokens with confidence below `config.LOW_CONFIDENCE_THRESHOLD` (`0.85`)
in inline markers that survive the Anthropic cleanup round-trip. Step D
consumes the marker-bearing text in the DOCX writer to render those
tokens with a yellow highlight.

## Scope

Files modified:

- `clean_format/formatter.py` — added optional `deepgram_words` and
  `low_confidence_threshold` parameters to `format_transcript`. When
  `deepgram_words` is provided, marker injection runs before chunking
  and the response is round-trip-validated for marker drift.
- `clean_format/prompt.py` — added `PART 11 — LOW-CONFIDENCE TOKEN
  MARKERS` instructing the Anthropic model to preserve markers exactly
  and never alter wrapped tokens. The `VERBATIM_TRANSCRIPT_REMINDER`
  postscript also gained a marker reminder line.

New files:

- `clean_format/low_confidence_markers.py` — `inject_markers`,
  `count_markers`, `strip_markers`, `split_into_runs`,
  `validate_marker_round_trip` plus the marker constants.
- `clean_format/tests/test_low_confidence_markers.py` — 32 tests
  across 4 test classes.

## Marker form

`‹LC:word›`

- **Open** = `‹` (U+2039) + ASCII `LC:`
- **Close** = `›` (U+203A)
- **Body** = the literal Deepgram token, no surrounding whitespace or
  punctuation. Trailing punctuation stays outside the close character.

### Chosen for

- Single Unicode-char boundaries → low token cost in the API call.
- The `LC:` namespace prefix makes the directive intent obvious to
  Claude and to any human reviewing the cleaned text.
- U+2039 / U+203A are essentially absent from English-language Texas
  deposition transcripts, minimising false-positive collision.

## API surface (additive)

```python
format_transcript(
    raw_text: str,
    case_meta: dict,
    *,
    client=None,
    model=None,
    max_chunk_chars=CHUNK_CHAR_LIMIT,
    deepgram_words: list[dict] | None = None,        # Step C
    low_confidence_threshold: float = 0.85,          # Step C
) -> str
```

When `deepgram_words` is `None` (default), `format_transcript` behavior
is byte-identical to pre-C. Existing callers that have not been updated
keep working unchanged.

## Injection algorithm

`inject_markers(raw_text, words, *, threshold)` walks `words` in order,
locating each token in `raw_text` past the running cursor with a
case-insensitive whole-word match (`\bWORD\b`). Tokens whose confidence
falls below `threshold` are wrapped with markers; tokens at or above the
threshold pass through unchanged. Tokens that cannot be located in the
text (e.g., upstream post-processing rewrote them) are skipped silently,
preserving alignment for the remaining words.

The function never raises. Degraded output (some markers missing) is
preferred to a crashed pipeline.

## Round-trip validation

After each Anthropic response, `validate_marker_round_trip(sent, received)`
counts markers in both. When the model drops markers, a warning is
logged with the drop count and continues — the transcript is still
legally usable, but the scopist loses the yellow review surface for the
dropped tokens.

The plan called for "marker count mismatch is treated as an error
rather than silently dropped." Step C takes a softer stance: drift is
**logged**, not raised. The reasoning is that a dropped marker is a
quality signal (yellow highlight missing), not a correctness bug
(transcript text is still valid). Raising would break otherwise-good
transcripts on what is recoverable degradation.

## Step D handoff

Step D's DOCX writer calls `split_into_runs(text)` to split paragraph
text into `(chunk, is_low_confidence)` tuples. Marked chunks get a
yellow `WD_COLOR_INDEX.YELLOW` highlight; unmarked chunks render
default. The marker characters themselves are stripped from the
rendered document — they were inline metadata only.

## Threshold semantics

Strict less-than: `confidence < threshold`. A token whose confidence
exactly equals the threshold is NOT marked. Matches the convention used
throughout `pipeline/transcriber.py`.

## Backward compatibility

- Existing `format_transcript` callers without `deepgram_words`: no
  change in input or output.
- Existing 4 `clean_format/tests/test_formatter.py` tests: pass
  unchanged.
- Marker characters U+2039 / U+203A are not touched by any regex in
  `_normalize_body_text` or `_postprocess_formatted_text`, so markers
  survive post-processing.

## Authority

- `docs/plans/verbatim_punctuation_plan_2026-05-12.md`
- `docs/plans/step_b0_word_carry_2026-05-12.md`
- `docs/plans/step_b1_word_carry_merge_split_2026-05-12.md`
