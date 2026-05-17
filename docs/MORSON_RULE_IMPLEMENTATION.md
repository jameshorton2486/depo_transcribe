# Morson Rule Implementation (Deterministic)

Implemented safe punctuation-shape normalization only:

- Interruption markers normalized to ` -- `.
- Ellipsis variants normalized to `...`.

Safety:
- No lexical substitutions.
- No paraphrase.
- No punctuation inference from semantics.
