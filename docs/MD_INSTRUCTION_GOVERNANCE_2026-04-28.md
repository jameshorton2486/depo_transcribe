# Markdown Instruction Governance Audit (Consolidated)

Generated: 2026-04-28  
Scope: all tracked `*.md` files in this repository.

## Purpose

This document consolidates instruction precedence for markdown guidance and
records whether any markdown files currently conflict on instructions that
could change application behavior.

## Instruction Precedence (Authoritative Order)

1. `CLAUDE.md` (single source of truth for architecture/invariants).
2. Pointer files that explicitly defer to `CLAUDE.md`:
   - `AGENTS.md`
   - `README_AI.md`
   - `.github/copilot-instructions.md`
   - `README.md` (AI instructions section)
3. Active standards and plans:
   - `docs/transcription_standards/depo_pro_style.md`
   - `STABILIZATION_PLAN.md`
4. Historical/diagnostic/reference markdown files (non-authoritative unless
   manually promoted and reconciled with `CLAUDE.md`).

If any file conflicts with `CLAUDE.md`, `CLAUDE.md` wins.

## Audit Result

**Result: No active instruction conflicts found among authoritative files.**

Most historical files that previously contained conflicting guidance are already
explicitly marked with `STATUS: SUPERSEDED`, `STATUS: HISTORICAL`, or
`STATUS: REFERENCE ONLY` banners.

## File-by-File Classification

### A) Authoritative / Active

| File | Role | Conflict status |
|---|---|---|
| `CLAUDE.md` | Canonical AI operating rules and invariants | N/A (authority) |
| `AGENTS.md` | Root assistant pointer to `CLAUDE.md` | No conflict |
| `README.md` | Human/project README with AI pointer | No conflict |
| `README_AI.md` | AI pointer | No conflict |
| `.github/copilot-instructions.md` | Copilot pointer | No conflict |
| `docs/transcription_standards/depo_pro_style.md` | House style authority (UFM-cited) | No conflict (already aligned with `CLAUDE.md`) |
| `STABILIZATION_PLAN.md` | Active phased plan | No conflict |
| `spec_engine/SPEAKER_LABEL_RULES.md` | Active domain behavior guidance | No conflict |
| `training_corpus/README.md` | Corpus handling policy | No conflict |
| `spec_engine/tests/golden/README.md` | Golden test fixture contract | No conflict |
| `backups/README.md` | Explicitly states backups are non-runtime | No conflict |

### B) Historical / Diagnostic / Superseded (Non-authoritative)

| File | Status marker present? | Risk of misuse |
|---|---:|---|
| `FIX_REMOVE_HARD_WRAPPING.md` | Yes (`SUPERSEDED`) | Low |
| `TRANSCRIPT_CORRECTION_RULES (2).md` | Yes (`SUPERSEDED`) | Low |
| `PIPELINE_AUDIT_2026-04-04.md` | Yes (`HISTORICAL`) | Low |
| `SAFE_PIPELINE_AUDIT_PROMPT.md` | Yes (`REFERENCE ONLY`) | Low |
| `docs/_archive/FORMATTING_AUDIT_AND_RULES.md` | Yes (`SUPERSEDED`) | Low |
| `docs/_archive/FORMATTING_AUDIT_GUIDE.md` | Yes (`SUPERSEDED`) | Low |
| Dated diagnostics/analyses (`*_2026-04-27.md`) | Date-scoped diagnostic context | Low |
| `docs/verifications/phase_h_double_spacing_2026-04-27.md` | Verification snapshot | Low |
| `md_audit_2026-04-27.md` | Prior read-only markdown audit | Low |

## Consolidation Actions Applied in This Pass

- Added this consolidated governance file.
- Updated AI-pointer markdown files to explicitly reference this governance
  file in addition to `CLAUDE.md`, so agents get one centralized policy map.

## Ongoing Rule for New Markdown Files

When adding any new instruction-bearing markdown file:

1. Add a `Status` line (`ACTIVE`, `REFERENCE`, `HISTORICAL`, `SUPERSEDED`).
2. If `ACTIVE`, state its precedence relative to `CLAUDE.md`.
3. If `REFERENCE`/`HISTORICAL`/`SUPERSEDED`, include "Do not use as
   authoritative runtime instruction" wording.

