"""Regression tests for the "Speaker 10+ misclassified as court reporter"
bug.

Root cause located: ui/tab_transcribe.py was extracting transcript speaker
ids via re.findall (returns strings) and calling sorted() on them.
sorted() on string-typed digits is lexicographic, so "10" sorts between
"1" and "2". That mis-ordered list then got zip()'d against the ordered
NOD suggestion list inside _build_ui_speaker_defaults, which puts the
two-digit speaker into a NOD slot it shouldn't get — including the
first slot (THE REPORTER) when the transcript contained only two-digit
ids.

Fix: _sorted_transcript_speaker_ids uses key=int so numeric order is
preserved.
"""
from __future__ import annotations

from ui.tab_transcribe import (
    _build_ui_speaker_defaults,
    _sorted_transcript_speaker_ids,
)


# ── _sorted_transcript_speaker_ids helper ──────────────────────────────


def test_single_digit_only_ids_preserve_numeric_order():
    text = "Speaker 0: A\nSpeaker 1: B\nSpeaker 2: C\nSpeaker 3: D\n"
    assert _sorted_transcript_speaker_ids(text) == ["0", "1", "2", "3"]


def test_mixed_single_and_double_digit_ids_sort_numerically():
    """The buggy lex sort would have produced ['0','1','10','2','3'].
    Numeric sort must produce ['0','1','2','3','10']."""
    text = "Speaker 0: A\nSpeaker 1: B\nSpeaker 2: C\nSpeaker 3: D\nSpeaker 10: E\n"
    assert _sorted_transcript_speaker_ids(text) == ["0", "1", "2", "3", "10"]


def test_only_double_digit_ids_keep_their_natural_order():
    text = "Speaker 11: A\nSpeaker 10: B\nSpeaker 12: C\n"
    assert _sorted_transcript_speaker_ids(text) == ["10", "11", "12"]


def test_speaker_ids_are_deduplicated():
    text = "Speaker 1: A\nSpeaker 1: B\nSpeaker 2: C\n"
    assert _sorted_transcript_speaker_ids(text) == ["1", "2"]


def test_empty_or_no_match_returns_empty():
    assert _sorted_transcript_speaker_ids("") == []
    assert _sorted_transcript_speaker_ids(None) == []  # type: ignore[arg-type]
    assert _sorted_transcript_speaker_ids("Some plain text with no speakers.") == []


def test_lex_vs_numeric_order_differ_for_the_known_bug_case():
    """Document the difference. With the buggy lex sort the result
    would have put '10' between '1' and '2', changing zip pairing in
    _build_ui_speaker_defaults — which is where the misclassification
    surfaced."""
    text = "Speaker 1: A\nSpeaker 2: B\nSpeaker 10: C\n"
    numeric = _sorted_transcript_speaker_ids(text)
    lex = sorted({"1", "2", "10"})
    assert numeric == ["1", "2", "10"]
    assert lex == ["1", "10", "2"]
    assert numeric != lex


# ── integrated regression on the misclassification path ────────────────


def test_speaker_10_does_not_steal_an_earlier_nod_slot():
    """The headline regression: with the buggy sort, transcript ids
    [1, 2, 10] became ['1','10','2'], so Speaker 10 received the
    second NOD suggestion instead of the third. Numeric sort fixes it.
    """
    text = "Speaker 1: A\nSpeaker 2: B\nSpeaker 10: C\n"
    speakers = _sorted_transcript_speaker_ids(text)
    suggestion = {
        "reporter": "Miah Bardot",
        "ordering_attorney": "David Volk",
        "witness": "Bianca Caram",
    }
    defaults = _build_ui_speaker_defaults(
        speakers, saved_map=None, suggestion=suggestion
    )
    assert defaults["Speaker 1"] == "THE REPORTER"
    # Speaker 2 takes the second NOD slot (ordering_attorney), NOT
    # Speaker 10. With the lex-sort bug this used to be reversed.
    assert defaults["Speaker 2"] == "David Volk"
    # Speaker 10 lands in the third slot (witness), as its numeric
    # position dictates.
    assert defaults["Speaker 10"] == "THE WITNESS"


def test_first_speaker_id_is_first_nod_slot_regardless_of_two_digit_position():
    """Whatever the smallest-numbered speaker id is, it gets the first
    NOD suggestion slot (typically THE REPORTER). This test pins the
    contract for the "first speaker = reporter" pairing."""
    suggestion = {"reporter": "Miah Bardot"}

    # Single-digit only
    defaults = _build_ui_speaker_defaults(["0", "1"], None, suggestion)
    assert defaults["Speaker 0"] == "THE REPORTER"

    # Mixed; smallest is still 0
    defaults = _build_ui_speaker_defaults(["0", "1", "10"], None, suggestion)
    assert defaults["Speaker 0"] == "THE REPORTER"
    assert "THE REPORTER" not in (
        defaults.get("Speaker 1"), defaults.get("Speaker 10")
    )


def test_saved_map_takes_precedence_over_zip_pairing():
    """A confirmed saved map should always win over the positional NOD
    suggestion zip — including for two-digit ids. Without this guard
    the bug would have been even harder to diagnose since users would
    have manually corrected once and watched it stick incorrectly."""
    saved = {10: "THE VIDEOGRAPHER"}
    suggestion = {"reporter": "Miah Bardot"}
    defaults = _build_ui_speaker_defaults(
        ["0", "10"], saved_map=saved, suggestion=suggestion
    )
    assert defaults["Speaker 10"] == "THE VIDEOGRAPHER"
