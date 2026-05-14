# Merge-Run Comparison — `TEST_A_CURRENT` vs `TEST_C_TIGHT`

- Run A: `C:\Users\james\PycharmProjects\depo_transcribe\docs\investigations\merge_threshold_testing\runs\etminan_mohammad\TEST_A_CURRENT`
- Run B: `C:\Users\james\PycharmProjects\depo_transcribe\docs\investigations\merge_threshold_testing\runs\etminan_mohammad\TEST_C_TIGHT`

## Configuration

| Field | A | B |
|---|---|---|
| name | TEST_A_CURRENT | TEST_C_TIGHT |
| in_chunk_gap (s) | 0.6 | 0.6 |
| cross_chunk_gap (s) | 1.25 | 0.6 |

## Structure

| Metric | A | B | Δ |
|---|---:|---:|---:|
| utterance_count | 354 | 523 | +169 |
| long_utterance_count (>30s) | 35 | 6 | -29 |
| over_100_words_count | 20 | 5 | -15 |
| merged_qa_candidates | 77 | 92 | +15 |
| speaker_transition_inside_utterance | 101 | 110 | +9 |
| standalone_short_answers | 4 | 4 | 0 |
| avg duration (s) | 12.168 | 7.957 | -4.21 |
| max duration (s) | 101.63 | 84.125 | -17.5 |
| avg words/utt | 34.35 | 23.25 | -11.1 |
| max words/utt | 296 | 242 | -54 |

## Classifier (spec_engine)

| Type | A | B | Δ |
|---|---:|---:|---:|
| colloquy | 353 | 522 | +169 |
| oath | 1 | 1 | 0 |
| total_blocks | 354 | 523 | +169 |

## Read-out

Going from `TEST_A_CURRENT` (in/cross = 0.6/1.25) to `TEST_C_TIGHT` (in/cross = 0.6/0.6):

- Utterance count: 354 → 523 (+47.7%).
- Suspicious merged-Q/A: 77 → 92 (+15).
- Standalone witness short answers preserved: 4 → 4 (+0).
