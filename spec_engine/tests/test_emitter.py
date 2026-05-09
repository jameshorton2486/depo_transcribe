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
    """Step 2J: colloquy lines (label + body) are prefixed with three
    tabs. Prior versions used 4-space/8-space soft indents."""
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
        == "\t\t\tVIDEOGRAPHER:\n\t\t\tToday's date is April 9, 2026.\n\t\t\tThe time is 8:12 a.m."
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


# ── Step 2J: tab-prefix contract ─────────────────────────────────────────────


class TestStep2JTabPrefix:
    """Step 2J formatting contract:
      * Q/A lines emitted as "\\tQ.\\t{text}" / "\\tA.\\t{text}" (one
        leading tab, then label, then tab, then body).
      * Non-Q/A lines (colloquy, directive, fallback) emitted with
        exactly three leading tabs.
      * Tabs are real \\t characters, not spaces or arrows.
    """

    def test_question_line_starts_with_one_tab_then_q_dot_tab(self):
        from spec_engine.emitter import format_qa
        from spec_engine.models import TranscriptBlock

        block = TranscriptBlock(
            speaker="Speaker 1", text="What is your name?", type="question"
        )
        out = format_qa(block)
        assert out.startswith("\tQ.\t")
        assert "→" not in out
        # Exactly one leading tab before Q., not three.
        assert not out.startswith("\t\t")

    def test_answer_line_starts_with_one_tab_then_a_dot_tab(self):
        from spec_engine.emitter import format_qa
        from spec_engine.models import TranscriptBlock

        block = TranscriptBlock(
            speaker="Speaker 2", text="John Smith.", type="answer"
        )
        out = format_qa(block)
        assert out.startswith("\tA.\t")
        assert "→" not in out
        assert not out.startswith("\t\t")

    def test_colloquy_speaker_label_starts_with_three_tabs(self):
        classified = classify_blocks(
            [
                {
                    "speaker": "the reporter",
                    "text": "Please raise your right hand.",
                    "type": "paragraph",
                },
            ]
        )
        rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
        # Every non-empty line in the colloquy block must start with \t\t\t.
        non_empty = [line for line in rendered.split("\n") if line]
        assert non_empty, "expected at least one non-empty line"
        for line in non_empty:
            assert line.startswith("\t\t\t"), (
                f"non-Q/A line missing 3-tab prefix: {line!r}"
            )

    def test_directive_starts_with_three_tabs(self):
        classified = classify_blocks(
            [
                {"speaker": "speaker 1", "text": "BY MS. MALONEY:", "type": "paragraph"},
                {
                    "speaker": "speaker 1",
                    "text": "\tQ.\tDid you go there?",
                    "type": "paragraph",
                },
                {"speaker": "speaker 2", "text": "\tA.\tYes.", "type": "paragraph"},
            ]
        )
        rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
        # The directive should appear with three-tab prefix, on its own line.
        assert "\t\t\tBY MS. MALONEY:" in rendered

    def test_no_arrow_characters_in_output(self):
        classified = classify_blocks(
            [
                {"speaker": "speaker 1", "text": "BY MS. MALONEY:", "type": "paragraph"},
                {
                    "speaker": "speaker 1",
                    "text": "\tQ.\tDid you see the dog?",
                    "type": "paragraph",
                },
                {"speaker": "speaker 2", "text": "\tA.\tYes.", "type": "paragraph"},
                {
                    "speaker": "videographer",
                    "text": "Off the record at 9:00 a.m.",
                    "type": "paragraph",
                },
            ]
        )
        rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
        for arrow in ("→", "⇒", "⟶", "►", "▶"):
            assert arrow not in rendered, f"unexpected arrow {arrow!r} in output"

    def test_long_question_text_preserved_verbatim(self):
        """Wrapping is the consumer's job (DOCX uses paragraph wrap with
        tab stops). The emitter must not insert mid-line tabs or split
        long Q text into multiple lines."""
        from spec_engine.emitter import format_qa
        from spec_engine.models import TranscriptBlock

        long_text = (
            "Did you review the records from Doctor Fisher before "
            "preparing your report and forming your opinions in this case?"
        )
        block = TranscriptBlock(speaker="Speaker 1", text=long_text, type="question")
        out = format_qa(block)
        # Single line, leading "\tQ.\t", no embedded tabs after the body.
        assert out.startswith("\tQ.\t")
        assert "\n" not in out
        # Body starts after the second tab, contains no tabs.
        body = out[len("\tQ.\t"):]
        assert "\t" not in body

    def test_long_answer_text_preserved_verbatim(self):
        from spec_engine.emitter import format_qa
        from spec_engine.models import TranscriptBlock

        long_text = (
            "I reviewed all the records that were provided to me by counsel, "
            "including the operative reports and the imaging studies."
        )
        block = TranscriptBlock(speaker="Speaker 2", text=long_text, type="answer")
        out = format_qa(block)
        assert out.startswith("\tA.\t")
        assert "\n" not in out
        body = out[len("\tA.\t"):]
        assert "\t" not in body
