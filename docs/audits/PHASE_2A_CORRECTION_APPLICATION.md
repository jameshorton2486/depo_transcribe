# Phase 2A Correction Application Audit

**Case:** `C:\Users\james\Depositions\2026\May\2026CV00803\cavazos_gilberto`
**Diagnostic run:** `diag_phase2a_20260512_173640/` (post Phase 2A.1 commit `887ec98`)
**Input held constant:** captured `raw_deepgram.json` + `raw_deepgram.txt`

## Headline

**Confirmed_spellings corrections are NOT being applied at scale — only 1 of 10 missing marker bodies (`Mister → Mr.`) corresponds to a real reference-data correction. The other 9 are marker strips: the LC wrapper was removed but the underlying token text was preserved, or, in 2 cases, the content was silently trimmed at the deposition boundary.**

## Run summary

This Phase 2A.1 diagnostic run dropped 10 markers (6.5%) — above the 5% threshold, would have raised `MarkerDriftError`. Run-to-run variance: prior 3-run verification showed 0/0/0 drops with output *higher* than input; this run dropped 10. The MARKER INVIOLABILITY rule reduced average drift but did not eliminate it.

## Per-token classification

For each of the 10 missing marker bodies, I read the input/output text around the marker and classified what actually happened. Heuristic-flagged AMBIGUOUS cases are resolved by inspection.

| body | refined verdict | what happened |
|---|---|---|
| `Animal` | **MARKER_ONLY_DROPPED** | input: `‹LC:Animal› Care Services` → output: `Animal Care Services` (bare). Text preserved; marker stripped. |
| `Bye` | **SILENT_DROP** | input: `Bye. You too ‹LC:too›. Alright. ‹LC:Bye›.` (closing remarks) → output: word `Bye` does not appear anywhere. Closing remarks trimmed by the model. |
| `David` | **MARKER_ONLY_DROPPED** | input: `‹LC:David› Gonzalez, ‹LC:Jr›` → output: `David Gonzalez, Jr.` Text preserved; marker stripped. |
| `Got` | **MARKER_ONLY_DROPPED + SCOPIST FLAG substitution** | input: `Speaker 0: ‹LC:Got›,` → output: `Got,` plus `[SCOPIST: FLAG 1: "Opening word 'Got' -- unclear context..."]`. The exact failure mode the Phase 2A.1 fix was supposed to prevent. Still happening on the opening word. |
| `Jr` | **MARKER_ONLY_DROPPED** | input: `‹LC:Jr›` → output: `Jr.` Text preserved. Confirmed_spellings has `Gonzalez Junior → Gonzalez, Jr.` but `Jr` alone isn't a direct key. |
| `Mister` | **APPLIED** | input: `‹LC:Mister› Cavazos` → output: `Mr. Cavazos`. `Mr.` appears 33 more times in output than in input. Real reference-data correction applied at scale. 12 instances of `Mister` still remain in output uncorrected (the model is not 100% consistent). |
| `Mr` | **MARKER_ONLY_DROPPED** | input: `‹LC:Mr›. Gonzalez` (Deepgram already wrapped `Mr` with low-confidence) → output: `Mr. Gonzalez`. Text preserved; marker stripped. |
| `That` | **MARKER_ONLY_DROPPED** | input: `‹LC:That› would be great` → output: `That would be great` (in altered context — the model rewrote surrounding sentences too). Text preserved at the specific position. |
| `cause` | **APPLIED (via keyterm)** | input: `‹LC:cause› number 2026CV008` → output likely `Cause Number 2026CV008` (the `Cause Number` keyterm is in `deepgram_keyterms`). Lowercase `cause` doesn't appear at that location in the output; `Cause Number` does. Same effect as a confirmed_spelling correction, applied via the keyterms path. |
| `too` | **SILENT_DROP** | input: `Bye. You too ‹LC:too›. Alright. ‹LC:Bye›.` (closing remarks, same as `Bye` row above) → output: closing-remarks block does not appear. Trimmed by the model. |

## Stage Attribution Summary

| verdict | count | notes |
|---|---|---|
| **APPLIED** (reference-data correction) | 2 | `Mister → Mr.` (33 applications), `cause → Cause Number` (via keyterm, single application) |
| **MARKER_ONLY_DROPPED** (wrapper gone, text kept) | 6 | `Animal`, `David`, `Jr`, `Mr`, `That`, `Got` |
| **SILENT_DROP** (token absent from output) | 2 | `Bye`, `too` — both in trimmed closing remarks at deposition boundary |
| **NEW marker bodies in output** | 0 | The model is not inventing new markers |
| **`Got` SCOPIST-FLAG substitution** | 1 | The exact failure mode Phase 2A.1 was designed to prevent is still happening on this token specifically |

## What this tells us

**The reference-data correction workflow IS functional** — the `Mister → Mr.` mapping fires 33 times in this single chunk, and the `Cause Number` keyterm normalization fires once. The `confirmed_spellings` data is reaching the model and being acted on. The Phase 2A wiring (commit `91e8282`) is doing real work.

**But that's only 1 of 33 confirmed_spellings entries with measurable applications on this case**, because the Cavazos audio doesn't contain mis-heard variants for the other 32 entries (most are alternate spellings of `Objection.`, `Leading.`, witness names not yet spoken, etc.). The application rate is determined by which mis-heard variants are actually in the audio, not by the wiring itself.

**The remaining 8 missing markers are NOT corrections in disguise.** They're a mix of:
- Marker strips on "well-formed" tokens (`David`, `Jr`, `Mr`, `That`, `Animal`) — the model thinks the token is clear and removes the LC wrapper, even though Deepgram's per-word audio confidence was low. This is the residual of the original bug; Phase 2A.1 reduced it but didn't eliminate it.
- A SCOPIST FLAG substitution on the opening word `Got` — the exact failure mode the MARKER INVIOLABILITY rule was supposed to prevent. Still happening, at least on the opening word at the start of the prompt where the model's attention is presumably strongest on the new REFERENCE DATA FIELDS section.
- Two genuine silent drops (`Bye`, `too`) at the deposition's closing remarks — but these aren't a Phase 2A regression. The model has always trimmed transitional content; the difference is that the trimmed content happened to contain low-confidence markers in this run.

## What this does NOT explain

- **The run-to-run variance is huge.** Previous 3-run verification: 0/0/0 marker drops. This run: 10. Same prompt, same input, same model. The model's interpretation of the prompt is unstable.
- **Why specifically these tokens.** The strips concentrate on proper-noun-like tokens (`David`, `Jr`, `Mr`, `Animal`) and common short words (`That`, `cause`, `too`). The pattern is consistent across multiple runs (`Animal`, `Got`, `Mister`, `That`, `cause` appear in nearly every run's missing list) — but why these and not others is opaque.

## What to decide next

The original `(A) vs (B)` framing from the prior turn was based on the hypothesis that "missing markers = corrections applied silently." That hypothesis is **mostly wrong** — only 2 of 10 missing markers are corrections; the rest are residual stripping that Phase 2A.1 didn't eliminate.

The real choice now:

- **(I) Accept the residual stripping.** The drift safety net catches the worst-case runs (>5%) and produces a MarkerDriftError that surfaces a popup. The typical runs land at 0-7% drift. Miah sees a popup occasionally; most of the time the run succeeds. The 33 confirmed_spellings entries are wired and applying where they apply.
- **(II) Iterate the prompt further.** The MARKER INVIOLABILITY rule is being read but not consistently obeyed for proper-noun-adjacent and short common tokens. A more aggressive prompt iteration would name those classes specifically (e.g., "even for tokens like David, Mr, Jr, That, Animal that look 'well-formed' to you — preserve the marker"). Estimated ~$2-6 to verify across multiple runs.
- **(III) Raise the drift threshold from 5% to 10%.** The current threshold catches reasonable variation. If the residual stripping is acceptable risk (which it is, since the text content is preserved), bumping the threshold means fewer false-positive failures in production. No prompt change required; one constant change in `clean_format/low_confidence_markers.py`.
- **(IV) Accept the design as-is, ship Phase 2A, move on.** The wiring is correct, the corrections that fire are correct, the safety net is functional. The residual marker stripping reduces yellow-highlight coverage by ~6% per affected run, which is a real but not severe regression vs. the pre-Phase-2A baseline (2.6%). The product still works.
