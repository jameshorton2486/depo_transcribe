# Merge-Run Comparison — `TEST_A_CURRENT` vs `TEST_B_MODERATE`

- Run A: `C:\Users\james\PycharmProjects\depo_transcribe\docs\investigations\merge_threshold_testing\runs\etminan_mohammad\TEST_A_CURRENT`
- Run B: `C:\Users\james\PycharmProjects\depo_transcribe\docs\investigations\merge_threshold_testing\runs\etminan_mohammad\TEST_B_MODERATE`

## Configuration

| Field | A | B |
|---|---|---|
| name | TEST_A_CURRENT | TEST_B_MODERATE |
| in_chunk_gap (s) | 0.6 | 0.6 |
| cross_chunk_gap (s) | 1.25 | 0.9 |

## Structure

| Metric | A | B | Δ |
|---|---:|---:|---:|
| utterance_count | 354 | 419 | +65 |
| long_utterance_count (>30s) | 35 | 19 | -16 |
| over_100_words_count | 20 | 11 | -9 |
| merged_qa_candidates | 77 | 85 | +8 |
| speaker_transition_inside_utterance | 101 | 105 | +4 |
| standalone_short_answers | 4 | 4 | 0 |
| avg duration (s) | 12.168 | 10.115 | -2.05 |
| max duration (s) | 101.63 | 101.63 | 0 |
| avg words/utt | 34.35 | 29.02 | -5.33 |
| max words/utt | 296 | 296 | 0 |

## Classifier (spec_engine)

| Type | A | B | Δ |
|---|---:|---:|---:|
| colloquy | 353 | 418 | +65 |
| oath | 1 | 1 | 0 |
| total_blocks | 354 | 419 | +65 |

## Read-out

Going from `TEST_A_CURRENT` (in/cross = 0.6/1.25) to `TEST_B_MODERATE` (in/cross = 0.6/0.9):

- Utterance count: 354 → 419 (+18.4%).
- Suspicious merged-Q/A: 77 → 85 (+8).
- Standalone witness short answers preserved: 4 → 4 (+0).
