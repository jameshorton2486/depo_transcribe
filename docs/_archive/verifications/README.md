# Archived Verifications

These reports describe earlier states of the repository. They are preserved here for historical reference but should not be treated as authoritative for current architecture.

**For current authority:**
- Active-path import graph and module wiring: `docs/audits/ACTIVE_PATH_AUDIT.md`
- Pipeline-stage verification: `docs/audits/CASE_PIPELINE_VERIFICATION_REPORT.md`
- Per-token mutation/correction analysis: `docs/audits/CASE_MUTATION_REPORT.md`, `docs/audits/PHASE_2A_CORRECTION_APPLICATION.md`
- Known architectural limitations: `docs/architecture/PHASE_2A_KNOWN_LIMITATIONS.md`

**Specific contradictions between these archived reports and the current code** are catalogued in `docs/reports/dead_module_hygiene_audit_2026-05-15.md` Sections 4.1–4.3 and 4.9. The most consequential: the 2026-05-09 and 2026-05-12 pipeline reports claim `pipeline/exporter.py` is wired into `core/job_runner.py`. It is not — see the active-path audit. The 2026-04-28 deterministic-corrections audit references three modules (`spec_engine/parser.py`, `spec_engine/objections.py`, `core/correction_runner.py` singular) that no longer exist.

AI agents: defer to the audits and architecture docs above. The files in this directory describe history, not current state.
