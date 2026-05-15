# Depo-Pro Persistence Boundary & Cross-Case Contamination Audit

Date: 2026-05-14
Scope: `core/`, `pipeline/`, `spec_engine/`, `clean_format/`, `ui/`, plus tests/fixtures and runtime artifact paths.

## Executive Summary

Overall contamination risk level: **MEDIUM**.

The current architecture is **mostly safe by design** for case isolation because production writes are scoped to per-case directories (`{year}/{month}/{cause}/{witness}/...`) and case-specific metadata is loaded from/saved to `source_docs/job_config.json` under that case root. However, a small number of real contamination surfaces exist:

1. **Cross-case folder collision risk** due to aggressive cause-number normalization that can merge differently formatted cause numbers into the same canonical folder key.
2. **Potential long-term retention leakage in logs** where parsed legal entities and filename-derived witness names are logged in plaintext.
3. **Optional walkthrough/debug capture artifacts** are written into case folders and can retain transcript content indefinitely if not lifecycle-managed.

No evidence was found of global singleton memory stores of witness/attorney/provider data that automatically bleed into new runs.

## Confirmed Safe Boundaries

- **Per-case persistence root is explicit and consistent** via case path resolution + required subfolders (`source_docs`, `Deepgram`).
- **Job config persistence is scoped per case** at `{case_root}/source_docs/job_config.json`; load/save APIs require `case_root` input and do not use a process-global config store.
- **Transcription outputs are written under case folder** (`Deepgram/` + case-root artifacts) and not to shared global transcript stores.
- **In-memory UI case state has reset paths** that clear case-bound speaker/term/spelling state when case context changes.
- **Prompt templates are static instructions**; they consume case metadata at runtime and do not embed persistent case-specific entities in the template source.
- **Spec-engine deterministic layers are stateless transforms** (functions over passed blocks) without persistent entity caches.

## Confirmed Risks

### 1) Canonical cause-number collisions can merge distinct cases (HIGH)

Evidence:
- `normalize_cause_number()` strips all non-alphanumeric characters and uppercases, potentially collapsing distinct externally meaningful formats to one key.
- `build_case_path()` and `resolve_or_create_case()` rely on that canonicalized cause segment for folder routing and re-use.

Impact:
- Two distinct matters with different official formatting could resolve to the same cause folder, creating a direct cross-case artifact mix risk.

Bounded fix:
- Keep canonical lookup for matching legacy folders, but persist an immutable `original_cause_number` marker in `case_meta.json` or `job_config.json` and reject/review when a mismatch is detected in an existing folder.

### 2) Legal entity data appears in logs (MEDIUM)

Evidence:
- Filename extraction logs include extracted witness fields.
- Intake parser logs preview keyterms with reason text.

Impact:
- Witness/attorney/provider entities can persist in application logs outside case folders, broadening retention surface and discoverability.

Bounded fix:
- Redact or hash entity values in info logs; keep only counts and event metadata in non-debug mode.

### 3) Walkthrough/debug capture retains transcript content (MEDIUM)

Evidence:
- `_run_clean_format_job()` invokes `capture_stage()` comments indicate optional capture controlled by env and writes staged transcript/docx text artifacts under case directory.

Impact:
- Even within case folder, debug artifacts can increase retention of sensitive text beyond operational need and may be overlooked during case cleanup.

Bounded fix:
- Add TTL/cleanup toggle for walkthrough captures or gate capture to explicit debug builds only.

## False Alarms / Non-Issues

- **No global in-process cache of case entities** was identified in the reviewed modules; module constants are rule/config lexicons, not mutable per-case entity stores.
- **`job_config_manager` centralization is a safety feature**, not a contamination risk, because path derivation remains case-root bound.
- **`clean_format/prompt.py` includes generic legal guidance only** and does not hardcode any witness/attorney/provider identities.
- **Test fixtures under `tests/fixtures/` are explicitly test-scoped assets** and are not read by production path resolution logic.

## Recommended Bounded Fixes

1. Add cause-number collision guard when opening an existing case folder.
2. Reduce PII/entity verbosity in routine logs.
3. Add optional cleanup policy for walkthrough/debug captures.
4. Add one regression test ensuring two differently formatted but distinct cause identifiers cannot silently share the same active case without operator confirmation.

## Severity Classification

- Cause-folder collision by canonicalization: **HIGH**
- Logging of legal entities outside case artifacts: **MEDIUM**
- Walkthrough/debug retention: **MEDIUM**
- Residual UI in-memory state carryover after explicit case reset paths: **LOW**

## Do Not Change

- Keep layered split (`pipeline/` vs `clean_format/` vs `spec_engine/`) intact.
- Keep per-case folder artifact model.
- Keep deterministic correction and formatting rule stores as global static config/rule data.
- Keep `job_config_manager` as the single persistence gateway for `job_config.json`.
