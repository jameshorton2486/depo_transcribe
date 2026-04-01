"""
core/config.py

Shared core-layer constants for Depo-Pro.

This module is intentionally separate from the repo-root config.py:
- config.py handles active runtime/pipeline settings and API integration values
- core/config.py handles reusable core constants consumed across core modules

Never scatter these values across files — import from here.
If a value needs to change (model upgrade, schema version bump, etc.)
it changes in one place and takes effect everywhere.
"""

# ── AI Model ──────────────────────────────────────────────────────────────────
# Used by core/intake_parser.py and core/pdf_extractor.py
AI_MODEL = "claude-sonnet-4-6"

# ── Job Config File ───────────────────────────────────────────────────────────
# Single source-of-truth file per deposition case.
# Location: {case_root}/source_docs/job_config.json
# Behavior: always overwrite — never create timestamped duplicates.
JOB_CONFIG_FILENAME = "job_config.json"
JOB_CONFIG_DIR      = "source_docs"
JOB_CONFIG_VERSION  = 1          # increment when schema changes

# ── Deepgram Keyterms ─────────────────────────────────────────────────────────
# Deepgram Nova-3 hard cap is 100 terms per request.
# MIN_TERM_LENGTH filters noise (single letters, two-char fragments).
# Both values are imported by core/keyterm_extractor.py — change here only.
MAX_KEYTERMS    = 100
MIN_TERM_LENGTH = 3
