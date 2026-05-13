# Deterministic Formatting/Correction Audit (Non-AI)

Generated: 2026-04-28  
Scope: Python/regex/script-based formatting, punctuation, and correction paths only.

## Files Audited

- `spec_engine/corrections.py`
- `spec_engine/emitter.py`
- `spec_engine/parser.py`
- `spec_engine/classifier.py`
- `spec_engine/qa_fixer.py`
- `spec_engine/objections.py`
- `spec_engine/speaker_mapper.py`
- `spec_engine/processor.py`
- `core/correction_runner.py`

## Audit Summary

- Deterministic correction order remains intact (`clean_block` priority chain unchanged).
- No AI-dependent behavior was introduced in this pass.
- Existing deterministic modules already enforce strong separation of concerns:
  - `corrections.py`: text-only deterministic rewrites and punctuation normalization.
  - `classifier.py` / `qa_fixer.py`: structure decisions and Q/A recovery.
  - `emitter.py`: output formatting only.
  - `correction_runner.py`: orchestration only.

## Improvements Applied in This Pass

1. **Direct-address punctuation coverage expanded** in `corrections.py`.
   - Added deterministic support for:
     - `Yes your honor` → `Yes, Your Honor`
     - `No your honour` → `No, Your Honor`
   - Preserves existing behavior for already-comma-correct forms.

2. **Input-format detection hardening** in `parser.py`.
   - `detect_input_format()` now recognizes lowercase and indented Q/A lines.
   - This reduces false `FORMAT_UNKNOWN` outcomes for manually edited transcripts.

3. **Whitespace normalization hardening** in `emitter.py`.
   - `_clean()` now normalizes NBSP (`\xa0`) and narrow NBSP (`\u202f`) to plain spaces.
   - Prevents hidden non-ASCII spacing artifacts from leaking into output text.

## Test Additions

- Added deterministic tests for direct-address comma handling with `Your Honor`/`honour` variants.
- Added parser tests for lowercase and indented Q/A format detection.
- Added emitter test for NBSP and narrow-NBSP normalization.

## Notes

- This was a surgical pass focused only on deterministic non-AI logic.
- No refactor, no cross-layer movement, no AI prompt changes.
