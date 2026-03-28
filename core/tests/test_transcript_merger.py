from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.transcript_merger import merge_utterances


def test_merge_utterances_combines_same_speaker_with_short_gap():
    utterances = [
        {"speaker": 0, "transcript": "Today's date is 03/24/2026.", "start": 0.0, "end": 2.0, "words": []},
        {"speaker": 0, "transcript": "The time is 10:08AM.", "start": 2.4, "end": 3.8, "words": []},
    ]

    merged = merge_utterances(utterances, gap_threshold_seconds=1.5, min_word_count=2)

    assert len(merged) == 1
    assert merged[0]["speaker"] == 0
    assert merged[0]["transcript"] == "Today's date is 03/24/2026. The time is 10:08AM."


def test_merge_utterances_flags_short_cross_speaker_utterance():
    utterances = [
        {"speaker": 0, "transcript": "Matthew Coger.", "start": 0.0, "end": 1.0, "words": []},
        {"speaker": 1, "transcript": "Coger.", "start": 1.2, "end": 1.4, "words": []},
    ]

    merged = merge_utterances(utterances, gap_threshold_seconds=1.5, min_word_count=2)

    assert len(merged) == 2
    assert merged[1]["flagged"] is True
    assert merged[1]["flag_reason"] == "short_utterance_possible_diarization_error"
