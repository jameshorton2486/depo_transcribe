"""Tests for objection routing (defect #3)."""

from spec_engine.objection_routing import (
    SENTINEL_SPEAKER,
    split_misattributed_objections,
)
from spec_engine.models import TranscriptBlock


def _q(text: str, examiner: str | None = "MR. NUNEZ") -> TranscriptBlock:
    return TranscriptBlock(
        speaker="MR. NUNEZ", text=text, type="question", examiner=examiner
    )


def _a(text: str = "Yes.") -> TranscriptBlock:
    return TranscriptBlock(speaker="THE WITNESS", text=text, type="answer")


def _colloquy(speaker: str, text: str) -> TranscriptBlock:
    return TranscriptBlock(speaker=speaker, text=text, type="colloquy")


def _directive(text: str) -> TranscriptBlock:
    return TranscriptBlock(speaker="", text=text, type="directive")


def test_empty_input():
    assert split_misattributed_objections([]) == []


def test_block_with_no_objection_unchanged():
    blocks = [_q("Did you see the vehicle approaching from the left?")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "Did you see the vehicle approaching from the left?"
    assert result[0].speaker == "MR. NUNEZ"
    assert result[0].type == "question"


def test_canonical_merged_question_objection_splits():
    """The Thomas-style merged block: a question, then an objection,
    both attributed to the examining attorney. Split into Q +
    sentinel colloquy."""
    blocks = [
        _q("You could not see directly in front of you? Objection. Form. Vague and ambiguous.")
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[0].speaker == "MR. NUNEZ"
    assert result[0].type == "question"
    assert result[0].text == "You could not see directly in front of you?"
    assert result[0].examiner == "MR. NUNEZ"
    assert result[1].speaker == SENTINEL_SPEAKER
    assert result[1].type == "colloquy"
    assert result[1].text == "Objection. Form. Vague and ambiguous."
    assert result[1].examiner is None


def test_split_preserves_question_block_metadata():
    """source_type, examiner, words on the question block are
    preserved on the truncated half."""
    block = TranscriptBlock(
        speaker="MR. NUNEZ",
        text="And what happened next, sir? Objection. Asked and answered.",
        type="question",
        source_type="diarized",
        examiner="MR. NUNEZ",
        words=[{"word": "And", "start": 1.0}],
    )
    result = split_misattributed_objections([block])
    assert len(result) == 2
    assert result[0].source_type == "diarized"
    assert result[0].examiner == "MR. NUNEZ"
    assert result[0].words == [{"word": "And", "start": 1.0}]
    assert result[1].examiner is None
    assert result[1].words is None


def test_block_starting_with_objection_no_split():
    """A block whose text IS just an objection (real attorney's
    correctly-attributed objection) must not be split."""
    blocks = [_colloquy("MS. ZHAN", "Objection. Form. Vague.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].speaker == "MS. ZHAN"
    assert result[0].text == "Objection. Form. Vague."


def test_objection_within_offset_threshold_no_split():
    """Objection at character 5 (< 10) means the block IS the
    objection, not a merger. No split."""
    blocks = [_colloquy("MS. ZHAN", "Yes. Objection. Form.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "Yes. Objection. Form."


def test_short_preceding_text_no_split():
    """Less than 20 chars of non-whitespace preceding text means
    likely a quick attorney objection in their own block, not a
    merged utterance."""
    blocks = [_colloquy("MS. ZHAN", "I object now. Objection. Form.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "I object now. Objection. Form."


def test_no_sentence_boundary_no_split():
    """If there is no sentence boundary before the objection, we
    can't determine where the question ends. Suppress the split
    rather than emit an empty pre-text."""
    blocks = [_q("This whole long sentence Objection. Form.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "This whole long sentence Objection. Form."


def test_first_match_only_no_recursive_split():
    """When two objections appear in one block, only the first
    match drives the split. The post-text keeps its second
    objection intact."""
    blocks = [
        _q("Did you see it? Objection. Form. Asked. Objection. Asked and answered.")
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[0].text == "Did you see it?"
    assert result[1].text == "Objection. Form. Asked. Objection. Asked and answered."
    assert result[1].speaker == SENTINEL_SPEAKER


def test_colloquy_block_eligible_for_split():
    """Not just question blocks - a colloquy block with the same
    merge pattern is also split."""
    blocks = [
        _colloquy(
            "MR. NUNEZ",
            "Counsel, please instruct your witness. Objection. Form.",
        )
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[0].type == "colloquy"
    assert result[0].speaker == "MR. NUNEZ"
    assert result[0].text == "Counsel, please instruct your witness."
    assert result[1].type == "colloquy"
    assert result[1].speaker == SENTINEL_SPEAKER
    assert result[1].text == "Objection. Form."


def test_answer_block_never_split():
    """Answer blocks are excluded by TYPE, not by content.
    Witnesses do use the word 'objection' in their answers —
    discussing prior objections, reciting events, etc. — but
    those uses are not merge defects. The type check in
    _SPLIT_TARGET_TYPES is what prevents the split."""
    block = TranscriptBlock(
        speaker="THE WITNESS",
        text="Well, I would have raised an objection if I had been there. Objection. Form.",
        type="answer",
    )
    result = split_misattributed_objections([block])
    assert len(result) == 1
    assert result[0].type == "answer"
    assert result[0].text.startswith("Well, I would have raised")


def test_directive_block_never_split():
    """A directive block is never split."""
    blocks = [_directive("(Witness sworn. Objection raised by counsel.)")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].type == "directive"


def test_objection_with_comma_punctuation():
    """The regex matches `objection,` (with comma)."""
    blocks = [_q("Did you see the vehicle approaching? Objection, your honor.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[1].text == "Objection, your honor."


def test_objection_with_colon_punctuation():
    """The regex matches `objection:` (with colon)."""
    blocks = [_q("Did you see the vehicle approaching? Objection: form.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[1].text == "Objection: form."


def test_objection_without_trailing_punctuation():
    """The regex matches `objection` with no trailing punctuation
    (optional in the pattern)."""
    blocks = [_q("Did you see the vehicle approaching? Objection form vague.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[1].text == "Objection form vague."


def test_objection_case_insensitive():
    """The regex is case-insensitive."""
    blocks = [_q("Did you see the vehicle approaching? OBJECTION. Form.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[1].text == "OBJECTION. Form."


def test_word_boundary_objectionable_does_not_match():
    """The regex requires a word boundary AFTER 'objection',
    so 'objectionable' does not match."""
    blocks = [_q("Did you find any of his testimony objectionable in that case?")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "Did you find any of his testimony objectionable in that case?"


def test_word_boundary_objections_plural_no_match_with_punctuation():
    """The plural 'objections' followed by punctuation does not
    match the singular 'objection' word."""
    blocks = [_q("Are there any further objections at this time, counsel?")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1


def test_no_objection_phrase_does_not_split():
    """The phrase 'no objection' is normal colloquy, not a
    merged-objection defect. The block must pass through
    unchanged regardless of how much preceding text it has or
    whether a sentence boundary precedes the match."""
    blocks = [
        _q(
            "Counsel reviewed exhibit one in detail. "
            "Plaintiff has no objection to admission."
        )
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == (
        "Counsel reviewed exhibit one in detail. "
        "Plaintiff has no objection to admission."
    )


def test_without_objection_at_start_filtered_by_offset():
    """'Without objection' near the block start is filtered by
    the 10-char offset threshold (the match is too early)."""
    blocks = [_colloquy("THE COURT", "Without objection, the exhibit is admitted.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "Without objection, the exhibit is admitted."


def test_without_objection_mid_block_does_not_split():
    """'Without objection' mid-block (not at start, past the
    offset threshold) is suppressed by the phrase window."""
    blocks = [
        _colloquy(
            "THE COURT",
            "We have addressed the record. Counsel proceeds without objection.",
        )
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == (
        "We have addressed the record. Counsel proceeds without objection."
    )


def test_subject_to_objection_does_not_split():
    """'Subject to objection' is normal legal colloquy. The
    phrase window suppresses the split."""
    blocks = [
        _colloquy(
            "MS. ZHAN",
            "The witness may answer subject to objection on form.",
        )
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "The witness may answer subject to objection on form."


def test_merged_block_with_nearby_colloquy_phrase_suppressed():
    """Trade-off pin. If a real merged block happens to contain
    'no objection' within the phrase window of the first match,
    the split is suppressed. This is rare in practice; we accept
    it to avoid splitting normal colloquy.

    If review evidence shows real merges being missed because
    of this trade-off, tighten the phrase check (e.g. require
    the phrase to immediately precede the match) rather than
    removing the exclusion."""
    blocks = [
        _q("Did you see the car? Objection. No objection here.")
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1


def test_distant_colloquy_phrase_does_not_suppress_split():
    """A 'no objection' phrase far enough from the first match
    (outside the +-25 char window) does NOT suppress the split.
    The real merge is still caught."""
    blocks = [
        _q(
            "Did you see the vehicle? Objection. Form and foundation. "
            "But on a different point, plaintiff has no objection to "
            "the next exhibit."
        )
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[0].text == "Did you see the vehicle?"
    assert result[1].speaker == SENTINEL_SPEAKER
    assert result[1].text.startswith("Objection. Form and foundation.")


def test_split_with_question_mark_boundary():
    """A `?` followed by whitespace is a valid sentence boundary."""
    blocks = [_q("Did you see the car coming? Objection. Speculation.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[0].text == "Did you see the car coming?"
    assert result[1].text == "Objection. Speculation."


def test_split_with_exclamation_boundary():
    """A `!` followed by whitespace is a valid sentence boundary."""
    blocks = [_q("Watch out for that turn! Objection. Argumentative.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[0].text == "Watch out for that turn!"
    assert result[1].text == "Objection. Argumentative."


def test_multiple_blocks_only_targeted_block_splits():
    """Process several blocks; only the one matching the trigger
    is split. Others pass through unchanged in order."""
    blocks = [
        _q("State your name for the record."),
        _a("Heath Thomas."),
        _q("Did you see anything unusual? Objection. Form. Vague."),
        _a("No."),
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 5
    assert result[0].text == "State your name for the record."
    assert result[1].text == "Heath Thomas."
    assert result[2].text == "Did you see anything unusual?"
    assert result[3].speaker == SENTINEL_SPEAKER
    assert result[3].text == "Objection. Form. Vague."
    assert result[4].text == "No."


def test_chunk_3_thomas_real_pattern():
    """The actual pattern observed in the Thomas chunk 3 raw
    Deepgram output: a question ending with `?` followed by a
    Form objection. Confirms the canonical case is caught."""
    blocks = [
        _q("you could not see directly in front of you? Objection. Form. Big ambiguous.")
    ]
    result = split_misattributed_objections(blocks)
    assert len(result) == 2
    assert result[0].text == "you could not see directly in front of you?"
    assert result[1].speaker == SENTINEL_SPEAKER
    assert result[1].text == "Objection. Form. Big ambiguous."


def test_chunk_12_thomas_malformed_merger_not_split():
    """The chunk-12 pattern 'My question is and Objection.
    It's nonresponsive.' is a known malformed merger. Preceding
    stripped text length is 18 chars, below the 20-char
    threshold. The current implementation does NOT split this
    case; it passes through unchanged. Documents current
    behavior - if Miah's review flags this as a needed catch,
    lower the threshold from real evidence."""
    blocks = [_q("My question is and Objection. It's nonresponsive.")]
    result = split_misattributed_objections(blocks)
    assert len(result) == 1
    assert result[0].text == "My question is and Objection. It's nonresponsive."
