# Phase A Canonical Raw Fixture (Etminan)

Forensic-architecture baseline for the immutable raw-response
persistence layer (`pipeline/raw_store.py`). Captured from a real
end-to-end Deepgram + Anthropic run on **2026-05-13 13:47:06** against
the Etminan deposition audio. Consumed by
`tests/transcript_integrity/test_word_object_integrity.py`.

## What this fixture validates

The Phase A persistence *architecture*:

- raw-response shape and provenance fields
- per-chunk word/utterance counts at the source (pre-mutation)
- word-object field integrity (`word`, `start`, `end`, `confidence`, `speaker`)
- utterance-level integrity
- the documented overlap-dedup bound between native and assembled counts

It is **not** the Phase B baseline. Phase B (word-object regression
behavior under conversational complexity) is captured separately at
`tests/fixtures/canonical_raw_fixture/` against the Heath Thomas
5-minute clip. The two fixtures serve different purposes and are not
interchangeable.

## Files

| File | Provenance |
|------|------------|
| `raw_dg_response.json` | The full immutable raw-response file from the live run. **Schema v1** — predates the v2 bump that added `keyterms_sent` and tightened request-params capture. |
| `raw_deepgram.txt` | The plain-text transcript Deepgram returned, captured alongside the raw response. |
| `metadata.json` | **Operator-curated.** Hand-built to expose the counts and request-params snapshot the integrity test asserts against. Its keys (`native_word_total`, `canonical_assembled_words`, `request_params_snapshot`) do not match either the v1 or v2 on-disk save shape. Treat as a *companion summary file* of the run, not as something produced by `raw_store.py`. |

## Schema-version note

This fixture was captured against `pipeline/raw_store.SCHEMA_VERSION = 1`.
The current production schema is `2` (adds top-level `keyterms_sent`,
tightens length validation). Do **not** regenerate this fixture using the
v2 raw_store — that would change its meaning. If a Phase A re-validation
is required at v2, capture into a sibling directory rather than
overwriting this one.

## Do not regenerate without cause

This fixture is the historical artifact of the Phase A acceptance run.
Regenerating it destroys the architectural evidence trail. Legitimate
reasons to regenerate would be: a Deepgram model change that
invalidates the comparison, a deliberate schema migration, or an
operator-driven re-validation. Any regeneration must be a separate
commit with a justification in the message.
