# Implementation Prompt — Step A: Corrections Cleanup

## Scope

Edit one file: `spec_engine/corrections.py`. Add tests in one new file: `spec_engine/tests/test_corrections_step_a.py`. No other files modified.

This is the first step of the verbatim-punctuation plan
(`docs/plans/verbatim_punctuation_plan_2026-05-12.md`). It reverses four
specific behaviors in the deterministic correction pass that violate the
project's verbatim-with-scribal-punctuation posture.

## Context

`spec_engine/corrections.py::apply_morsons_rules` is the deterministic
post-processing chain applied by the manual "Run Corrections" utility
through `core/corrections_runner.py`. Today it does three things that
contradict the project's authoritative style source (Morson's English
Guide for Court Reporters, Second Edition) and the strict-verbatim
prompt at `clean_format/prompt.py`:

1. **Strips trailing fillers** (`uh`, `um`, `you know`) — violates verbatim. Morson's gives no rule for filler removal; the project's `clean_format/prompt.py` says: *"PRESERVE EXACTLY AS SPOKEN: All filler words (um, uh, like, you know, I mean)."*
2. **Auto-appends `?` based on question-word heuristic** — Morson's has no rule for inferring `?` from word order. The reporter is assumed to have heard the inflection.
3. **Collapses ` -- ` to two spaces** — destroys interruption markers. Morson's Rules 87–89 explicitly use ` -- ` as the interruption representation; Rule 85 Note: *"most court reporters prefer a space before and after the dash."*

And it has one off-by-two: `_SMALL_NUMBER_WORDS` covers 1–12, but
Morson's Rule 170 spells out 1–10 only.

Step A fixes all four. No other behavior in `corrections.py` changes.

## DO NOT TOUCH

* `core/`, `pipeline/`, `ufm_engine/`, `clean_format/`, `ui/`, `scripts/`
* `spec_engine/` files other than `corrections.py` and the new test file
* `spec_engine/qa_fixer.py`, `spec_engine/emitter.py`, `spec_engine/classifier.py`, `spec_engine/processor.py`, `spec_engine/block_builder.py`, `spec_engine/utterance_splitter.py`, `spec_engine/speaker_mapper.py`, `spec_engine/ufm_rules.py`, `spec_engine/models.py`
* Any existing test file (including `spec_engine/tests/test_corrections.py` and `spec_engine/tests/test_morsons_rules.py`)
* `config.py`, `pytest.ini`, `requirements.txt`

If any FIND anchor below does not match the current file content,
**stop and report** rather than guessing.

## Contracts (final)

The four behavioral changes to `apply_morsons_rules`:

### 1. Trailing filler strip removed

The line in `_fix_ending_punctuation` that uses `re.sub` to delete
trailing `uh|um|you know` is deleted entirely. After Step A, the
function only handles `rstrip()` and terminal-punctuation defaulting.

### 2. Terminal-`?` heuristic replaced with period-only default

The branch in `_fix_ending_punctuation` that appends `?` when the text
starts with a word in `_QUESTION_STARTERS` is deleted. When no terminal
`.!?` is present, append `.`. Nothing else. `_QUESTION_STARTERS` may
remain defined at module scope; it is no longer referenced.

### 3. `_fix_em_dashes` deleted; `_normalize_em_dashes` added

`_fix_em_dashes` was a destructive collapser (`re.sub(r"\s?--\s?", "  ", text)`).
It is removed entirely from the module.

A new function `_normalize_em_dashes` is added in its place. Contract:

- Normalizes representations of em-dashes to spaced double-hyphen ` -- `.
- Sources normalized: `—` (U+2014), `–` (U+2013), `--` with any surrounding whitespace pattern.
- Never deletes a dash. Never collapses to whitespace.
- Idempotent: running it twice produces the same result as running it once.

### 4. `_SMALL_NUMBER_WORDS` narrowed to 1–10

Per Morson's Rule 170. Keys `"11"` and `"12"` are removed from the dict.
Sentence-initial `11` and `12` remain digits.

### 5. Pipeline order in `apply_morsons_rules` updated

The replaced call to `_fix_em_dashes` becomes `_normalize_em_dashes`. No
other ordering changes.

---

## Edit 1 — `spec_engine/corrections.py`

Make the following find-and-replace edits in this exact order. If any
FIND anchor does not match the current file content character-for-character,
stop and report.

### Edit 1.1 — Narrow `_SMALL_NUMBER_WORDS`

**FIND** (verbatim, including comma trailing on the last entry):

```python
_SMALL_NUMBER_WORDS = {
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
    "10": "Ten",
    "11": "Eleven",
    "12": "Twelve",
}
```

**REPLACE WITH**:

```python
# Per Morson's Rule 170: spell out isolated numbers 1-10. Eleven and
# twelve are kept as digits. Authority for this project's style is
# Morson's English Guide for Court Reporters, Second Edition.
_SMALL_NUMBER_WORDS = {
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
    "10": "Ten",
}
```

### Edit 1.2 — Replace `_fix_em_dashes` with `_normalize_em_dashes`

**FIND** (the entire function as it currently stands):

```python
def _fix_em_dashes(text: str) -> str:
    text = re.sub(r"\s?--\s?", "  ", text)
    return re.sub(r"\s-\s", "  ", text)
```

**REPLACE WITH**:

```python
def _normalize_em_dashes(text: str) -> str:
    """Normalize all em-dash representations to spaced double-hyphen.

    Per Morson's Rule 85 Note, the spaced double-hyphen ` -- ` is the
    canonical court-reporting form. This function ONLY normalizes the
    representation; it NEVER collapses an interruption marker into
    spaces and NEVER removes one.

    Conversions:
    - U+2014 (em-dash) `—` -> ` -- `
    - U+2013 (en-dash) `–` -> ` -- `
    - ASCII `--` with inconsistent surrounding whitespace -> ` -- `

    The function is idempotent: running it on already-normalized text
    produces the same result.
    """
    # Unicode em-dash and en-dash with any surrounding whitespace.
    text = re.sub(r"\s*[\u2013\u2014]\s*", " -- ", text)
    # ASCII double-hyphen with any surrounding whitespace.
    text = re.sub(r"\s*--\s*", " -- ", text)
    return text
```

### Edit 1.3 — Rewrite `_fix_ending_punctuation`

**FIND** (the entire function as it currently stands):

```python
def _fix_ending_punctuation(text: str) -> str:
    text = re.sub(r"(?:,\s*)?(you know|uh|um)\s*$", "", text, flags=re.IGNORECASE)
    text = text.rstrip()

    if not re.search(r"[.?!]$", text):
        if text.lower().startswith(_QUESTION_STARTERS):
            text += "?"
        else:
            text += "."

    return text
```

**REPLACE WITH**:

```python
def _fix_ending_punctuation(text: str) -> str:
    """Default missing terminal punctuation to a period.

    Verbatim rule (Morson's; clean_format/prompt.py):
    - Filler words (uh, um, you know) are spoken evidence and are
      NEVER stripped from the transcript, including from end of an
      utterance. The earlier regex that did so is removed.
    - Inferring `?` from word order is unsafe. Morson's gives no rule
      for it; the reporter is assumed to have heard the inflection.
      This deterministic pass defaults to `.` and lets the human
      reviewer flip the call to `?` after audio review.
    """
    text = text.rstrip()

    if not re.search(r"[.?!]$", text):
        text += "."

    return text
```

### Edit 1.4 — Update `apply_morsons_rules` pipeline order

**FIND** (the entire function as it currently stands):

```python
def apply_morsons_rules(text: str) -> str:
    """Apply deterministic Morson's-style transcript rules."""
    text = _fix_spacing(text)
    text = _fix_sentence_start(text)
    text = _fix_ellipses(text)
    text = _fix_em_dashes(text)
    text = _fix_stutters(text)
    text = _fix_short_answer_commas(text)
    text = _fix_ending_punctuation(text)
    return text
```

**REPLACE WITH**:

```python
def apply_morsons_rules(text: str) -> str:
    """Apply deterministic Morson's-style transcript rules.

    Order is significant:
    1. _fix_spacing collapses runs of whitespace.
    2. _normalize_em_dashes converts unicode and inconsistent ASCII
       em-dashes to canonical ` -- `. Runs after _fix_spacing so any
       pre-existing whitespace anomalies are settled first.
    3. _fix_sentence_start uppercases the first letter and spells out
       sentence-initial digits 1-10 per Morson's Rule 170.
    4. _fix_ellipses normalizes `. . .` and `....` to `...`.
    5. _fix_stutters preserves repeated tokens with explicit spacing.
    6. _fix_short_answer_commas inserts editorial commas after
       'yes/no/well/so/now/correct' at the start of an answer and
       before conjunctions in long sentences.
    7. _fix_ending_punctuation defaults missing terminal punctuation
       to `.`. Never strips fillers.
    """
    text = _fix_spacing(text)
    text = _normalize_em_dashes(text)
    text = _fix_sentence_start(text)
    text = _fix_ellipses(text)
    text = _fix_stutters(text)
    text = _fix_short_answer_commas(text)
    text = _fix_ending_punctuation(text)
    return text
```

---

## Edit 2 — Create `spec_engine/tests/test_corrections_step_a.py`

Create this new test file. The name `_step_a` is intentional so it does
not shadow existing `test_corrections.py` or `test_morsons_rules.py`.

```python
"""Positive-coverage tests for Step A behavioral changes.

These tests pin the four behaviors introduced in Step A:
  1. Trailing fillers are preserved (no strip).
  2. Missing terminal punctuation defaults to `.`, never `?`.
  3. Em-dash interruption markers are preserved and normalized to ` -- `.
  4. Sentence-initial digits 11 and 12 are NOT spelled out (Morson's 1-10).

Existing tests in test_corrections.py and test_morsons_rules.py that
encode the now-reversed behaviors must be reviewed in Step A.1. This
file does not modify them.
"""

from __future__ import annotations

from spec_engine.corrections import (
    _normalize_em_dashes,
    apply_morsons_rules,
)


# Rule 1 - filler preservation -------------------------------------------------


class TestFillerPreservation:
    def test_trailing_uh_is_kept(self):
        assert apply_morsons_rules("I think it was, uh") == "I think it was, uh."

    def test_trailing_um_is_kept(self):
        assert apply_morsons_rules("Maybe, um") == "Maybe, um."

    def test_trailing_you_know_is_kept(self):
        assert apply_morsons_rules("It was like that, you know") == "It was like that, you know."

    def test_inline_fillers_are_kept(self):
        assert (
            apply_morsons_rules("I, uh, went to the store, you know, on Tuesday")
            == "I, uh, went to the store, you know, on Tuesday."
        )

    def test_standalone_uh_block_is_kept(self):
        assert apply_morsons_rules("Uh") == "Uh."


# Rule 2 - period-only terminal default ---------------------------------------


class TestPeriodOnlyDefault:
    def test_did_you_does_not_get_question_mark(self):
        assert apply_morsons_rules("did you go there") == "Did you go there."

    def test_who_was_there_does_not_get_question_mark(self):
        assert apply_morsons_rules("who was there") == "Who was there."

    def test_explicit_question_mark_is_kept(self):
        assert apply_morsons_rules("Did you go there?") == "Did you go there?"

    def test_explicit_exclamation_is_kept(self):
        assert apply_morsons_rules("Stop!") == "Stop!"

    def test_explicit_period_is_kept(self):
        assert apply_morsons_rules("I went there.") == "I went there."


# Rule 3 - em-dash preservation and normalization -----------------------------


class TestEmDashHandling:
    def test_spaced_double_hyphen_is_preserved(self):
        assert apply_morsons_rules("I was walking -- no, running") == "I was walking -- no, running."

    def test_unicode_em_dash_is_normalized(self):
        assert apply_morsons_rules("I was walking \u2014 no, running") == "I was walking -- no, running."

    def test_unicode_en_dash_is_normalized(self):
        assert apply_morsons_rules("I was walking \u2013 no, running") == "I was walking -- no, running."

    def test_double_hyphen_without_spaces_is_normalized(self):
        assert apply_morsons_rules("I was walking--no, running") == "I was walking -- no, running."

    def test_trailing_interruption_marker_is_preserved(self):
        # Trailing -- with no terminal punctuation. After Step A:
        # _normalize_em_dashes leaves the -- in place; _fix_ending_punctuation
        # appends `.` since there is no terminal `.!?`. Note: the dash is
        # NOT stripped or collapsed.
        result = apply_morsons_rules("I was about to say --")
        assert " -- " in result or result.endswith(" --.")

    def test_normalize_em_dashes_is_idempotent(self):
        once = _normalize_em_dashes("a -- b")
        twice = _normalize_em_dashes(once)
        assert once == twice
        assert once == "a -- b"

    def test_em_dash_is_never_collapsed_to_spaces(self):
        # Hard guarantee: regardless of source form, output contains ` -- `.
        for src in (
            "A -- B",
            "A \u2014 B",
            "A \u2013 B",
            "A--B",
            "A  --  B",
        ):
            result = _normalize_em_dashes(src)
            assert " -- " in result, f"Em-dash collapsed for input: {src!r}"


# Rule 4 - Morson's 1-10 number range -----------------------------------------


class TestNumberRange:
    def test_one_through_ten_still_spell_out(self):
        assert apply_morsons_rules("1 person was there").startswith("One ")
        assert apply_morsons_rules("5 people were there").startswith("Five ")
        assert apply_morsons_rules("10 people were there").startswith("Ten ")

    def test_eleven_is_not_spelled_out(self):
        assert apply_morsons_rules("11 people were there").startswith("11 ")

    def test_twelve_is_not_spelled_out(self):
        assert apply_morsons_rules("12 people were there").startswith("12 ")

    def test_thirteen_is_not_spelled_out(self):
        assert apply_morsons_rules("13 people were there").startswith("13 ")
```

---

## Acceptance checklist (PowerShell)

Run from the repo root, in order. **If any existing test fails, stop and
report — do NOT modify the failing test.** See "Expected failures from
pre-existing tests" below for the test names that are expected to fail
by design.

```powershell
"=== syntax check ==="
.\.venv\Scripts\python.exe -c "import ast; ast.parse(open(r'spec_engine\corrections.py', encoding='utf-8').read()); print('AST OK')"
""
"=== new tests pass ==="
.\.venv\Scripts\python.exe -m pytest spec_engine/tests/test_corrections_step_a.py -v 2>&1 | Select-Object -Last 30
""
"=== full suite — note any failures and report ==="
.\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 20
""
"=== confirm scope ==="
git status --porcelain
"(expected: only ' M spec_engine/corrections.py' and '?? spec_engine/tests/test_corrections_step_a.py')"
```

### Expected failures from pre-existing tests (do NOT modify, report only)

These four tests encode the behaviors Step A explicitly reverses. They
are expected to fail after this step. Codex must list them in the run
report. James decides in a follow-up turn whether to authorize updating
their assertions in Step A.1.

1. `spec_engine/tests/test_morsons_rules.py::test_question_detection` — asserts `?` auto-append.
2. `spec_engine/tests/test_morsons_rules.py::test_em_dash_normalization` — asserts ` -- ` collapses to spaces.
3. `spec_engine/tests/test_morsons_rules.py::test_interrogative_without_punctuation_gets_question_mark` — asserts `?` auto-append.
4. `spec_engine/tests/test_corrections.py::test_apply_morsons_rules_handles_basic_legal_cleanup` — asserts `?` auto-append for `"did you go there"`.

**If any test fails outside those four, STOP. Report the failure verbatim and do not commit.** A surprise failure is informative and means a behavior we didn't intend to break is broken.

---

## Done definition

* `spec_engine/corrections.py` modified per Edits 1.1-1.4 above.
* `spec_engine/tests/test_corrections_step_a.py` created per Edit 2.
* No other files modified.
* All tests in `test_corrections_step_a.py` pass.
* The four expected pre-existing failures are listed in the run report.
* No other test fails.

Once approved by James, commit with:

```
spec_engine/corrections: stop violating verbatim, preserve interruption markers (Step A)

Aligns the deterministic corrections pass with the project's verbatim-
with-scribal-punctuation posture. Four behavioral changes:

* _fix_ending_punctuation no longer strips trailing fillers (uh, um,
  you know) and no longer auto-appends `?` based on a question-word
  heuristic. Defaults missing terminal punctuation to `.` only.
* _fix_em_dashes (destructive collapser) is replaced by
  _normalize_em_dashes, which converts U+2014, U+2013, and inconsistent
  ASCII `--` to canonical spaced double-hyphen ` -- `. Never collapses,
  never deletes. Idempotent.
* _SMALL_NUMBER_WORDS narrowed from 1-12 to 1-10 per Morson's Rule 170.
* apply_morsons_rules pipeline order updated to call
  _normalize_em_dashes in place of _fix_em_dashes.

Authority: Morson's English Guide for Court Reporters (Rules 85, 170);
clean_format/prompt.py strict-verbatim posture;
docs/plans/verbatim_punctuation_plan_2026-05-12.md.

Pre-existing tests that encode the reversed behaviors (4 cases in
test_morsons_rules.py and test_corrections.py) will fail. They are
intentionally not modified in this commit; assertion updates land
under Step A.1 with explicit per-case review.
```

Step A.1 — updating the four pre-existing failing tests — is a separate
prompt issued only after James confirms the failure list.
