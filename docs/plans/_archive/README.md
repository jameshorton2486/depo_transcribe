# Archived Plans

Each file in this directory is an implementation prompt that has been executed. The actual work landed via commits referenced in the plan's frontmatter or findable via `git log --grep=<step name>`. These are historical artifacts preserved for context, not active work items.

## What lives here

Plans for the verbatim-punctuation series (Steps A through E) plus the Phase 2A hygiene + post-release passes, all dated 2026-05-12:

| Plan | Landing commit(s) |
|---|---|
| `verbatim_punctuation_plan_2026-05-12.md` | master plan; covered by the step commits below |
| `step_a_corrections_cleanup_2026-05-12.md` | `40be155`, `e235d5e` |
| `step_b0_word_carry_2026-05-12.md` | `3530abf` |
| `step_b1_word_carry_merge_split_2026-05-12.md` | `dfda8c1` |
| `step_c_low_confidence_markers_2026-05-12.md` | `d7a45f4` |
| `step_d_yellow_highlight_rendering_2026-05-12.md` | `558e740` |
| `step_e_production_wiring_2026-05-12.md` | `7b66c68`, drift policy `601b943` |
| `audit_hygiene_pass_2026-05-12.md` | `164fd18` |
| `post_release_cleanup_2026-05-12.md` | `f820eee` (Phase 1 no-op), `a16abb2` (Phase 2), `24ebc70` (Phase 3) |

## Reading these

Plans contain implementation prompts as they were written at the time, including absolute paths and assumptions about repo state at that point. **Do not treat them as authoritative for current architecture.** Specifically:

- File paths and module names reflect the state at write-time, not after subsequent refactors.
- Internal cross-references between plans use the pre-archive paths (`docs/plans/<name>.md`). They are not updated to point at `docs/plans/_archive/<name>.md`. This is intentional — these files are historical artifacts.
- For current authority on architecture, wiring, and verification, see:
  - `docs/audits/ACTIVE_PATH_AUDIT.md`
  - `docs/architecture/PHASE_2A_KNOWN_LIMITATIONS.md`
  - `CLAUDE.md`

## Active plans

Active (work-in-progress) plans live at the top level of `docs/plans/`. See `docs/plans/README.md`.
