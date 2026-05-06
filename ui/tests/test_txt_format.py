"""Tests for the plain-text Q/A formatter used by the Notepad / preview
export in ui/tab_transcribe.py. The helper is a pure function — testable
without any Tk setup.

Layout under test:
  first line: 8 spaces + label + 4 spaces + body  (body starts col 14)
  wrapped:    14 spaces + body                    (wrap aligns col 14)
"""
from ui.tab_transcribe import _format_transcript_for_txt, format_qa_for_plain_text


# ── format_qa_for_plain_text ────────────────────────────────────────────


def test_qa_helper_first_line_prefix_is_q_at_col_8_body_at_col_14():
    out = format_qa_for_plain_text("Q.", "Short question.")
    first = out.splitlines()[0]
    # 8 leading spaces, then "Q."
    assert first.startswith("        Q."), first
    # body starts at character 15 (1-indexed) = col 14 (0-indexed)
    assert first[14] == "S"   # "S" of "Short"


def test_qa_helper_a_label_uses_same_geometry():
    out = format_qa_for_plain_text("A.", "Short answer.")
    first = out.splitlines()[0]
    assert first.startswith("        A."), first
    assert first[14] == "S"


def test_qa_helper_continuation_lines_align_at_col_14():
    long_q = (
        "And in this one, doing a comparison of the head to the abdominal "
        "circumference, is it saying that would give a gestational age of "
        "40 weeks and 4 days?"
    )
    out = format_qa_for_plain_text("Q.", long_q)
    lines = out.splitlines()
    assert len(lines) >= 2, "long question should wrap to multiple lines"
    # Every continuation line begins with exactly 14 spaces of prefix
    for line in lines[1:]:
        assert line[:14] == " " * 14, repr(line)
        # First non-space character is at column 14 (0-indexed)
        assert line[14] != " ", repr(line)


def test_qa_helper_does_not_drop_words():
    body = (
        "And in this one, doing a comparison of the head to the abdominal "
        "circumference, is it saying that would give a gestational age of "
        "40 weeks and 4 days?"
    )
    out = format_qa_for_plain_text("Q.", body)
    # Recombine the wrapped output and confirm every input word survives
    flattened = " ".join(line.strip() for line in out.splitlines())
    # The label "Q." sits at the front; everything after the label run
    # should be the original body's word sequence.
    assert flattened.startswith("Q.    ")
    body_only = flattened[len("Q.    "):]
    assert body_only.replace("  ", " ").split() == body.split()


def test_qa_helper_preserves_double_space_after_sentence_ending():
    body = (
        "That's the measurement for the abdominal circumference.  Is "
        "that what it's consistent with at that stage?"
    )
    out = format_qa_for_plain_text("A.", body)
    assert "circumference.  Is" in out


def test_qa_helper_does_not_emit_visible_tab_or_arrow_markers():
    out = format_qa_for_plain_text(
        "Q.", "And in this one, doing a comparison of the head?"
    )
    assert "\t" not in out, "no real tab characters in TXT output"
    assert "→" not in out, "no arrow glyphs"
    assert "→" not in out, "no ASCII-style arrows"


def test_qa_helper_handles_empty_body():
    out = format_qa_for_plain_text("Q.", "")
    # Just the prefix, trimmed of trailing spaces — no exception
    assert out == "        Q."


# ── _format_transcript_for_txt integration ──────────────────────────────


def test_format_transcript_for_txt_emits_wrapped_qa_not_raw_tabs():
    raw = (
        "Q.\tAnd in this one, doing a comparison of the head to the "
        "abdominal circumference, is it saying that would give a "
        "gestational age of 40 weeks and 4 days?\n\n"
        "A.\tThat's the measurement for the abdominal circumference.  "
        "Is that what it's consistent with at that stage?"
    )
    out = _format_transcript_for_txt(raw)
    # No \tQ.\t anywhere — Notepad rendering is space-based now
    assert "\t" not in out, repr(out)
    # Q. block first line at col 8
    q_first_line = next(
        line for line in out.splitlines() if line.lstrip().startswith("Q.")
    )
    assert q_first_line.startswith("        Q.")
    a_first_line = next(
        line for line in out.splitlines() if line.lstrip().startswith("A.")
    )
    assert a_first_line.startswith("        A.")


def test_format_transcript_for_txt_keeps_speaker_block_layout():
    """Speaker blocks (4-space indent label + 8-space indent body) are
    untouched — only Q/A bodies use the new plain-text wrap."""
    raw = "Q.\tFirst question.\n\nMR. SMITH:\tObjection. Form."
    out = _format_transcript_for_txt(raw)
    lines = out.splitlines()
    # Speaker label at 4-space indent; body at 8-space indent.
    assert any(line.startswith("    MR. SMITH:") for line in lines), out
    assert any(
        line.startswith("        ") and "Objection" in line for line in lines
    ), out
