from spec_engine.paragraph_splitter import split_block_text


def test_no_split_short_text():
    text = "Q. Hello."
    result = split_block_text(text)

    assert result == ["Q. Hello."]


def test_sentence_split():
    text = (
        "This is a sentence that is intentionally long enough to exceed the threshold for splitting in a deposition-style paragraph with added context. "
        "This is another sentence."
    )
    result = split_block_text(text)

    assert result == [
        "This is a sentence that is intentionally long enough to exceed the threshold for splitting in a deposition-style paragraph with added context.",
        "This is another sentence.",
    ]


def test_embedded_qa_split():
    text = (
        "You understand this is under oath and that your answers carry the same force and effect as testimony in court. "
        "Correct? Correct."
    )
    result = split_block_text(text)

    assert result == [
        "You understand this is under oath and that your answers carry the same force and effect as testimony in court.",
        "Correct?",
        "Correct.",
    ]


def test_no_false_positive_split():
    text = (
        "Dr. Smith was present for the deposition and remained in the room through the break while counsel discussed scheduling and exhibit handling. "
        "He testified."
    )
    result = split_block_text(text)

    assert result == [
        "Dr. Smith was present for the deposition and remained in the room through the break while counsel discussed scheduling and exhibit handling.",
        "He testified.",
    ]


def test_real_transcript_case():
    text = (
        "I'm sure you've spoken with your lawyer about what today would entail, "
        "but just so you and I are on the same page, you understand your testimony "
        "today has the same effect as a weapon in the courthouse. Correct? Correct."
    )

    result = split_block_text(text)

    assert result[-2:] == ["Correct?", "Correct."]
