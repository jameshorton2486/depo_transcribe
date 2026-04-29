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
