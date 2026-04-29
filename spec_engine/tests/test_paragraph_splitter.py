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


# ── Phase D — initial-awareness fix ──────────────────────────────────────────
# SENTENCE_SPLIT_RE treats any "[.?!] + whitespace + capital" as a sentence
# boundary. Single-letter initials inside names ("Holly D. Scholl",
# "J. K. Rowling") match this exactly, so the splitter was breaking
# mid-name. Fix: INITIAL_RE protects "<single uppercase>.<space><capital>"
# patterns by replacing the dot with the same __DOT__ placeholder used for
# multi-letter abbreviations. Lookahead in the regex avoids consuming the
# trailing capital so consecutive initials (J. K.) are caught in one pass.
#
# All inputs below are >120 chars so they exceed split_block_text's
# short-text guard. CorrectionRecord assertion not applicable —
# the splitter returns a list and does not log to the corrections audit
# trail.


def test_holly_d_scholl_stays_whole():
    text = (
        "There were several attorneys present today, including Mary Mauricio "
        "Pena, Holly D. Scholl, and counsel for the defendant. I represent "
        "the plaintiff in this matter."
    )
    result = split_block_text(text)

    # Two blocks: everything up to and including "defendant.", then the
    # next sentence. The middle name "Holly D. Scholl" must NOT be split.
    assert len(result) == 2
    assert "Holly D. Scholl" in result[0]
    # The buggy output produced a "Scholl, and counsel..." standalone
    # block — guard against that regression.
    assert not any(block.startswith("Scholl") for block in result)


def test_j_k_rowling_multi_initial_stays_whole():
    text = (
        "We have an exhibit from a book authored by J. K. Rowling, which "
        "the witness reviewed before the deposition began. The witness "
        "agreed to its authenticity."
    )
    result = split_block_text(text)

    assert len(result) == 2
    # Both initials and the surname must be in the same block.
    assert "J. K. Rowling" in result[0]
    # Pre-fix produced standalone "K." or "Rowling, which..." blocks.
    assert not any(block.strip() == "K." for block in result)
    assert not any(block.startswith("K.") for block in result)


def test_normal_sentence_split_still_works():
    # Regression guard — the patch must not affect plain sentence splits
    # where no initials are involved.
    text = (
        "He went to the store and picked up groceries before driving back "
        "to the office for the meeting that had been scheduled. She came "
        "home later that evening after the meeting concluded."
    )
    result = split_block_text(text)

    assert len(result) == 2
    assert result[0].endswith("scheduled.")
    assert result[1].startswith("She came home")


def test_dr_smith_abbreviation_still_protected():
    # Regression guard — the patch must not regress the existing
    # multi-letter abbreviation protection (Dr. / Mr. / etc).
    text = (
        "Dr. Smith was present for the deposition and remained in the room "
        "through the break while counsel discussed scheduling and exhibit "
        "handling. He testified."
    )
    result = split_block_text(text)

    assert len(result) == 2
    assert result[0].startswith("Dr. Smith")


def test_doctor_spelled_out_abbreviation_is_protected():
    text = (
        "Doctor. Anders reviewed the chart with counsel during the lunch "
        "break and remained available for additional questioning as needed. "
        "He later returned to the stand."
    )
    result = split_block_text(text)

    assert len(result) == 2
    assert result[0].startswith("Doctor. Anders")
    assert result[1].startswith("He later returned")


def test_singh_compound_case():
    # The realistic bug from the Singh transcript — initials embedded
    # mid-sentence followed by a real sentence terminator and a new
    # sentence. The splitter must keep "Holly D. Scholl." whole AND
    # split normally at "Scholl. I represent..." into a new block.
    text = (
        "There were several attorneys present today: Mary Mauricio Pena, "
        "Holly D. Scholl. I represent the defendant in this matter and "
        "have done so for years."
    )
    result = split_block_text(text)

    assert len(result) == 2
    assert "Holly D. Scholl." in result[0]
    assert result[1].startswith("I represent")


def test_initial_followed_by_lowercase_not_protected():
    # False-positive guard. INITIAL_RE only protects when the trailing
    # token is capitalized — that's the actual "name initial" shape.
    # If an isolated capital letter ends a sentence and the next sentence
    # starts with lowercase (rare but possible), no protection should
    # fire. Plain sentence boundaries should still split.
    text = (
        "The witness mentioned someone named Q. when describing the call. "
        "She did not elaborate on the identity. The deposition continued "
        "without further reference to the matter."
    )
    result = split_block_text(text)

    # The first sentence ends in "call." — that's a real sentence
    # boundary because "She" follows. The "Q." mid-sentence is followed
    # by lowercase "when", so it's not treated as an initial. Result
    # should split into 3 blocks at the two real sentence boundaries.
    assert len(result) == 3
    assert "Q. when" in result[0]
