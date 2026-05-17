# UFM Rule Implementation (Deterministic)

Scope: regex-only Q/A prefix normalization and tab enforcement.

- `is_qa_formatted(line)` checks canonical `\tQ.\t` / `\tA.\t` shape.
- `normalize_qa_line(line)` converts malformed `Q:` / `A:` / spacing variants to canonical tabs.
- `enforce_qa_tabs(line)` applies canonical tab formatting for Q/A prefixed lines.

Safety:
- No semantic rewriting.
- Body text preserved verbatim aside from outer whitespace trimming.
