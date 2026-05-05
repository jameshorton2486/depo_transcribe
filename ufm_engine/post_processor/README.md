# UFM Post-Processor

Applies the UFM format box and line numbers to a populated `.docx` file.

Pipeline B: templates ship without these elements; this component adds
them at finish time.

## Contract

- Pure structural transform: NEVER modifies text.
- Idempotent.
- Text-preservation is enforced by tests.

## Status

Implemented. Contract tests in `tests/ufm_engine/test_post_processor.py`
verify text preservation, idempotence, format-box presence, line-number
gutter, and firm-footer behavior.

## Why this exists

Some agencies add the format box and line numbers themselves after
receiving the reporter's deliverable. By keeping the chassis out of the
templates and applying it post-populate, this app supports both
workflows: agencies that want UFM-compliant output get it via this
post-processor; reporters who hand off plain transcripts can skip it.
