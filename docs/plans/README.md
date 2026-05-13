# Plans Directory

Plans in this project are **implementation prompts** — structured natural-language instructions that an AI coding agent (or a human reader) can execute as a sequence of focused commits. Each plan covers one logical unit of work and lands as one or more git commits referenced in the plan's text.

## Directory layout

| Path | What lives here |
|---|---|
| `docs/plans/` (this directory, top level) | **Active or in-progress plans.** A plan stays at the top level while it is queued for execution or actively being worked on. |
| `docs/plans/_archive/` | **Executed plans.** Once the work referenced by a plan has landed in git, the plan moves here. The archive's own README links each plan to its landing commit(s). |

## How AI agents should use this directory

Per `.cursorrules` line 4: "Check `docs/plans/` for the active plan document. Plan files use the pattern `<topic>_<YYYY-MM-DD>.md` and the most recent dated plan covering the area you're touching is authoritative."

Apply that rule at this top level first. If no plan covers the area you're touching, no active plan exists for that area, and you should defer to `CLAUDE.md` and the audits under `docs/audits/`.

The `_archive/` directory is for historical context only — do not treat archived plans as authoritative for current work.

## Currently active plans

- `hygiene_stage1_archive_segregation.md` — the plan that produced this archive segregation (Stage 1 of `docs/reports/dead_module_hygiene_audit_2026-05-15.md`). This file itself will move into `_archive/` once Stage 1 is fully shipped.

No other active plans at this time.

## Authoring new plans

Follow the pattern: `<topic>_<YYYY-MM-DD>.md`. Include:

- Purpose / motivation.
- Exact file paths to be touched (FIND/REPLACE anchors when applicable).
- Stop conditions.
- Acceptance criteria.
- Commit message template.

When the plan's work has landed, move the file to `_archive/` and update `_archive/README.md` to record the landing commit(s).
