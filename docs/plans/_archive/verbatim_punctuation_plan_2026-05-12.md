# Verbatim Transcript Plan — Punctuation and Low-Confidence Highlighting

| Field | Value |
|---|---|
| Status | Active. Draft 2026-05-12. |
| Authority | `CLAUDE.md` > `AGENTS.md` > this plan. |
| Style source | Morson's English Guide for Court Reporters, Second Edition. |
| Replaces | The pre-clean-format-migration planning docs that were removed from the repo and now exist only in stale Claude Project knowledge: `IMPLEMENTATION_PROMPT.md`, `DEPO_PRO_MASTER_PLAN.md`, `step_2a_tighten_qa_sequence_prompt.md`, `step_2c_ai_splitter_prompt.md`, `run_corrections_button_prompt.md`. |
| Sequencing | Four steps (A–D). One step per commit. Acceptance check between steps. No layer touched twice in one step. |

---

## Purpose

Lock down the deterministic transcript-handling rules across the two correction paths in this repo so they agree on:

1. **Speech preservation** — verbatim, no exceptions.
2. **Punctuation defaulting** — additive and conservative.
3. **Em-dash normalization** — interruption markers are preserved and normalized to ` -- `, never destroyed.
4. **Number style** — Morson's Rule 170 (1–10 spelled out when isolated; identifiers and special references stay as digits).
5. **Low-confidence visual flagging** — words below the Deepgram confidence threshold render with `WD_COLOR_INDEX.YELLOW` highlight in the final DOCX.

Today, the primary path (`clean_format/`) is governed by a strict-verbatim prompt and the manual utility path (`spec_engine/`) is not. This plan converges them on a single posture: **speech is sacred, punctuation is scribal, the scopist is the final authority on `?` vs `.` and on inflection-driven calls.**

---

## The Five Rules

### Rule 1 — Speech is sacred

Never remove, replace, paraphrase, or reorder any spoken word. Includes:

- All filler words: `uh`, `um`, `like`, `you know`, `I mean`.
- All stutters and repetitions: `"the the the"`, `"I -- I think"`.
- All false starts and self-corrections.
- All hedges and pauses.

The only justification for changing speech text is verification against the source audio.

### Rule 2 — Punctuation is additive and editorial

The deterministic pass may add or normalize: commas, periods, capitalization, ellipses, proper-noun spellings from the NOD.

When inferring terminal punctuation, **default to `.`**. Never guess `?`. The scopist flips it after audio review.

Morson's gives no rule for inferring `?` from word order — the reporter is assumed to have heard the inflection.

### Rule 3 — Em-dashes are speech events; normalize but never destroy

Em-dashes (` -- `) are the textual representation of an interruption or trailing-off. They:

- Are **preserved** wherever they appear (Deepgram output, AI cleanup output, hand-edited input).
- Are **normalized** in form: Unicode `—` (U+2014) and `–` (U+2013) become ASCII ` -- ` (space, two hyphens, space) per Morson's Rule 85 Note: *"most court reporters prefer a space before and after the dash."*
- Are **added** only by one deterministic rule for Phase 1: if an utterance ends without `.!?` and the next utterance is a different speaker, append ` --` to the unfinished one. (Morson's Rules 87, 88.)

Same-speaker self-corrections (Rule 85), parenthetical asides (Rule 86), and interruption-with-verbal-stop (Rule 89) are **not** detected deterministically in Phase 1 — they need audio cadence or semantic inference. Those are deferred to scopist review.

### Rule 4 — Number style follows Morson's Rule 170

Spell out isolated standalone numbers **1 through 10** in narrative text.

Keep as digits when the number is any of:

- An identifier following one of these reference words within a 3-word window (case-insensitive):
  `Cause`, `Case`, `Exhibit`, `Volume`, `Vol.`, `Section`, `Sec.`, `Page`, `Pg.`, `Line`, `Number`, `No.`, `Bates`, `Bates No.`, `Document`, `Doc.`, `Item`, `Figure`, `Schedule`, `Paragraph`, `¶`, `Article`, `Rule`, `Request`, `Interrogatory`, `RFP`, `RFP No.`, `Deposition`, `Transcript`.
- Any value 11 or higher.
- A date, time, currency, percentage, address, phone number, mixed alphanumeric token, hyphenated identifier, docket/cause pattern, medical measurement, or citation.

Examples that **must remain untouched**:

```
DC-25-13430        2024-CI-19595      3:00          $500
5%                 12-gauge            7 millimeters Exhibit 4
Page 5 Line 12     Bates 000123       C4-C5         P-7
```

Authority: Morson's Rules 170, 172, 202, 217.

### Rule 5 — Low-confidence words get yellow highlight

Words whose Deepgram confidence falls below `config.LOW_CONFIDENCE_THRESHOLD` (currently `0.85`) render with `WD_COLOR_INDEX.YELLOW` highlight in the final DOCX so the scopist can spot them at a glance.

**Strategy:** option (a) — mark in the cleanup prompt.

The flow is:

1. Pre-cleanup: inject inline markers around low-confidence tokens (form to be defined in Step C).
2. Cleanup prompt is updated to instruct Claude to preserve marked tokens verbatim, no rewording, exact spelling and casing.
3. Post-cleanup: parse the markers back out, attach the highlight state to the output token stream.
4. DOCX writer renders marked runs with yellow highlight.

This gives deterministic traceability and stable review synchronization. Future colors are reserved (red = confirmed correction; green = reviewed/verified) but not implemented in Phase 1.

---

## Implementation sequence

Four steps. One per commit. Acceptance check between each.

| # | Step | Files | Layer | Risk | Behavior change? |
|---|---|---|---|---|---|
| A | Corrections cleanup | `spec_engine/corrections.py`, `spec_engine/tests/*` | `spec_engine` | Low | Yes — stops destroying interruptions, stops stripping fillers, stops auto-guessing `?`, narrows 1–12 to 1–10. |
| B | Word-object metadata carry | `spec_engine/models.py`, `spec_engine/block_builder.py`, `spec_engine/tests/*` | `spec_engine` | Very low | No — additive only. Existing consumers untouched. |
| C | Low-confidence marker injection | `clean_format/prompt.py`, `clean_format/formatter.py`, `clean_format/tests/*` | `clean_format` | Medium | Yes — primary path behavior. |
| D | Yellow-highlight DOCX rendering | `clean_format/docx_writer.py`, `clean_format/tests/*` | `clean_format` | Low | Yes — rendering only. |

No step touches more than one layer. No step depends on a layer-crossing change.

### Step A — Corrections cleanup

**Goal:** make `spec_engine/corrections.py` stop violating verbatim and stop being destructive of interruption markers.

**Changes:**

1. Remove the trailing-filler strip from `_fix_ending_punctuation` (the `re.sub` that deletes `uh`/`um`/`you know` from end of text).
2. Replace the question-mark heuristic in `_fix_ending_punctuation` with a period-only default. Drop reliance on `_QUESTION_STARTERS` for terminal punctuation. `_QUESTION_STARTERS` may stay defined; it is no longer referenced.
3. Delete `_fix_em_dashes` (the destructive ` -- ` → `  ` collapser).
4. Add `_normalize_em_dashes` that converts Unicode `—` (U+2014) and `–` (U+2013) and any ASCII `--` with inconsistent surrounding whitespace to canonical ` -- `. Never deletes; only normalizes.
5. Narrow `_SMALL_NUMBER_WORDS` from 1–12 to 1–10 per Morson's Rule 170.
6. Update `apply_morsons_rules` pipeline order accordingly.

**Existing tests that encode reversed behavior** (will fail by design):

- `spec_engine/tests/test_morsons_rules.py::test_question_detection` (asserts `?` auto-append).
- `spec_engine/tests/test_morsons_rules.py::test_em_dash_normalization` (asserts ` -- ` collapses to spaces).
- `spec_engine/tests/test_morsons_rules.py::test_interrogative_without_punctuation_gets_question_mark` (asserts `?` auto-append).
- `spec_engine/tests/test_corrections.py::test_apply_morsons_rules_handles_basic_legal_cleanup` (asserts `?` auto-append).

**Codex protocol:** make the code changes, add the new positive-assertion test file, run the suite, **stop and report** any pre-existing test that fails. James reviews each failure and explicitly authorizes the assertion updates in a follow-up turn (Step A.1).

**Success criteria for Step A:**

- The four code changes land.
- A new test file `spec_engine/tests/test_corrections_step_a.py` adds positive coverage for: filler preservation, period-only default, ` -- ` preservation, ` -- ` normalization from `—`/`–`, 11/12 left as digits, 1–10 still spelling out, end-with-`uh` preserved.
- The pre-existing failing tests are listed in the run report — not modified.
- All other tests pass at the pre-change count or higher.

### Step B — Word-object metadata carry

**Goal:** start carrying Deepgram word-level metadata (text, start, end, confidence, speaker) through the `spec_engine/` data model additively, without breaking any existing consumer.

**Changes:**

1. Introduce a `TranscriptWord` dataclass in `spec_engine/models.py` with `text: str`, `start: float`, `end: float`, `confidence: float`, `speaker: str | int | None`.
2. Extend `TranscriptBlock` with `words: list[TranscriptWord] | None = None` (default `None`, fully optional).
3. In `spec_engine/block_builder.py`, when a paragraph or utterance carries Deepgram words, populate `words` on the resulting block. When it doesn't, leave it `None`.

**Non-changes:**

- No existing consumer of `TranscriptBlock` is required to read `words`.
- The emitter, corrections, qa_fixer, classifier, speaker_mapper, and processor remain unchanged.
- Output of the spec_engine path remains byte-identical to pre-change.

**Success criteria for Step B:**

- All existing tests pass at the same count.
- New test: when block_builder receives a Deepgram alt with words, the resulting blocks carry word arrays whose joined text equals the block text (modulo whitespace).
- New test: when no words are present, blocks have `words=None` and downstream processing is unaffected.

### Step C — Low-confidence marker injection in clean_format

**Goal:** route low-confidence Deepgram tokens through Claude's cleanup pass with explicit preservation instructions and recoverable markers.

**Depends on:** Step B (word-object carry).

**Changes (detailed in Step C prompt):**

1. Pre-cleanup: walk the raw transcript text, find tokens whose Deepgram confidence is below `LOW_CONFIDENCE_THRESHOLD`, wrap them with inline markers. Marker form to be specified in the Step C prompt (candidates: `[[lc:word]]`, `‹word›`, custom Unicode pair — chosen to survive AI round-trip).
2. Update `clean_format/prompt.py` to explicitly instruct: marked tokens MUST be preserved exactly as spelled, with the marker boundaries intact; never reworded; never re-cased.
3. Post-cleanup: parse markers out of Claude's response; track which output tokens were marked.
4. Pass the marked-token set to `clean_format/docx_writer.py` alongside the cleaned text.

**Success criteria for Step C:**

- Round-trip test: a fixture with N marked tokens produces cleaned text with N marker pairs preserved at the corresponding tokens.
- Drift test: a token that Claude reworded (against instructions) is detected and logged; the marker count mismatch is treated as an error rather than silently dropped.
- All existing clean_format tests pass.

### Step D — Yellow-highlight DOCX rendering

**Goal:** render marked tokens with `WD_COLOR_INDEX.YELLOW` highlight in the final DOCX.

**Depends on:** Step C.

**Changes:**

1. Extend `clean_format/docx_writer.py`'s block-parsing logic to recognize marker-bracketed tokens.
2. Render each marked token as its own `run` within the surrounding paragraph, with `run.font.highlight_color = WD_COLOR_INDEX.YELLOW`.
3. Unmarked tokens render with default styling.

**Success criteria for Step D:**

- DOCX-output test: a fixture with marked tokens produces a DOCX where exactly the marked runs carry yellow highlight.
- Existing DOCX layout tests pass: tab stops, hanging indents, Q/A formatting unchanged.

---

## Out of scope (deferred or non-code)

- **Audio-verification UI** — click-a-word → seek VLC to its timestamp. Needs the data model from Step B but is its own UI feature; not in Phase 1.
- **Inline 1–10 narrative spell-out for body text** — Step A only narrows the existing sentence-initial conversion to 1–10. A separate later step adds inline digit-to-word conversion (with the identifier-context exception list from Rule 4) throughout transcript body text. That's a larger and riskier change.
- **Future highlight colors** — red (confirmed correction) and green (reviewed/verified) reserved. Not implemented.
- **Same-speaker em-dash insertion** (Morson's Rules 85, 86, 89) — not detectable deterministically. Future AI-cleanup-pass enhancement or scopist review surface.
- **`CLAUDE.md` drift items** — listed in the 2026-05-12 audit but addressed separately. Not part of this plan.

---

## How to use this plan

1. James reviews this plan and approves it as the canonical reference for the four steps.
2. Claude generates one Codex-ready prompt at a time (`step_a_corrections_cleanup_2026-05-12.md`, then `step_b_*.md`, then `step_c_*.md`, then `step_d_*.md`), each in this same `docs/plans/` directory.
3. Codex executes one step's prompt. The prompt enforces:
   - Single-file or single-package edits.
   - Explicit `DO NOT TOUCH` boundary list.
   - "Stop and report" on any unexpected test failure.
   - PowerShell-compatible acceptance commands.
4. James reviews the diff, runs the acceptance commands, decides:
   - Approve and commit. Move to next step.
   - Reject and revert. Discuss what went wrong.
   - Pause for follow-up sub-step (e.g., Step A.1 to update reversed test assertions).
5. After the step lands, this plan is updated with a status line for that step.
