# Regex Rule Engine

This module family provides deterministic regex primitives and safe wrappers:

- `spec_engine/regex_patterns.py`
- `spec_engine/ufm_rules.py`
- `spec_engine/morson_rules.py`
- `spec_engine/punctuation_rules.py`
- `spec_engine/legal_dictionary.py`

Design constraints:
- Ordered, auditable, testable.
- Formatting-only transformations.
- No transcript semantic mutations.
