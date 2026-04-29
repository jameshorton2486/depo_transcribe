# Depo-Pro Transcribe — Stabilization Plan
## Track 1: Fix What Exists | Track 2: Formal Change Process

**Principle:** Each phase ends with a compile check and a full test run.
No phase begins until the previous phase passes its exit gate.
The application runs correctly throughout — no phase breaks runtime behavior.

---

## STOP CONDITIONS — Read This First

**Stop immediately and do not proceed if any of the following occurs:**

```
[ ] A previously passing test now fails unexpectedly
[ ] A corrected transcript output changes in meaning (not just formatting)
[ ] Speaker labels are altered in an unintended way
[ ] Q/A structure breaks in any transcript
[ ] The corrections.json file stops recording changes
[ ] A compile check fails on any modified file
[ ] The app fails to start after a change
```

Do not move to the next phase until the stop condition is resolved.
Do not assume it will sort itself out.

---

## PHASE 0 — Safety Baseline (Mandatory Before Anything Else)

**What:** Save current pipeline output on real transcripts before
touching a single file. This is your rollback reference.

**Why:** Tests passing does not guarantee output is unchanged. The
baseline lets you compare before/after at every phase and immediately
catch "tests passed but output changed" bugs.

**Time required:** 20–30 minutes.

### Step 0.1 — Record test baseline

```powershell
cd C:\Users\james\PycharmProjects\depo_transcribe
.\.venv\Scripts\python.exe -m pytest --tb=no -q 2>&1 | tail -3
```

Write down: **363 passed, 34 failed, 3 skipped**

### Step 0.2 — Save corrected output for 2–3 real transcripts

Use cases you already have on disk. For each:
1. Open Depo-Pro
2. Load the case in the Corrections tab
3. Run Pass 1 (Python corrections only — not AI)

### Step 0.3 — Copy outputs to baseline folder

```powershell
mkdir spec_engine\tests\baseline

# Repeat for each case you ran
copy "{case_folder}\Deepgram\{stem}_corrected.txt" `
     spec_engine\tests\baseline\{casename}_corrected_BASELINE.txt

copy "{case_folder}\Deepgram\{stem}_corrections.json" `
     spec_engine\tests\baseline\{casename}_corrections_BASELINE.json
```

Priority: save the Matthew Coger transcript at minimum:
```
spec_engine\tests\baseline\coger_corrected_BASELINE.txt
spec_engine\tests\baseline\coger_corrections_BASELINE.json
```

### Step 0.4 — Verify corrections.json is populated

Open the corrections JSON file. Confirm it contains actual correction
entries — not an empty array `[]`. If it is empty, note this as a
pre-existing issue before proceeding to Phase 1.

### Phase 0 Exit Gate
```
[ ] Test count recorded (363/34/3)
[ ] At least 2 baseline corrected .txt files saved
[ ] corrections.json files saved alongside each
[ ] Baseline folder is safe (backed up or committed)
```

---

## PHASE 1 — Clean the Test Suite (No Code Risk)

**What:** Fix 34 failing tests that fail because of stale references,
not because the code is broken. Zero runtime changes. Zero risk.

**Why first:** A noisy test suite with 34 failures hides real problems.
After this phase, any new failure is a genuine signal you need to act on.

**Exit gate:** `0 failed, 363+ passed`

---

### Step 1.1 — Fix 22 stale `formatter` import failures

These tests import `from formatter import ...` but that module was
merged into `spec_engine/corrections.py` and `core/correction_runner.py`.

**Files to change:**
- `spec_engine/tests/test_spec.py`
- `spec_engine/tests/test_phase5_verification.py`

**Find every line matching:**
```python
from formatter import format_transcript
from formatter import normalize_sentence_spacing
from formatter import format_blocks
from formatter import QA_WIDTH
```

**Replace with the correct import paths:**
```python
# normalize_sentence_spacing moved to spec_engine.corrections
from spec_engine.corrections import normalize_sentence_spacing

# format_transcript equivalent is format_blocks_to_text
from core.correction_runner import format_blocks_to_text

# format_blocks — use format_blocks_to_text
from core.correction_runner import format_blocks_to_text as format_blocks

# QA_WIDTH — now in spec_engine.emitter
from spec_engine.emitter import QA_WRAP_WIDTH as QA_WIDTH
```

**Verify after:**
```powershell
.\.venv\Scripts\python.exe -m pytest spec_engine/tests/test_spec.py spec_engine/tests/test_phase5_verification.py --tb=short -q
```

---

### Step 1.2 — Fix 4 `main.py not found` failures

Tests in `test_phase6_verification.py` look for `main.py` at the project
root. The entry point is `app.py`.

**File to change:** `spec_engine/tests/test_phase6_verification.py`

**Find:**
```python
Path("main.py").read_text()
```

**Replace with:**
```python
Path("app.py").read_text()
```

**Verify after:**
```powershell
.\.venv\Scripts\python.exe -m pytest spec_engine/tests/test_phase6_verification.py --tb=short -q
```

---

### Step 1.3 — Fix 1 Windows path separator failure

`core/tests/test_file_manager.py` asserts a Windows backslash path but
the test environment uses forward slashes.

**File to change:** `core/tests/test_file_manager.py`

**Find:**
```python
assert path.endswith("2026\\Mar\\2025CI19595\\coger_matthew")
```

**Replace with:**
```python
import os
expected = os.path.join("2026", "Mar", "2025CI19595", "coger_matthew")
assert path.endswith(expected)
```

**Verify after:**
```powershell
.\.venv\Scripts\python.exe -m pytest core/tests/test_file_manager.py --tb=short -q
```

---

### Step 1.4 — Fix 2 `ai_tools` missing module failures

Two tests in `test_spec.py` import `from ai_tools import ...` — that
module does not exist. These tests describe planned functionality that
was never implemented. Mark them as skipped with a reason.

**File to change:** `spec_engine/tests/test_spec.py`

**Find:**
```python
def test_validate_legal_correction_output_rejects_label_reordering():
    from ai_tools import validate_legal_correction_output
```

**Replace with:**
```python
@pytest.mark.skip(reason="ai_tools module not yet implemented — planned feature")
def test_validate_legal_correction_output_rejects_label_reordering():
    from ai_tools import validate_legal_correction_output
```

Apply the same `@pytest.mark.skip` decorator to:
- `test_parse_indexed_ai_output_rejects_reordered_output`
- `test_diff_viewer_summary`

---

### Step 1.5 — Fix `docxtpl` missing in ufm_engine test

One test tries to import `ufm_engine` which requires `docxtpl` — a
dependency that is in requirements.txt but not installed in the test
environment. Mark it skipped.

**File to change:** `spec_engine/tests/test_spec.py`

**Find:**
```python
def test_docx_merger_single_source():
    from docx import Document
    from ufm_engine.docx_merger import DocxMerger
```

**Replace with:**
```python
@pytest.mark.skip(reason="ufm_engine is inactive subsystem — requires docxtpl")
def test_docx_merger_single_source():
    from docx import Document
    from ufm_engine.docx_merger import DocxMerger
```

---

### Phase 1 Exit Gate

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=no -q 2>&1 | tail -3
```

**Required result: 0 failed** (skipped tests are acceptable)

### Phase 1 Completion Checklist
```
[ ] 0 failing tests (skipped is fine)
[ ] No new warnings introduced
[ ] Compile check passes on every file touched
[ ] Baseline output files unchanged (compare against Phase 0 baseline)
[ ] No app behavior changed — this phase touched tests only
```

Do not proceed to Phase 2 until all boxes are checked.

---

## PHASE 2 — Fix Real Behavioral Issues

**What:** Fix two genuine code issues found by the test suite.
These affect the quality of the plain text correction output.

**Risk level:** Low. Changes are contained to one function and
do not touch the DOCX export path or the Deepgram pipeline.

**Exit gate:** `test_block_pipeline_behavior.py` — 0 failed

---

### Step 2.1 — Fix tab format in format_blocks_to_text

**Problem:** `format_blocks_to_text()` in `core/correction_runner.py`
outputs `\tQ.\t\t{text}` (two tabs after Q.) but the UFM standard
requires `\tQ.  {text}` — one tab before Q., then TWO LITERAL SPACES
after the period. Not a tab. Two spaces.

**File:** `core/correction_runner.py`

**Find:**
```python
if bv == "Q":
    lines.append(f"\tQ.\t\t{text}")
elif bv == "A":
    lines.append(f"\tA.\t\t{text}")
```

**Replace with:**
```python
if bv == "Q":
    lines.append(f"\tQ.  {text}")
elif bv == "A":
    lines.append(f"\tA.  {text}")
```

**Note:** The DOCX output via `spec_engine/emitter.py` uses tab stops
configured in twips — that is a separate Phase 7 task (the emitter
tab stop values need adjustment to match 720/1440/2160 twips).
This fix affects the plain .txt correction output only.

---

### Step 2.2 — Add line wrapping to plain text output

**Problem:** `format_blocks_to_text()` outputs lines with no wrapping.
Long witness answers run as single lines in the .txt file. The DOCX
emitter wraps at 56 chars (Q/A) and 65 chars (SP), so the .txt output
should match.

**File:** `core/correction_runner.py`

**Add import at top of file:**
```python
import textwrap
```

**Replace the format_blocks_to_text function:**
```python
_QA_WRAP  = 56   # matches spec_engine/emitter.py QA_WRAP_WIDTH
_SP_WRAP  = 65   # matches spec_engine/emitter.py WRAP_WIDTH

def format_blocks_to_text(blocks: list) -> str:
    from spec_engine.models import BlockType
    lines: list[str] = []

    for block in blocks:
        bt  = getattr(block, "block_type", None)
        bv  = getattr(bt, "value", str(bt)) if bt else "UNKNOWN"
        text = (block.text or "").strip()
        role = (getattr(block, "speaker_role", "") or "").strip()
        name = (getattr(block, "speaker_name", "") or "").strip()

        if not text:
            continue

        if bv == "Q":
            wrapped = textwrap.fill(text, width=_QA_WRAP)
            lines.append(f"\tQ.  {wrapped}")
        elif bv == "A":
            wrapped = textwrap.fill(text, width=_QA_WRAP)
            lines.append(f"\tA.  {wrapped}")
        elif bv in ("COLLOQUY", "SPEAKER", "SP"):
            label   = (name or role or "SPEAKER").upper()
            wrapped = textwrap.fill(text, width=_SP_WRAP)
            lines.append(f"\t\t\t{label}:  {wrapped}")
        elif bv in ("PAREN", "PARENTHETICAL", "PN"):
            lines.append(f"({text})")
        elif bv == "FLAG":
            lines.append(text)
        else:
            if name or role:
                label   = (name or role).upper()
                wrapped = textwrap.fill(text, width=_SP_WRAP)
                lines.append(f"\t\t\t{label}:  {wrapped}")
            else:
                lines.append(text)

    return "\n\n".join(lines)
```

---

### Phase 2 Exit Gate

```powershell
.\.venv\Scripts\python.exe -m pytest spec_engine/tests/test_block_pipeline_behavior.py -v
.\.venv\Scripts\python.exe -m pytest --tb=no -q 2>&1 | tail -3
```

**Required:** `test_block_pipeline_behavior.py` — 0 failed.
Full suite — no new failures compared to end of Phase 1.

### Phase 2 Diff Verification

After Phase 2, re-run corrections on the Coger transcript and compare
the output against your Phase 0 baseline:

```powershell
# Run corrections again (Pass 1 only)
# Then compare:
fc spec_engine\tests\baseline\coger_corrected_BASELINE.txt `
   "{case_folder}\Deepgram\{stem}_corrected.txt"
```

**Expected differences:** Only formatting changes — tab spacing and
line wrapping. The words, speaker labels, and content must be identical.

If `fc` reports differences in content (not just whitespace/tabs):
→ Stop. Investigate before proceeding to Phase 3.

### Phase 2 Completion Checklist
```
[ ] test_block_pipeline_behavior.py — 0 failed
[ ] Full suite — no new failures vs Phase 1
[ ] Diff vs baseline shows formatting changes only
[ ] No content, speaker label, or meaning changes
[ ] Compile check on core/correction_runner.py passes
```

---

## PHASE 3 — Add Missing Test Coverage

**What:** Write tests for six functions that currently have zero coverage.
These run on every transcript. No changes to production code.

**Risk level:** Zero. Tests only. Production code unchanged.

**Exit gate:** All new tests pass. Full suite still green.

---

### Step 3.1 — Tests for apply_case_corrections

This is the highest-risk untested function. It applies confirmed spellings
from the NOD (e.g., "Koger" → "Coger"). If it silently breaks, names are
wrong in every transcript with no visible error.

**Create:** `spec_engine/tests/test_corrections_coverage.py`

Start with this template and fill in real examples from actual depositions:

```python
"""
Tests for correction functions that had zero coverage.
All tests are offline and deterministic.
Run: python -m pytest spec_engine/tests/test_corrections_coverage.py -v
"""
import pytest
from spec_engine.corrections import (
    apply_case_corrections,
    fix_conversational_titles,
    fix_even_dollar_amounts,
    fix_uh_huh_hyphenation,
    normalize_time_and_dashes,
)
from spec_engine.models import CorrectionRecord, JobConfig


def _job(spellings: dict) -> JobConfig:
    cfg = JobConfig()
    cfg.confirmed_spellings = spellings
    return cfg


class TestApplyCaseCorrections:

    def test_replaces_misspelled_name(self):
        records = []
        result = apply_case_corrections(
            "The witness is Koger.", _job({"Koger": "Coger"}), records, 0
        )
        assert result == "The witness is Coger."

    def test_case_insensitive_match(self):
        records = []
        result = apply_case_corrections(
            "koger testified.", _job({"Koger": "Coger"}), records, 0
        )
        assert "Coger" in result

    def test_records_correction(self):
        records = []
        apply_case_corrections(
            "Koger was there.", _job({"Koger": "Coger"}), records, 0
        )
        assert len(records) == 1
        assert records[0].original == "Koger"

    def test_no_change_when_already_correct(self):
        records = []
        result = apply_case_corrections(
            "Coger was there.", _job({"Koger": "Coger"}), records, 0
        )
        assert result == "Coger was there."
        assert records == []

    def test_empty_spellings_leaves_text_unchanged(self):
        records = []
        original = "Some text here."
        result = apply_case_corrections(original, _job({}), records, 0)
        assert result == original

    def test_multiple_spellings_applied(self):
        records = []
        result = apply_case_corrections(
            "Koger and Jenkins testified.",
            _job({"Koger": "Coger", "Jenkins": "Jenkyns"}),
            records, 0,
        )
        assert "Coger" in result
        assert "Jenkyns" in result

    def test_does_not_replace_substring(self):
        # "Rog" should not be replaced if the spelling is "Roger" → "Rogar"
        records = []
        result = apply_case_corrections(
            "The Rogerson case.", _job({"Roger": "Rogar"}), records, 0
        )
        # "Rogerson" contains "Roger" but should not match whole-word
        assert "Rogerson" in result


class TestFixConversationalTitles:

    def test_mister_to_mr(self):
        from spec_engine.corrections import fix_conversational_titles
        records = []
        result = fix_conversational_titles("mister Garcia testified.", records, 0)
        assert result == "Mr. Garcia testified."

    def test_miss_to_ms(self):
        from spec_engine.corrections import fix_conversational_titles
        records = []
        result = fix_conversational_titles("miss Ozuna asked.", records, 0)
        assert result == "Ms. Ozuna asked."

    def test_already_correct_unchanged(self):
        from spec_engine.corrections import fix_conversational_titles
        records = []
        original = "Mr. Garcia testified."
        result = fix_conversational_titles(original, records, 0)
        assert result == original
        assert records == []

    def test_lowercase_context_unchanged(self):
        from spec_engine.corrections import fix_conversational_titles
        records = []
        result = fix_conversational_titles("the mister of the house", records, 0)
        # "mister" without a following name should not change
        assert "Mr." not in result


class TestFixEvenDollarAmounts:

    def test_removes_trailing_zeros(self):
        from spec_engine.corrections import fix_even_dollar_amounts
        records = []
        result = fix_even_dollar_amounts("paid $450.00 for services.", records, 0)
        assert "$450" in result
        assert "$450.00" not in result

    def test_non_even_amount_unchanged(self):
        from spec_engine.corrections import fix_even_dollar_amounts
        records = []
        original = "paid $450.50 for services."
        result = fix_even_dollar_amounts(original, records, 0)
        assert result == original


class TestFixUhHuhHyphenation:

    def test_uh_huh_space_to_hyphen(self):
        from spec_engine.corrections import fix_uh_huh_hyphenation
        records = []
        result = fix_uh_huh_hyphenation("Uh huh, I agree.", records, 0)
        assert "uh-huh" in result.lower()

    def test_uh_uh_space_to_hyphen(self):
        from spec_engine.corrections import fix_uh_huh_hyphenation
        records = []
        result = fix_uh_huh_hyphenation("Uh uh, I disagree.", records, 0)
        assert "uh-uh" in result.lower()

    def test_already_hyphenated_unchanged(self):
        from spec_engine.corrections import fix_uh_huh_hyphenation
        records = []
        original = "Uh-huh, that's right."
        result = fix_uh_huh_hyphenation(original, records, 0)
        assert result == original


class TestNormalizeTimeAndDashes:

    def test_time_without_space_gets_space(self):
        from spec_engine.corrections import normalize_time_and_dashes
        records = []
        result = normalize_time_and_dashes("at 10:08AM.", records, 0)
        assert "10:08 AM" in result

    def test_already_correct_time_unchanged(self):
        from spec_engine.corrections import normalize_time_and_dashes
        records = []
        original = "at 10:08 AM."
        result = normalize_time_and_dashes(original, records, 0)
        assert result == original
```

### Steps 3.2–3.6 — Remaining untested functions

Apply the same pattern (HappyPath / FalsePositiveGuard / EdgeCases) to:

- `normalize_time_and_dashes()` — verify AM/PM spacing, 12-hour format
- `fix_qa_structure()` — verify inline split, orphan merge
- `apply_multiword_corrections()` — verify subpoena variants
- `apply_artifact_removal()` — verify 4+ char only, not short words
- `apply_sentence_start_number()` — verify Morson's 1-10 at sentence start

---

### Phase 3 Exit Gate

```powershell
.\.venv\Scripts\python.exe -m pytest spec_engine/tests/test_corrections_coverage.py -v
.\.venv\Scripts\python.exe -m pytest --tb=no -q 2>&1 | tail -3
```

**Required:** All new tests pass. No regression in full suite.

---

## PHASE 4 — AI Corrector Cleanup

**What:** Reduce token waste in the AI correction pass and eliminate
rule overlap between Python Pass 1 and AI Pass 2.

**Risk level:** Low-medium. System prompt changes only. No Python changes.
Test by running a real AI correction on one transcript before and after.

**Exit gate:** AI correction run on a real transcript produces identical
or better output. Cost per run visibly reduced.

---

### Step 4.1 — Strip cosmetic dividers from system prompt

**File:** `spec_engine/ai_corrector.py`

The system prompt uses `═══` and `───` borders around each rule section.
These consume ~535 tokens (25% of the prompt) with no benefit to Claude.

Replace all section headers from:
```
═══════════════════════════════════════════════════════════════════
RULE 5 — SPEAKER STRUCTURE
═══════════════════════════════════════════════════════════════════
```

To:
```
## RULE 5 — SPEAKER STRUCTURE
```

Apply to all 16 section headers in the prompt.

---

### Step 4.2 — Remove rules already handled by Python

Remove from the AI system prompt (Python already handles these correctly):

- **Rule 20 (Conversational titles)** — `fix_conversational_titles()` in
  corrections.py handles `mister → Mr.` deterministically. AI re-doing this
  risks inconsistency and wastes tokens.

- **The verbatim list repetition** — The intro paragraph and the Rule 23
  section both list the verbatim-protected words. Keep Rule 23, remove the
  duplicate list from the intro.

---

### Step 4.3 — Increase MAX_CHARS to reduce chunk count

**File:** `spec_engine/ai_corrector.py`

```python
# Before
MAX_CHARS = 12000

# After — reduces 1hr deposition from 4 chunks to 3 chunks
MAX_CHARS = 18000
```

Also update max_tokens to match:
```python
# Before
max_tokens=4096,

# After — output cannot exceed input length for correction tasks
max_tokens=5500,
```

---

### Step 4.4 — Cap proper nouns list

```python
# Before
proper_nouns[:80]

# After — 30 is sufficient for a single deposition
proper_nouns[:30]
```

---

### Phase 4 Exit Gate

Run AI correction on the Matthew Coger transcript. Verify:
1. Output quality is equal or better
2. Terminal shows 3 chunks instead of 4
3. Log shows reduced token estimates

### Phase 4 AI Structural Guardrails

After running AI correction, verify the AI has not altered structure:

```powershell
# Compare Pass 1 output vs AI output
fc "{stem}_corrected.txt" "{stem}_ai_corrected.txt"
```

The AI output must NOT have:
- Different number of speaker turns
- Changed any `Q.` / `A.` / `MR. GARCIA:` labels
- Removed any text (deletions are not corrections)
- Added paragraphs that were not in Pass 1 output

If any structural differences are found:
→ Do not use the AI output. Investigate the system prompt change
  that caused the structural modification before re-running.

### Phase 4 Completion Checklist
```
[ ] AI correction runs without error
[ ] 3 chunks logged (not 4) for Coger transcript
[ ] AI output content quality equal or better than before
[ ] AI output has no structural differences from Pass 1
[ ] No speaker labels altered by AI
[ ] No Q/A blocks added, removed, or reordered
[ ] System prompt changes documented in ai_corrector.py comment
```

---

## PHASE 5 — Add AI Corrector Tests

**What:** Add tests for `spec_engine/ai_corrector.py` which currently
has zero test coverage. All tests use mock clients — no API calls.

**Risk level:** Zero. Tests only.

**Create:** `spec_engine/tests/test_ai_corrector.py`

```python
"""
Tests for spec_engine/ai_corrector.py
All offline — mock client used, no real API calls.
Run: python -m pytest spec_engine/tests/test_ai_corrector.py -v
"""
import pytest
from unittest.mock import MagicMock
from spec_engine.ai_corrector import (
    _split_into_chunks,
    _renumber_scopist_flags,
    _build_user_prompt,
)


class TestSplitIntoChunks:

    def test_short_text_single_chunk(self):
        text = "Speaker 1: Short text."
        result = _split_into_chunks(text, max_chars=1000)
        assert len(result) == 1
        assert result[0] == text

    def test_splits_at_paragraph_boundary(self):
        para1 = "A" * 100
        para2 = "B" * 100
        text = para1 + "\n\n" + para2
        result = _split_into_chunks(text, max_chars=150)
        assert len(result) == 2
        assert para1 in result[0]
        assert para2 in result[1]

    def test_never_splits_mid_paragraph(self):
        long_para = "word " * 500  # 2500 chars, one paragraph
        result = _split_into_chunks(long_para, max_chars=500)
        # Should be one chunk — cannot split a single paragraph
        assert len(result) == 1

    def test_chunks_reassemble_to_original(self):
        text = "\n\n".join([f"Paragraph {i}: " + "x" * 50 for i in range(10)])
        chunks = _split_into_chunks(text, max_chars=300)
        reassembled = "\n\n".join(chunks)
        assert reassembled == text


class TestRenumberScopistFlags:

    def test_renumbers_from_one(self):
        text = "text [SCOPIST: FLAG 5: something] more [SCOPIST: FLAG 12: other]"
        result = _renumber_scopist_flags(text)
        assert "[SCOPIST: FLAG 1:" in result
        assert "[SCOPIST: FLAG 2:" in result
        assert "[SCOPIST: FLAG 5:" not in result
        assert "[SCOPIST: FLAG 12:" not in result

    def test_no_flags_unchanged(self):
        text = "Clean transcript text with no flags."
        assert _renumber_scopist_flags(text) == text

    def test_single_flag_becomes_flag_1(self):
        text = "text [SCOPIST: FLAG 99: verify this]"
        result = _renumber_scopist_flags(text)
        assert "[SCOPIST: FLAG 1:" in result


class TestBuildUserPrompt:

    def test_includes_proper_nouns(self):
        prompt = _build_user_prompt("text", ["Coger", "Murphy Oil"], {}, {})
        assert "Coger" in prompt
        assert "Murphy Oil" in prompt

    def test_includes_speaker_map(self):
        prompt = _build_user_prompt("text", [], {0: "THE WITNESS", 2: "MR. GARCIA"}, {})
        assert "THE WITNESS" in prompt
        assert "MR. GARCIA" in prompt

    def test_includes_transcript_text(self):
        prompt = _build_user_prompt("Did you go there?", [], {}, {})
        assert "Did you go there?" in prompt

    def test_empty_context_still_includes_text(self):
        prompt = _build_user_prompt("Some testimony.", [], {}, {})
        assert "Some testimony." in prompt


class TestAIFallbackInterface:

    def test_raises_value_error_without_client(self):
        from spec_engine.corrections.repeated_words import correct_repeated_words
        # Verify the interface contract: ai_client=None raises ValueError
        with pytest.raises((ValueError, TypeError)):
            correct_repeated_words("I I", use_ai_fallback=True, ai_client=None)
```

---

### Phase 5 Exit Gate

```powershell
.\.venv\Scripts\python.exe -m pytest spec_engine/tests/test_ai_corrector.py -v
.\.venv\Scripts\python.exe -m pytest --tb=no -q 2>&1 | tail -3
```

**Required:** All new tests pass. No regression.

---

## PHASE 6 — First Golden Test

**What:** Create the first end-to-end golden test using the Matthew Coger
deposition. This is the most valuable test you can have — it verifies that
the full pipeline from Deepgram JSON to corrected text output is correct.

**Why now:** After Phases 1–5, the pipeline is stable and tested. Now is
the right time to lock in the expected output of a real deposition.

**Steps:**

1. Run a full correction on the Matthew Coger transcript
2. Verify the output is correct (all speakers, corrections, formatting)
3. Copy files to golden folder:
```powershell
copy "{case_folder}\Deepgram\{stem}.json" spec_engine\tests\golden\coger_input.json
copy "{case_folder}\Deepgram\{stem}_ufm_fields.json" spec_engine\tests\golden\coger_job_config.json
```
4. Generate expected output:
```powershell
.\.venv\Scripts\python.exe tools\generate_golden_expected.py `
    spec_engine\tests\golden\coger_input.json `
    spec_engine\tests\golden\coger_job_config.json `
    spec_engine\tests\golden\coger_expected.txt
```
5. Review `coger_expected.txt` carefully — this becomes the contract
6. Run the golden test:
```powershell
.\.venv\Scripts\python.exe -m pytest spec_engine/tests/test_golden.py -v
```

---

### Phase 6 Exit Gate

Golden test passes. Full suite green.

---

## PHASE 7 — Add New Rules (Using Formal Process)

Only begin this phase after all previous phases are complete and the
test suite is fully green.

Each rule below is fully specified and ready to implement.
Use the Generic Rule Template from CLAUDE.md Section 21.
All four gates must pass before adding any rule to `clean_block()`.

---

### Rule 1: Spelled-out names (Deepgram letter-by-letter artifact)

**What it fixes:**
Deepgram sometimes transcribes a spelled-out name as individual
space-separated letters: `B r e n n e n` → `Brennen`

**Should correct:**
- `B r e n n e n` → `Brennen`
- `J e n k i n s` → `Jenkins`
- `My name is B r e n n e n Jenkins` → `My name is Brennen Jenkins`

**Must NOT change:**
- `Q.` `A.` — single-letter legal line markers
- `J. Smith` — legal name initials with period
- `I` — first-person pronoun

**Rule:** 3+ consecutive single-letter tokens (no periods) → collapse
and capitalize first letter.

**Priority slot:** After Rule 5 (artifact removal), before Rule 6.

---

### Rule 2: Texas cause number normalization

**What it fixes:**
Deepgram sometimes inserts spaces or dashes in alphanumeric cause
numbers: `2025 CI 19595` or `2025-CI-19595` → `2025CI19595`

**Should correct:**
- `2025 CI 19595` → `2025CI19595`
- `2025-CI-19595` → `2025CI19595`
- `cause number 2025 CI 19595` → `cause number 2025CI19595`

**Must NOT change:**
- `2025CI19595` — already correct
- `TX-2025-1234` — different format

**Priority slot:** Rule 2 (case corrections), after confirmed_spellings.

---

### Rule 3: Unclear speaker attribution flag

**What it fixes:**
When `fix_qa_structure()` cannot determine Q or A from the speaker
map, it currently defaults silently. Instead it should flag.

**Change:** In `spec_engine/qa_fixer.py`, when speaker role is
ambiguous, insert:
`[VERIFY: speaker role unclear — verify from audio]`

This is a `qa_fixer.py` change, not a `corrections.py` rule.

---

### Rule 4: Add zero to number-to-word map

**What it fixes:**
`apply_number_to_word()` handles 1–10 but not 0.
`"0 witnesses"` should become `"zero witnesses"`.

**Change:** Add to `NUMBER_WORD_MAP` in `corrections.py`:
```python
'0': 'zero',
```

**Guards:** Same exclusions as existing rule — case numbers,
addresses, zip codes, times, exhibit numbers.

**Priority slot:** Same as existing Rule 4a — no position change needed.

---

### Rule 5: Judicial district artifact correction

**What it fixes:**
Deepgram reads "408th Judicial District" digit by digit.

**Should correct:**
- `4 0 eight judicial district` → `408th Judicial District`
- `four o eight judicial district` → `408th Judicial District`
- `four zero eight judicial district` → `408th Judicial District`

**Must NOT change:**
- `408th` — already correct
- Any context where `4 0 8` appears that is not a judicial district

**Implementation:** Add to `MULTIWORD_CORRECTIONS` in `corrections.py`:
```python
(r'\b4\s+0\s+eight\s+judicial\s+district\b', '408th Judicial District'),
(r'\bfour\s+o\s+eight\s+judicial\s+district\b', '408th Judicial District'),
(r'\bfour\s+zero\s+eight\s+judicial\s+district\b', '408th Judicial District'),
```

**Priority slot:** Rule 1 (multiword corrections).

---

### Rule 6: Exhibit number formatting

**What it fixes:**
Deepgram produces `exhibit 15` but UFM requires `Exhibit No. 15`.

**Should correct:**
- `exhibit 15` → `Exhibit No. 15`
- `exhibit no 15` → `Exhibit No. 15`
- `exhibit number 15` → `Exhibit No. 15`

**Must NOT change:**
- `Exhibit No. 15` — already correct
- `exhibit hall` — not an exhibit reference

**Priority slot:** Rule 3 (universal corrections).

---

### Rule 7: Orphaned punctuation cleanup

**What it fixes:**
Deepgram + smart_format creates `Love,.` (comma immediately before
period) and `course,.` — two punctuation marks where only one belongs.

**Should correct:**
- `Love,.` → `Love.`
- `of course,.` → `of course.`
- `today,.` → `today.`

**Must NOT change:**
- `Inc.,` — comma after period abbreviation is correct
- `No. 15,` — number followed by comma is correct

**Priority slot:** Rule 3 (universal corrections), add as new pattern
in `UNIVERSAL_CORRECTIONS` list.

---

### Rule 8: "cop number" → "Cause Number" 

**What it fixes:**
Deepgram mishears "Cause Number" as "cop number" in the preamble.

**Should correct:**
- `cop number 2025CI19595` → `Cause Number 2025CI19595`
- `This is cop number` → `This is Cause Number`

**Must NOT change:**
- Any genuine use of "cop" in testimony context
- `cop number` when not followed by a case number pattern

**Priority slot:** Rule 3 (universal corrections).

---

### Task A: Witness introduction block template

**What it is:** A fixed template generated by `spec_engine/document_builder.py`
from case metadata. Not a correction rule.

**Template:**
```
[centered bold]  WITNESS FULL NAME,
having been first duly sworn, testified as follows:

[centered bold]  EXAMINATION

BY MR./MS. [ATTORNEY LAST NAME]:
```

**Source fields:** `witness_name` and `examining_attorney` from JobConfig.
Structure never varies. Only the names change.
This is a `document_builder.py` implementation task.

---

### Task B: Emitter tab stop correction

**What it is:** The tab stops in `spec_engine/emitter.py` are wrong.
Current: 360/900/1440/2160 twips.
Correct per UFM spec:
- 720 twips (0.5") left — Q./A. letter position
- 1440 twips (1.0") left — Q./A. text start / SP indent
- 2160 twips (1.5") left — SP text start
- Center of page — center aligned — headers and witness name

This is an `emitter.py` change. Test against the DOCX output
using the Coger golden test after correcting.

---

### Task C: Court reporter preamble block joining

**What it is:** Deepgram fragments the reporter's preamble into
multiple separate SPEAKER blocks. They need to be recognized as
one continuous utterance and joined before classification.

**Implementation:** `spec_engine/qa_fixer.py` — detect consecutive
blocks from the same speaker where the first contains the reporter
self-identification pattern, and join them before classification runs.

This requires careful testing against the golden transcript.

---

## Track 2 — Formal Change Process (Ongoing)

After Phase 7, every change to the correction pipeline — new rule,
modified rule, or AI prompt change — follows this process permanently.

### For any correction rule change:

```
1. DEFINE    Write: what it fixes, 3 real examples, 2 false-positive guards
             Get approval before writing any code.

2. IMPLEMENT Single function in corrections.py.
             Register in clean_block() at correct priority.
             Compile check immediately.

3. TEST      Create test file using Generic Rule Template.
             Five test classes: HappyPath, FalsePositiveGuard,
             PunctuationBoundary, PassOrdering, Interface.
             All offline and deterministic.

4. INTEGRATE Run full test suite.
             Zero regressions = merge.
             Any regression = fix before merging.
```

### For any AI prompt change:

```
1. Document what changed and why in a comment at the top of the
   TRANSCRIPT_CORRECTION_SYSTEM_PROMPT string.

2. Run AI correction on the Coger transcript before and after.
   Verify output quality is equal or better.

3. If the golden test exists, run it after the change.
```

### For any UI change:

```
1. Re-read CLAUDE.md Section 10 (CustomTkinter rules).
2. Compile check immediately after change.
3. Test right-click, keyboard shortcuts, and Edit Mode manually.
```

---

## Summary Timeline

| Phase | What | Risk | Duration |
|---|---|---|---|
| 0 | Safety baseline — save outputs | Zero | 30 min |
| 1 | Fix stale tests | Zero | 1–2 hours |
| 2 | Fix text output format | Low | 1–2 hours |
| 3 | Add missing test coverage | Zero | 3–4 hours |
| 4 | AI prompt cleanup + guardrails | Low | 1–2 hours |
| 5 | AI corrector tests | Zero | 2 hours |
| 6 | First golden test | Low | 1–2 hours |
| 7 | New correction rules | Per rule | Per rule |

**Total to stable baseline: approximately 10–15 hours of focused work.**
After that, the formal process in Track 2 keeps it stable indefinitely.

---

## PHASE U — Utterance-Native Pipeline Hardening

**What:** Harden the current block pipeline so Deepgram utterances remain the
primary structural truth all the way through pass-1 processing.

**Why:** The current repository does **not** flatten raw Deepgram JSON before
building blocks. `spec_engine/block_builder.py` already maps
`results.utterances[]` directly into `Block` objects. The real instability
appears later, when downstream stages reshape those utterance-native blocks:

- `speaker_mapper.py`
- `speaker_intelligence.py`
- `classifier.py`
- `qa_fixer.py`
- `processor.split_blocks_into_paragraphs()`
- `objections.py`

This phase therefore targets **post-block-builder mutation**, not the
utterance import step itself.

**Scope guard:**
- U1–U4 stay inside `spec_engine/` plus tests
- U5 touches `pipeline/transcriber.py` only after the `spec_engine` stages are
  instrumented and measurable
- Do not modify UI/exporter behavior until the exit gates pass

### Step U1 — Preserve Utterance Provenance End-to-End

**Goal:** Keep every block traceable back to its source utterance so later
stages can be audited instead of guessed at.

- Keep `build_blocks_from_deepgram()` as the entry point; do **not** replace it
  with a new parallel object model yet.
- Extend block metadata to carry utterance provenance explicitly:
  - `utterance_index`
  - `utterance_start`
  - `utterance_end`
  - `utterance_confidence`
  - optional `source_word_count`
- Add a run-log snapshot that records:
  - raw utterance count
  - block count after block_builder
  - block count after each subsequent structural stage

**Acceptance checks:**
- block count after `build_blocks_from_deepgram()` equals input utterance count
- each block retains exact source `start`/`end` values in metadata
- targeted tests verify provenance survives corrections and classification

### Step U2 — Add a Boundary Mutation Audit Layer

**Goal:** Identify exactly where utterance-native turns are being merged,
split, or reassigned incorrectly.

- Add deterministic audit logging around these stages:
  - speaker mapping
  - Q/A fixing
  - paragraph splitting
  - objection extraction
- For each stage, log:
  - input block count
  - output block count
  - blocks whose text changed
  - blocks whose speaker assignment changed
- Treat unreviewed speaker reassignment as suspicious when:
  - the utterance gap is short
  - the prior speaker resumes immediately
  - the changed turn is a short witness response (`Yes.`, `No.`, `Okay.`)

**Acceptance checks:**
- new tests cover “short answer swallowed into surrounding attorney turn”
- new tests cover “reporter takeover” false-positive scenario
- drift-suspect transitions are flagged, not silently normalized away

### Step U3 — Turn-Safe Q/A Structure

**Goal:** Make Q/A fixing respect utterance turns before any paragraph-level
splitting occurs.

- Update `qa_fixer.py` so its first responsibility is turn preservation:
  - short single-turn witness answers stay isolated
  - attorney follow-up text does not get attached backward across a witness turn
- Do not use regex alone as the primary turn detector when utterance metadata
  already shows a speaker boundary.
- Move any paragraph splitting logic **after** turn-safe Q/A decisions and keep
  a tested escape hatch for malformed diarization.

**Acceptance checks:**
- fixture reproduces:
  - `Yes.` staying with witness
  - `And is is this portion accurate?` staying with attorney
  - `No. It's not always complete.` staying with witness
- reduced orphan-Q / orphan-A regressions on existing comparison cases

### Step U4 — Timing Intelligence Without Text Mutation

**Goal:** Use utterance timing to support legal review without rewriting the
transcript text.

- Compute and preserve:
  - inter-utterance gap
  - overlap duration
  - interruption markers
  - hesitation windows
- Store these as metadata / flags only
- Never rewrite testimony text from timing analysis

**Acceptance checks:**
- tests for positive overlap and near-zero response gaps
- timing metadata survives pass-1 processing
- no transcript text mutation caused by timing routing

### Step U5 — Deposition-Safe `utt_split` Tuning

**Goal:** Tune transcription-time utterance splitting for legal turn-taking
without reintroducing text-structure drift.

**Important:** Do this **after** U1–U4. Do not change `utt_split` blind.

- Add bounded presets in `pipeline/transcriber.py`
  - rapid cross-exam
  - standard deposition
  - slower expert testimony
- Start with a conservative legal default and log which profile was used
- Keep hard override capability in config

**Initial direction from current evidence:**
- `paragraphs=true` caused harmful turn coalescing in deposition Q/A
- tighter `utt_split` values help preserve short witness responses
- therefore any future tuning must be validated against real-case turn fixtures

**Acceptance checks:**
- unit tests verify profile selection and enforced request params
- real-case comparison confirms improved short-turn separation
- no regression in keyterm transmission or utterance availability

### Step U6 — Confidence-Guided Review Routing

**Goal:** Route human attention to risky utterances instead of reviewing entire
transcripts manually.

- Flag low-confidence utterances deterministically
- Preserve the flag as metadata for downstream UI/highlight consumption
- Keep confidence routing separate from text correction logic

**Acceptance checks:**
- tests verify low-confidence utterances are flagged consistently
- no mutation of transcript text from confidence routing

### Phase U Exit Gate

- [ ] Every pass-1 block can be traced to a source utterance
- [ ] Boundary mutation audit identifies where speaker/turn drift occurs
- [ ] Short witness-answer fixtures pass without turn swallowing
- [ ] Reporter takeover scenario is flagged, not silently reassigned
- [ ] Timing and confidence metadata persist without changing transcript text
- [ ] `py_compile` on every touched module
- [ ] targeted tests green before any full-suite run
- [ ] full suite run with no new failures
