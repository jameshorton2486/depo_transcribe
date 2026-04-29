from spec_engine.models import Block, Word
from spec_engine.word_speaker_splitter import split_mixed_speaker_utterances


def test_split_mixed_speaker_utterances_splits_runs_and_preserves_order():
    block = Block(
        text="Question Yes Okay",
        raw_text="Question Yes Okay",
        speaker_id=1,
        words=[
            Word(text="Question", speaker=1),
            Word(text="Yes", speaker=0),
            Word(text="Okay", speaker=0),
        ],
    )

    result = split_mixed_speaker_utterances([block])

    assert [b.speaker_id for b in result] == [1, 0]
    assert [b.text for b in result] == ["Question", "Yes Okay"]
    assert result[1].meta.get("split_reason") == "per_word_speaker_drift"
    assert result[1].meta.get("split_from_word_speaker") is True


def test_split_mixed_speaker_utterances_keeps_block_without_word_speakers():
    block = Block(
        text="Single speaker block",
        raw_text="Single speaker block",
        speaker_id=2,
        words=[Word(text="Single", speaker=None), Word(text="speaker", speaker=None)],
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 1
    assert result[0] is block


def test_single_word_foreign_noise_is_consolidated_not_split():
    block = Block(
        text="Question um And",
        raw_text="Question um And",
        speaker_id=1,
        words=[
            Word(text="Question", speaker=1, start=0.0, end=0.5),
            Word(text="um", speaker=0, start=0.5, end=0.7),
            Word(text="And", speaker=1, start=0.7, end=0.9),
        ],
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 1
    assert result[0] is block


def test_splitter_does_not_duplicate_block_level_corrections_across_fragments():
    block = Block(
        text="Question Yes",
        raw_text="Question Yes",
        speaker_id=1,
        words=[Word(text="Question", speaker=1), Word(text="Yes", speaker=0)],
        meta={"corrections": [{"pattern": "example"}]},
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 2
    assert result[0].meta.get("corrections") == [{"pattern": "example"}]
    assert result[0].meta.get("split_reason") == "per_word_speaker_drift"
    assert result[1].meta.get("split_reason") == "per_word_speaker_drift"
    assert result[1].meta.get("split_from_word_speaker") is True
    assert "corrections" not in result[1].meta


def test_splitter_retags_unanimous_word_speaker_disagreement_without_mutating_input():
    block = Block(
        text="That is correct.",
        raw_text="That is correct.",
        speaker_id=1,
        words=[Word(text="That", speaker=0), Word(text="is", speaker=0), Word(text="correct.", speaker=0)],
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 1
    assert result[0].speaker_id == 0
    assert result[0].meta.get("split_reason") == "per_word_speaker_retag"
    assert result[0].meta.get("split_from_word_speaker") is True
    assert result[0].meta.get("original_block_speaker_id") == 1
    assert block.speaker_id == 1


def test_splitter_keeps_matching_unanimous_blocks_unchanged():
    block = Block(
        text="Yes.",
        raw_text="Yes.",
        speaker_id=0,
        words=[Word(text="Yes.", speaker=0)],
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 1
    assert result[0] is block
    assert "split_reason" not in result[0].meta


def test_splitter_preserves_timing_and_metadata_across_fragments():
    block = Block(
        text="Question Yes Okay And",
        raw_text="Question Yes Okay And",
        speaker_id=1,
        words=[
            Word(text="Question", speaker=1, start=1.0, end=1.4),
            Word(text="Yes", speaker=0, start=1.4, end=1.5),
            Word(text="Okay", speaker=0, start=1.5, end=1.8),
            Word(text="And", speaker=1, start=1.8, end=2.0),
        ],
        meta={"confidence": 0.91, "corrections": [{"pattern": "example"}]},
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 3
    assert [b.speaker_id for b in result] == [1, 0, 1]
    assert [b.text for b in result] == ["Question", "Yes Okay", "And"]
    assert result[0].meta["start"] == 1.0
    assert result[0].meta["end"] == 1.4
    assert result[1].meta["start"] == 1.4
    assert result[1].meta["end"] == 1.8
    assert result[2].meta["start"] == 1.8
    assert result[2].meta["end"] == 2.0
    assert result[1].meta.get("split_from_word_speaker") is True
    assert "corrections" not in result[1].meta


def test_splitter_handles_three_speaker_interleaving():
    block = Block(
        text="A B C D E F",
        raw_text="A B C D E F",
        speaker_id=1,
        words=[
            Word(text="A", speaker=1),
            Word(text="B", speaker=2),
            Word(text="C", speaker=2),
            Word(text="D", speaker=0),
            Word(text="E", speaker=0),
            Word(text="F", speaker=1),
        ],
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 4
    assert [b.speaker_id for b in result] == [1, 2, 0, 1]
    assert [b.text for b in result] == ["A", "B C", "D E", "F"]


def test_caram_full_invariants_in_one_block():
    """
    Production-shaped regression:
    one attorney -> witness -> attorney block must preserve speaker order,
    avoid duplicate corrections metadata, propagate timing to every fragment,
    and keep split audit shape on each derived block.
    """
    attorney_open = [
        Word(text="Is", start=10.0, end=10.10, confidence=0.95, speaker=1),
        Word(text="this", start=10.10, end=10.25, confidence=0.95, speaker=1),
        Word(text="your", start=10.25, end=10.40, confidence=0.94, speaker=1),
        Word(text="sole", start=10.40, end=10.60, confidence=0.93, speaker=1),
        Word(text="documentation?", start=10.60, end=11.10, confidence=0.92, speaker=1),
    ]
    witness_answer = [
        Word(text="Yes.", start=11.30, end=11.50, confidence=0.96, speaker=0),
        Word(text="Okay.", start=11.55, end=11.75, confidence=0.94, speaker=0),
    ]
    attorney_followup = [
        Word(text="And", start=11.95, end=12.05, confidence=0.95, speaker=1),
        Word(text="you", start=12.05, end=12.15, confidence=0.95, speaker=1),
        Word(text="documented", start=12.15, end=12.50, confidence=0.93, speaker=1),
        Word(text="this", start=12.50, end=12.65, confidence=0.94, speaker=1),
        Word(text="on", start=12.65, end=12.75, confidence=0.95, speaker=1),
        Word(text="October", start=12.75, end=13.05, confidence=0.92, speaker=1),
        Word(text="3?", start=13.05, end=13.25, confidence=0.91, speaker=1),
    ]
    all_words = attorney_open + witness_answer + attorney_followup
    block = Block(
        text=" ".join(word.text for word in all_words),
        speaker_id=1,
        raw_text=" ".join(word.text for word in all_words),
        words=all_words,
        meta={
            "corrections": [
                {"original": "Karam", "corrected": "Caram", "pattern": "confirmed_spellings"},
                {"original": "doctor", "corrected": "Doctor", "pattern": "title_case"},
            ],
            "start": 10.0,
            "end": 13.25,
            "confidence": 0.93,
        },
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 3
    assert [b.speaker_id for b in result] == [1, 0, 1]
    assert [b.text for b in result] == [
        "Is this your sole documentation?",
        "Yes. Okay.",
        "And you documented this on October 3?",
    ]

    retained_corrections = [b for b in result if b.meta.get("corrections")]
    assert len(retained_corrections) == 1
    assert retained_corrections[0].meta["corrections"] == [
        {"original": "Karam", "corrected": "Caram", "pattern": "confirmed_spellings"},
        {"original": "doctor", "corrected": "Doctor", "pattern": "title_case"},
    ]
    for fragment in result:
        assert fragment.meta.get("split_reason") == "per_word_speaker_drift"
        assert fragment.meta.get("start") is not None
        assert fragment.meta.get("end") is not None

    assert result[0].meta["start"] == 10.0
    assert result[0].meta["end"] == 11.10
    assert result[1].meta["start"] == 11.30
    assert result[1].meta["end"] == 11.75
    assert result[2].meta["start"] == 11.95
    assert result[2].meta["end"] == 13.25
    assert result[1].meta.get("split_from_word_speaker") is True
    assert "corrections" not in result[1].meta
    assert block.speaker_id == 1
    assert block.meta["start"] == 10.0
    assert block.meta["end"] == 13.25


def test_retag_path_propagates_timing_metadata():
    block = Block(
        text="That is correct.",
        raw_text="That is correct.",
        speaker_id=1,
        words=[
            Word(text="That", start=20.0, end=20.20, confidence=0.95, speaker=0),
            Word(text="is", start=20.20, end=20.30, confidence=0.96, speaker=0),
            Word(text="correct.", start=20.30, end=20.70, confidence=0.93, speaker=0),
        ],
        meta={"start": 20.0, "end": 20.70, "confidence": 0.94},
    )

    result = split_mixed_speaker_utterances([block])

    assert len(result) == 1
    assert result[0].speaker_id == 0
    assert result[0].meta.get("split_reason") == "per_word_speaker_retag"
    assert result[0].meta.get("split_from_word_speaker") is True
    assert result[0].meta.get("original_block_speaker_id") == 1
    assert result[0].meta.get("start") == 20.0
    assert result[0].meta.get("end") == 20.70
