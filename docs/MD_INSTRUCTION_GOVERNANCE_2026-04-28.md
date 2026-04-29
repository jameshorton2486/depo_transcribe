# Markdown Instruction Governance

Generated: 2026-04-29

## Current precedence

1. `CLAUDE.md`
2. `AGENTS.md`
3. `README_AI.md`
4. `README.md`

If markdown guidance conflicts, `CLAUDE.md` wins.

## Current-state note

The legacy correction architecture and its planning/diagnostic markdown files
were removed during the clean-format migration. The active architecture is now:

- `pipeline/` for audio preprocessing and Deepgram transcription
- `clean_format/` for Anthropic cleanup and DOCX generation
- `ui/tab_transcribe.py` as the visible desktop workflow

## Rule for new markdown files

If a markdown file contains instructions that could affect code changes:

1. Keep it short.
2. State whether it is active or historical.
3. Defer to `CLAUDE.md` unless there is a documented reason not to.
