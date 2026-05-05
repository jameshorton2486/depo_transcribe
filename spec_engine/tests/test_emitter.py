from spec_engine.classifier import classify_blocks
from spec_engine.emitter import emit_blocks
from spec_engine.qa_fixer import enforce_structure
from spec_engine.speaker_mapper import normalize_speakers


def test_emitter_enforces_tabbed_qa_and_double_spacing():
    classified = classify_blocks(
        [
            {"speaker": "speaker 1", "text": "BY MS. MALONEY:", "type": "paragraph"},
            {
                "speaker": "speaker 1",
                "text": "\tQ.\tDid you go there? yes.",
                "type": "paragraph",
            },
            {"speaker": "speaker 2", "text": "\tA.\tYes. I did.", "type": "paragraph"},
        ]
    )
    rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
    assert "BY MS. MALONEY:" in rendered
    assert "\tQ.\tDid you go there?  yes." in rendered
    assert "\tA.\tYes.  I did." in rendered
    assert "\n\n\tA.\t" in rendered


def test_emitter_groups_consecutive_colloquy_under_one_label():
    classified = classify_blocks(
        [
            {
                "speaker": "videographer",
                "text": "Today's date is April 9, 2026.",
                "type": "paragraph",
            },
            {
                "speaker": "videographer",
                "text": "The time is 8:12 a.m.",
                "type": "paragraph",
            },
        ]
    )
    rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
    assert (
        rendered
        == "    VIDEOGRAPHER:\n        Today's date is April 9, 2026.\n        The time is 8:12 a.m."
    )


def test_emitter_normalizes_time_format_in_colloquy():
    classified = classify_blocks(
        [
            {
                "speaker": "videographer",
                "text": "The time is 08:12 AM.",
                "type": "paragraph",
            },
        ]
    )
    rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
    assert "8:12 a.m." in rendered


def test_emitter_splits_long_answer_into_paragraphs():
    classified = classify_blocks(
        [
            {
                "speaker": "speaker 1",
                "text": "\tQ.\tTell me what happened.",
                "type": "paragraph",
            },
            {
                "speaker": "speaker 2",
                "text": "\tA.\tI walked in. I sat down. I signed the paper.",
                "type": "paragraph",
            },
        ]
    )
    rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
    assert rendered.count("\tA.\t") == 2


# ── normalize_speaker leading-zero canonicalization ────────────────────


from spec_engine.emitter import normalize_speaker


def test_normalize_speaker_single_digit_unchanged():
    assert normalize_speaker("Speaker 1") == "SPEAKER 1:"
    assert normalize_speaker("Speaker 0") == "SPEAKER 0:"
    assert normalize_speaker("Speaker 9") == "SPEAKER 9:"


def test_normalize_speaker_strips_leading_zero_from_two_digits():
    assert normalize_speaker("Speaker 01") == "SPEAKER 1:"
    assert normalize_speaker("Speaker 09") == "SPEAKER 9:"
    assert normalize_speaker("Speaker 00") == "SPEAKER 0:"


def test_normalize_speaker_canonicalizes_padded_and_unpadded_to_same_form():
    # The drift fix: same id, different padding, must canonicalize equal.
    assert normalize_speaker("Speaker 01") == normalize_speaker("Speaker 1")
    assert normalize_speaker("speaker 03") == normalize_speaker("Speaker 3")


def test_normalize_speaker_preserves_already_canonical_two_digit():
    # Real two-digit ids (10, 11, ...) are not padded so they pass through.
    assert normalize_speaker("Speaker 10") == "SPEAKER 10:"
    assert normalize_speaker("Speaker 12") == "SPEAKER 12:"


def test_normalize_speaker_handles_existing_colon_and_whitespace():
    assert normalize_speaker("  speaker 01:  ") == "SPEAKER 1:"
    assert normalize_speaker("SPEAKER 1:") == "SPEAKER 1:"


def test_normalize_speaker_does_not_strip_zeros_from_words():
    # The strip is bounded to whole-numeric tokens; CSR numbers and the
    # like must not be touched. (Speaker labels rarely contain these,
    # but defense-in-depth: the regex requires an isolated numeric run.)
    assert normalize_speaker("MR. 007") == "MR. 7:"
    assert normalize_speaker("MS. SMITH 02") == "MS. SMITH 2:"
    assert normalize_speaker("THE WITNESS") == "THE WITNESS:"
    assert normalize_speaker("THE COURT REPORTER") == "THE COURT REPORTER:"


def test_normalize_speaker_empty_and_none():
    assert normalize_speaker(None) == ""
    assert normalize_speaker("") == ""
