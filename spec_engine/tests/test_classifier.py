from spec_engine.classifier import classify_blocks
from spec_engine.speaker_mapper import normalize_speaker_label


def test_classify_assigns_structural_types():
    blocks = classify_blocks(
        [
            {
                "speaker": "speaker 1",
                "text": "\tQ.\tState your name.",
                "type": "paragraph",
            },
            {
                "speaker": "speaker 2",
                "text": "\tA.\tBianca Caram.",
                "type": "paragraph",
            },
            {"speaker": "speaker 3", "text": "BY MS. MALONEY:", "type": "paragraph"},
            {
                "speaker": "court reporter",
                "text": "Do you solemnly swear the testimony you give is true?",
                "type": "paragraph",
            },
            {
                "speaker": "videographer",
                "text": "Today's date is April 9, 2026.",
                "type": "paragraph",
            },
        ]
    )

    assert [block.type for block in blocks] == [
        "question",
        "answer",
        "directive",
        "oath",
        "colloquy",
    ]


def test_normalize_speaker_label_uppercases_and_normalizes_colon():
    assert normalize_speaker_label("Ms. Maloney;; ") == "MS. MALONEY:"
