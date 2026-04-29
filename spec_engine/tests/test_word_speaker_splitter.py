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
