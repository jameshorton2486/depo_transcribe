# Merge-Run Comparison — `TEST_A_CURRENT` vs `TEST_D_VERY_TIGHT`

- Run A: `C:\Users\james\PycharmProjects\depo_transcribe\docs\investigations\merge_threshold_testing\runs\etminan_mohammad\TEST_A_CURRENT`
- Run B: `C:\Users\james\PycharmProjects\depo_transcribe\docs\investigations\merge_threshold_testing\runs\etminan_mohammad\TEST_D_VERY_TIGHT`

## Configuration

| Field | A | B |
|---|---|---|
| name | TEST_A_CURRENT | TEST_D_VERY_TIGHT |
| in_chunk_gap (s) | 0.6 | 0.4 |
| cross_chunk_gap (s) | 1.25 | 0.5 |

## Structure

| Metric | A | B | Δ |
|---|---:|---:|---:|
| utterance_count | 354 | 576 | +222 |
| long_utterance_count (>30s) | 35 | 5 | -30 |
| over_100_words_count | 20 | 4 | -16 |
| merged_qa_candidates | 77 | 93 | +16 |
| speaker_transition_inside_utterance | 101 | 110 | +9 |
| standalone_short_answers | 4 | 4 | 0 |
| avg duration (s) | 12.168 | 7.174 | -4.99 |
| max duration (s) | 101.63 | 84.125 | -17.5 |
| avg words/utt | 34.35 | 21.11 | -13.24 |
| max words/utt | 296 | 242 | -54 |

## Classifier (spec_engine)

| Type | A | B | Δ |
|---|---:|---:|---:|
| colloquy | 353 | 575 | +222 |
| oath | 1 | 1 | 0 |
| total_blocks | 354 | 576 | +222 |

## Read-out

Going from `TEST_A_CURRENT` (in/cross = 0.6/1.25) to `TEST_D_VERY_TIGHT` (in/cross = 0.4/0.5):

- Utterance count: 354 → 576 (+62.7%).
- Suspicious merged-Q/A: 77 → 93 (+16).
- Standalone witness short answers preserved: 4 → 4 (+0).
