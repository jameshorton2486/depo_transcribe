| patch_stage | cumulative_utterance_retention | cumulative_token_retention | chunks_falling_back | notes |
| --- | --- | --- | --- | --- |
| Pre-Patch-1 | n/a | n/a | n/a | Heath Thomas fixture unavailable for measurement in this workspace; `THOMAS_CASE_DIR` unset. |
| Post-Patch-1 | n/a | n/a | n/a | Heath Thomas fixture unavailable for measurement in this workspace; `THOMAS_CASE_DIR` unset. |
| Post-Patch-2 | 12.6% | n/a | 0 | Thomas fixture unavailable; canonical raw fixture shape used with synthetic under-retained output. Gate fired at 140/1113 utterances on the document-level check. |
| Post-Patch-3 | 100.0% | n/a | 0 | Success-path proof used canonical raw fixture with clean fake-client pass-through via `format_transcript_with_status`; returned populated retention counts and success status. |
