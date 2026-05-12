# Implementation Prompt — Post-Release Cleanup (2026-05-12)

Three independent cleanup items, each in its own commit:

1. **CLAUDE.md drift refresh** — fix four statements that contradict the current code.
2. **MarkerDriftError UI propagation verification** — verify (and fix if needed) the path from `format_transcript` raising `MarkerDriftError` to a usable message in the UI.
3. **`ufm_template/` triage** — inspect the untracked directory and decide commit/gitignore/delete.

Each phase is independent. None depends on another. Run them in order; commit between each; report between each. Stop and report if any phase hits an unexpected condition.

---

## DO NOT TOUCH (applies to all phases)

- `pipeline/`, `spec_engine/`, `clean_format/`, `ufm_engine/`, `core/` (except `core/job_runner.py` if Phase 2 finds it needs a catch)
- Any test file outside what each phase explicitly creates
- `config.py`, `pytest.ini`, `requirements.txt`
- Step A through E behavioral code (commits `40be155` through `601b943` and the Step E commit)
- Any plan document under `docs/plans/` except the new one this prompt creates

---

## Phase 1 — CLAUDE.md drift refresh

### Scope

Edit one file: `CLAUDE.md`. No code changes. No test changes.

### Context

Per `AGENTS.md`, `CLAUDE.md` is the authoritative AI-context document. The earlier audit (in the conversation that produced this plan) identified four statements in `CLAUDE.md` that contradict the actual code. Since then, nine commits have landed. Some of those drift items may have been corrected by side-effect. Verify each before editing.

### Verify-then-fix protocol

For each of the four drift items below:

1. Locate the relevant section in `CLAUDE.md`.
2. Compare against the live code (the file/symbol cited in the "verify against" line).
3. If the doc statement is still wrong: edit it to match the live code.
4. If the doc statement is now correct (some other commit fixed it): skip and note "already correct" in the Phase 5 report.

### Drift item 1.1 — "Transcribe tab only"

- **Claim in CLAUDE.md:** the visible UI is the Transcribe tab only.
- **Verify against:** `ui/app_window.py`. If it wires both `TranscribeTab` AND `TemplatesTab`, the claim is still drifted.
- **Replacement intent:** state that the visible UI consists of two tabs — `Transcribe` (audio → DOCX via `clean_format/`) and `Templates` (case-template population via `ufm_engine/`). Both are wired in `ui/app_window.py`.

### Drift item 1.2 — "clean_format removes fillers"

- **Claim in CLAUDE.md:** clean_format's cleanup model removes filler and stutters when non-substantive.
- **Verify against:** `clean_format/prompt.py`. If the prompt body contains a strict-verbatim posture ("PRESERVE EXACTLY AS SPOKEN: All filler words..."), the doc claim is drifted.
- **Replacement intent:** state that `clean_format/prompt.py` enforces strict verbatim preservation — fillers (`uh`, `um`, `you know`), stutters, false starts, and self-corrections are preserved exactly as Deepgram transcribed them. The cleanup pass adds scribal punctuation, normalizes em-dashes to ` -- ` per Morson's Rule 85 Note, applies pre-approved proper-noun spellings, and wraps low-confidence tokens in `‹LC:...›` markers for downstream yellow-highlight rendering. It does NOT remove any spoken words. Authority: Morson's English Guide for Court Reporters Rule 170; `docs/plans/verbatim_punctuation_plan_2026-05-12.md`.

### Drift item 1.3 — Active packages list missing `spec_engine/` and `ufm_engine/`

- **Claim in CLAUDE.md:** an active-packages list that includes `pipeline/`, `clean_format/`, `core/`, `ui/` but omits `spec_engine/` and `ufm_engine/`.
- **Verify against:** the codebase. `spec_engine/` is exercised by `core/corrections_runner.py` (Run Corrections button) and `ufm_engine/` is exercised by `ui/tab_templates.py` (Templates tab). Both are actively wired.
- **Replacement intent:** add the two missing packages with one-line descriptions each:
  - `spec_engine/` — Manual deterministic correction utility. Invoked by the "Run Corrections" button via `core/corrections_runner.py`. Produces a `*_corrected.txt` sidecar; does NOT produce the final DOCX. Word-level metadata flows through it per `docs/plans/verbatim_punctuation_plan_2026-05-12.md`.
  - `ufm_engine/` — UFM-template DOCX generator. Powers the Templates tab via `ui/tab_templates.py`. Populates per-case templates with case metadata.

### Drift item 1.4 — "Do not reintroduce a second correction subsystem"

- **Claim in CLAUDE.md:** a rule against reintroducing a second correction subsystem.
- **Verify against:** the codebase. `clean_format/` and `spec_engine/` are both correction subsystems and have coexisted since before this conversation's plan. The rule as stated is contradicted by reality.
- **Replacement intent:** reframe the rule honestly. Two correction subsystems coexist by design:
  - `clean_format/` is the **primary** AI-driven cleanup pass that produces the final DOCX (the "Start Transcription" button).
  - `spec_engine/` is a **secondary** deterministic utility producing a sidecar text file (the "Run Corrections" button).
  - Both observe the same verbatim-with-scribal-punctuation posture per the verbatim-punctuation plan.
  - The rule becomes: **do not introduce a third correction subsystem.** Extend `clean_format/` or `spec_engine/` instead.

### Acceptance for Phase 1

```powershell
"=== syntax check (markdown is not parsed; just check the file exists) ==="
Test-Path CLAUDE.md
""
"=== full suite — no code changes, expect same count as pre-Phase-1 ==="
.\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 5
""
"=== scope check ==="
git status --porcelain
"(expected: only ' M CLAUDE.md', no other changes)"
```

### Commit (Phase 1)

```powershell
git add CLAUDE.md
git commit -m "CLAUDE.md: refresh four drift items against live code post-Step-E" -m "Aligns the authoritative AI-context doc with what the code actually does after the verbatim-punctuation plan landed (commits 40be155 through 601b943 and the Step E commit)." -m "Items refreshed (each verified against live code before editing):" -m "* Visible UI is two tabs (Transcribe, Templates) wired in ui/app_window.py, not one." -m "* clean_format/prompt.py enforces strict verbatim preservation; the prior 'removes filler when non-substantive' framing is reversed." -m "* Active packages list now includes spec_engine/ (Run Corrections utility) and ufm_engine/ (Templates tab generator)." -m "* The 'do not reintroduce a second correction subsystem' rule is reframed: two coexist by design (clean_format/ primary, spec_engine/ secondary); rule becomes 'do not introduce a third.'" -m "Doc only; no code or test changes. Authority for the new wording: live code at the cited files and docs/plans/verbatim_punctuation_plan_2026-05-12.md."
```

### Phase 5 report (Phase 1)

  ## CLAUDE.md drift
  - Item 1.1 (Transcribe tab only): [edited / already correct]
  - Item 1.2 (clean_format removes fillers): [edited / already correct]
  - Item 1.3 (Active packages missing spec_engine/ufm_engine): [edited / already correct]
  - Item 1.4 (Do not reintroduce a second correction subsystem): [edited / already correct]
  - Test suite: [N passed, M failed — should be unchanged from pre-Phase-1]
  - Commit SHA: [hash or "skipped — no items needed editing"]

---

## Phase 2 — MarkerDriftError UI propagation

### Scope

Investigation-first. Possibly edits one of: `ui/tab_transcribe.py`, `core/job_runner.py`. Possibly creates one new test file.

### Context

Commit `601b943` introduced `MarkerDriftError`, raised by `clean_format/low_confidence_markers.py::validate_marker_round_trip` when the Anthropic round-trip drops more than 5% of injected markers with input ≥ 5 markers. The error carries a `stats` attribute (`{input_count, output_count, dropped}`).

`format_transcript` (in `clean_format/formatter.py`) calls `validate_marker_round_trip` internally, so `format_transcript` itself can raise `MarkerDriftError` per the Step E call site (`ui/tab_transcribe.py::_run_clean_format_job` per the Step E report).

**Question this phase answers:** when `format_transcript` raises `MarkerDriftError`, what does Miah actually see in the UI? An unhandled stack trace, a generic "an error occurred" dialog, or a specific actionable message?

### Phase 2.0 — Trace and report (no edits)

Investigate, report, and STOP before editing anything. The fix depends on what's found.

1. Locate the call to `format_transcript` in `ui/tab_transcribe.py::_run_clean_format_job` (or wherever Step E wired it).
2. Identify the exception handling that wraps that call. Specifically:
   - Is there a `try/except` immediately around the `format_transcript` call?
   - If yes, what does the handler do? (logs? shows a dialog? swallows silently? re-raises?)
   - Does the handler catch `MarkerDriftError` specifically, or only `Exception`?
3. Trace one level up: does any parent function catch and handle the error before the UI displays anything?
4. Report findings using this structure:

  ## Trace findings
  - Call site: [file:line]
  - Local except clauses: [list, with what each does]
  - Parent except clauses: [list]
  - On MarkerDriftError, Miah currently sees: [stack trace / generic dialog / specific message / nothing]
  - Stats dict reaches user-visible output: [yes / no]

After reporting, **STOP** and await user decision on whether to proceed to Phase 2.1.

### Phase 2.1 — Fix (only if user authorizes after seeing the trace report)

The fix shape depends on findings, but the goal is:

- `MarkerDriftError` is caught at the UI boundary (most likely in `ui/tab_transcribe.py::_run_clean_format_job` or its caller).
- The catch produces a message Miah can act on, with shape like:

  > Cleanup pass dropped {dropped} of {input_count} low-confidence markers ({drop_pct}% drop). The transcript text is valid, but yellow highlights will be missing for the dropped tokens. Try running again, or proceed with the current transcript.

- The stats dict is logged at WARNING level for later analysis.
- The error does NOT silently downgrade the message; Miah sees that something specific happened.

If a fix is needed, it should add at most:
- One specific `except MarkerDriftError as exc:` clause at the UI boundary.
- One user-facing message (using whatever dialog/messagebox/logger the rest of `_run_clean_format_job` uses for similar errors).
- One test file: `clean_format/tests/test_marker_drift_ui_handling.py` OR `ui/tests/test_clean_format_job_error_handling.py` depending on where the catch lands. Test verifies the catch produces the expected message and logs the stats.

If no fix is needed (the existing handling is already correct), report that and skip the commit.

### Acceptance for Phase 2 (if a fix is applied)

```powershell
"=== syntax check on any edited file ==="
.\.venv\Scripts\python.exe -c "import ast; ast.parse(open('<edited-file>', encoding='utf-8').read()); print('AST OK')"
""
"=== run the new error-handling test ==="
.\.venv\Scripts\python.exe -m pytest <new-test-file> -v 2>&1 | Select-Object -Last 30
""
"=== full suite — expect 557 + new tests passing ==="
.\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 5
```

### Commit (Phase 2, only if a fix is applied)

```powershell
git add <edited-files> <new-test-file>
git commit -m "ui: handle MarkerDriftError with specific user-facing message (post Step E)" -m "Catches the MarkerDriftError raised by clean_format.format_transcript (introduced in commit 601b943) at the UI boundary and surfaces a specific actionable message instead of a generic error." -m "Stats dict (input_count, output_count, dropped, drop_pct) is logged at WARNING level for post-run analysis. Miah sees a message identifying that the cleanup pass dropped markers, that the transcript is still valid, and that re-running is an option." -m "No behavioral change to the cleanup pass itself; this is purely an error-presentation fix."
```

### Phase 5 report (Phase 2)

  ## MarkerDriftError UI propagation
  - Trace findings: [reproduce the report from Phase 2.0]
  - Fix applied: [yes / no — already adequate]
  - Commit SHA: [hash or "skipped — handling was already adequate"]

---

## Phase 3 — `ufm_template/` triage

### Scope

Inspect the `ufm_template/` directory at the repo root. Decide one of: commit, gitignore, delete. Apply the decision.

### Context

The `ufm_template/` directory has been untracked for several sessions. It was flagged in the post-Step-D summary but Claude Code's hygiene pass deliberately left it untouched (Claude Code's prior recap: *"Leaving ufm_template/ and CLAUDE.md alone — no specific drift to act on"*). It's the last "what is this and what do we do with it" item from the audit.

### Phase 3.0 — Inspect

```powershell
"--- directory listing ---"
Get-ChildItem ufm_template -Recurse -ErrorAction SilentlyContinue | Select-Object FullName, Length, LastWriteTime
""
"--- count by extension ---"
Get-ChildItem ufm_template -Recurse -File -ErrorAction SilentlyContinue | Group-Object Extension | Select-Object Name, Count
""
"--- total size ---"
(Get-ChildItem ufm_template -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
""
"--- any nested directories? ---"
Get-ChildItem ufm_template -Recurse -Directory -ErrorAction SilentlyContinue | Select-Object FullName
```

### Phase 3.1 — Decide based on contents

Apply the first matching rule. If none match cleanly (the contents are ambiguous), STOP and report — do not delete or commit speculatively.

- **Empty or doesn't exist:** `Remove-Item -Recurse -Force ufm_template -ErrorAction SilentlyContinue`. Note in report.
- **Contains only `.docx` template files (UFM templates):** these are reference assets; `git add ufm_template/` and commit. The `ufm_engine/` already has its own `templates/` subdirectory; this top-level one may be a duplicate or a newer set. If it duplicates `ufm_engine/templates/`, STOP and report rather than committing.
- **Contains only generated/transient files (logs, output JSON, build artifacts):** add `/ufm_template/` to `.gitignore`. Do NOT delete the directory itself — leave the contents in place since they may still be useful locally, just stop tracking it.
- **Mixed contents or unclear purpose:** STOP. Report what's in there and ask the user to make the call.

### Acceptance for Phase 3

```powershell
"=== scope check ==="
git status --porcelain
"(expected: depends on decision — see report below)"
""
"=== full suite — no code changes, count unchanged ==="
.\.venv\Scripts\python.exe -m pytest -q 2>&1 | Select-Object -Last 5
```

### Commit (Phase 3, shape depends on decision)

For commit-the-templates path:
```powershell
git add ufm_template/
git commit -m "ufm_template: commit reference templates" -m "[describe what's in there and why it's tracked]"
```

For gitignore path:
```powershell
git add .gitignore
git commit -m "gitignore: stop tracking ufm_template/ working directory" -m "[describe what's in there and why it's transient]"
```

For delete path:
```powershell
# (Remove-Item already deleted the directory; nothing to commit unless other working-tree changes accumulated.)
git status --porcelain
```

### Phase 5 report (Phase 3)

  ## ufm_template/ triage
  - Contents found: [extension counts, file count, total size]
  - Decision: [commit / gitignore / delete / stop-and-ask]
  - Reason: [one sentence]
  - Commit SHA: [hash or "no commit — directory deleted with no staged changes"]

---

## Final summary expected after all three phases

  ## Phase 1 (CLAUDE.md drift): [N items edited, M already correct]
  ## Phase 2 (MarkerDriftError UI): [findings summary, fix applied yes/no]
  ## Phase 3 (ufm_template/): [decision and SHA]

  Total commits added: [0–3]
  Test suite: [previous → new]
  Branch state: still local (not pushed) unless you say otherwise.

Begin Phase 1.
