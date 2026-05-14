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


def test_directive_requires_trailing_colon_for_by_prefix():
    """Defect #11: 'By' as English preposition (no trailing colon) must
    not be classified as directive. Previously this cascaded through
    qa_fixer._directive_examiner_name to corrupt examiner attribution
    on subsequent question blocks.
    """
    blocks = classify_blocks([
        {"speaker": "speaker 1",
         "text": "By putting around 20 windows on the sheet cart?",
         "type": "paragraph"},
    ])
    assert len(blocks) == 1
    assert blocks[0].type != "directive"


def test_directive_byline_with_colon_still_classified():
    """Canonical BY-line section headers (with trailing colon) must
    still classify as directive. Protects the legitimate path.
    """
    blocks = classify_blocks([
        {"speaker": "speaker 1", "text": "BY MR. NUNEZ:", "type": "paragraph"},
        {"speaker": "speaker 2", "text": "BY MS. ZHAN:", "type": "paragraph"},
        {"speaker": "speaker 3", "text": "by mr. ragan:", "type": "paragraph"},
    ])
    assert blocks[0].type == "directive"
    assert blocks[1].type == "directive"
    assert blocks[2].type == "directive"


def test_directive_rejects_by_prefix_without_colon():
    """Various 'By <something>' constructions that are English prose,
    not BY-line directives. None should classify as directive.
    """
    inputs = [
        "By the way, what's your name?",
        "By any chance, did you see it?",
        "By all means, please continue.",
        "By definition, that's not possible.",
    ]
    for text in inputs:
        blocks = classify_blocks([
            {"speaker": "speaker 1", "text": text, "type": "paragraph"},
        ])
        assert blocks[0].type != "directive", (
            f"{text!r} was incorrectly classified as directive"
        )


def test_directive_accepts_tab_separator_with_colon():
    """The BY\t variant (tab instead of space) is preserved from the
    original implementation. Must still require trailing colon.
    """
    blocks = classify_blocks([
        {"speaker": "speaker 1", "text": "BY\tMR. NUNEZ:", "type": "paragraph"},
        {"speaker": "speaker 2", "text": "BY\tMR. NUNEZ", "type": "paragraph"},
    ])
    assert blocks[0].type == "directive"
    assert blocks[1].type != "directive"
