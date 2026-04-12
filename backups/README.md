ARCHIVED BACKUPS

These files are retained only as historical snapshots from earlier cleanup passes.
They are not part of the active application runtime and may contradict current
repository behavior, tests, or provider requirements.

Important:
- Do not import code from `backups/` into the live app.
- Do not use archived Deepgram guidance here as current guidance.
- For Nova-3, the active codebase uses Deepgram `keyterm` prompting, not the
  older `keywords` approach.

Authoritative sources for current behavior:
- `CLAUDE.md`
- `pipeline/transcriber.py`
- `ui/tab_transcribe.py`
- tests under `pipeline/tests/`, `core/tests/`, and `spec_engine/tests/`
