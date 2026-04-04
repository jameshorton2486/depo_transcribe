from spec_engine.display_formatter import (
    format_blocks,
    is_question,
    normalize_speaker,
    two_space_fix,
)


def test_is_question_false_for_blank_text():
    assert is_question("") is False


def test_two_space_fix_normalizes_sentence_spacing():
    assert two_space_fix("Hello. there? yes!") == "Hello.  there?  yes!"


def test_normalize_speaker_maps_reporter_and_witness():
    assert normalize_speaker(0) == "THE REPORTER"
    assert normalize_speaker(1) == "THE WITNESS"


def test_normalize_speaker_does_not_use_substring_matching():
    assert normalize_speaker(10) == "SPEAKER 10"
    assert normalize_speaker(11) == "SPEAKER 11"


def test_format_blocks_applies_question_answer_and_speaker_display():
    blocks = [
        {"speaker": 1, "text": "Where are you located today?"},
        {"speaker": 2, "text": "1210 B Ash Street."},
        {"speaker": 0, "text": "Let's go on the record."},
    ]

    assert format_blocks(blocks) == (
        "Q.  Where are you located today?\n"
        "A.  1210 B Ash Street.\n"
        "THE REPORTER:  Let's go on the record."
    )
