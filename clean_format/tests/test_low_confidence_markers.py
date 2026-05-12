"""Step C — low-confidence marker injection / validation tests.

Coverage:
  1. ``inject_markers`` wraps tokens below the threshold; leaves
     high-confidence tokens untouched.
  2. ``inject_markers`` is tolerant of case, trailing punctuation, and
     missing tokens.
  3. ``inject_markers`` is a no-op when ``words`` is None / empty.
  4. ``count_markers`` and ``strip_markers`` are inverses for non-nested
     marker bodies.
  5. ``split_into_runs`` produces ``(chunk, is_low_confidence)`` tuples
     whose concatenation equals ``strip_markers(text)``.
  6. ``validate_marker_round_trip`` reports drift accurately and never
     raises.
  7. ``format_transcript`` honors ``deepgram_words`` parameter — sends
     marked text to Anthropic; behavior is unchanged when None.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from clean_format.formatter import format_transcript
from clean_format.low_confidence_markers import (
    LOW_CONF_CLOSE,
    LOW_CONF_OPEN,
    count_markers,
    inject_markers,
    split_into_runs,
    strip_markers,
    validate_marker_round_trip,
)


def _word(text: str, confidence: float) -> dict:
    return {
        "word": text,
        "start": 0.0,
        "end": 0.1,
        "confidence": confidence,
        "speaker": 0,
        "punctuated_word": text,
    }


# ----------------------------------------------------------------------------
# inject_markers — basic semantics
# ----------------------------------------------------------------------------


class TestInjectMarkers:
    def test_wraps_low_confidence_token(self):
        result = inject_markers(
            "I saw the witness.",
            [
                _word("i", 0.99),
                _word("saw", 0.99),
                _word("the", 0.99),
                _word("witness", 0.50),
            ],
            threshold=0.85,
        )
        assert result == f"I saw the {LOW_CONF_OPEN}witness{LOW_CONF_CLOSE}."

    def test_does_not_wrap_high_confidence_tokens(self):
        result = inject_markers(
            "Hello world.",
            [_word("hello", 0.99), _word("world", 0.99)],
            threshold=0.85,
        )
        assert LOW_CONF_OPEN not in result
        assert result == "Hello world."

    def test_wraps_multiple_low_confidence_tokens(self):
        result = inject_markers(
            "She saw the Acebo at Cesar Plaza.",
            [
                _word("she", 0.99),
                _word("saw", 0.99),
                _word("the", 0.99),
                _word("acebo", 0.40),
                _word("at", 0.99),
                _word("cesar", 0.50),
                _word("plaza", 0.99),
            ],
            threshold=0.85,
        )
        assert count_markers(result) == 2
        # Verify the right tokens were marked.
        runs = split_into_runs(result)
        marked = [chunk for chunk, is_lc in runs if is_lc]
        assert marked == ["Acebo", "Cesar"]

    def test_case_insensitive_match(self):
        # Deepgram word is lowercase; transcript shows capitalized.
        result = inject_markers(
            "I saw Witness.",
            [_word("i", 0.99), _word("saw", 0.99), _word("witness", 0.5)],
            threshold=0.85,
        )
        # Marked token preserves the rendered case.
        assert f"{LOW_CONF_OPEN}Witness{LOW_CONF_CLOSE}" in result

    def test_trailing_punctuation_outside_marker(self):
        result = inject_markers(
            "I saw witness, then left.",
            [
                _word("i", 0.99), _word("saw", 0.99),
                _word("witness", 0.40), _word("then", 0.99), _word("left", 0.99),
            ],
            threshold=0.85,
        )
        # Comma stays outside the close marker.
        assert f"{LOW_CONF_OPEN}witness{LOW_CONF_CLOSE}," in result

    def test_token_missing_from_text_is_skipped(self):
        # 'phantom' is in the word list but not in the text — algorithm
        # skips it silently and continues with the next word.
        result = inject_markers(
            "Hello there.",
            [
                _word("hello", 0.99),
                _word("phantom", 0.30),  # not in text — skipped
                _word("there", 0.40),
            ],
            threshold=0.85,
        )
        assert f"{LOW_CONF_OPEN}there{LOW_CONF_CLOSE}" in result
        assert "phantom" not in result

    def test_none_words_returns_unchanged(self):
        text = "Speaker 0: Hello world."
        assert inject_markers(text, None) == text

    def test_empty_words_returns_unchanged(self):
        text = "Speaker 0: Hello world."
        assert inject_markers(text, []) == text

    def test_empty_text_returns_unchanged(self):
        assert inject_markers("", [_word("hi", 0.5)]) == ""

    def test_word_boundary_not_matched_inside_other_word(self):
        # 'said' is low-confidence but the text contains 'unsaid' — the
        # \b\b pattern should not match the substring.
        result = inject_markers(
            "She said something unsaid.",
            [
                _word("she", 0.99), _word("said", 0.50),
                _word("something", 0.99),  # high confidence — not marked
                _word("unsaid", 0.99),
            ],
            threshold=0.85,
        )
        # Only the standalone 'said' should be wrapped.
        assert count_markers(result) == 1
        assert f"{LOW_CONF_OPEN}said{LOW_CONF_CLOSE}" in result
        # 'unsaid' should NOT have been wrapped.
        assert f"un{LOW_CONF_OPEN}" not in result

    def test_apostrophe_inside_token(self):
        result = inject_markers(
            "I don't know.",
            [
                _word("i", 0.99),
                _word("don't", 0.40),
                _word("know", 0.99),
            ],
            threshold=0.85,
        )
        assert f"{LOW_CONF_OPEN}don't{LOW_CONF_CLOSE}" in result

    def test_threshold_boundary_strict_less_than(self):
        # confidence == threshold is NOT wrapped (strict <).
        result = inject_markers(
            "Hello world.",
            [_word("hello", 0.99), _word("world", 0.85)],
            threshold=0.85,
        )
        assert LOW_CONF_OPEN not in result


# ----------------------------------------------------------------------------
# count_markers / strip_markers / split_into_runs round-trip
# ----------------------------------------------------------------------------


class TestMarkerUtilities:
    def test_count_markers_on_empty_returns_zero(self):
        assert count_markers("") == 0
        assert count_markers("no markers here") == 0

    def test_count_markers_counts_pairs(self):
        text = (
            f"a {LOW_CONF_OPEN}b{LOW_CONF_CLOSE} c "
            f"{LOW_CONF_OPEN}d{LOW_CONF_CLOSE} e"
        )
        assert count_markers(text) == 2

    def test_strip_markers_removes_markers_keeps_body(self):
        text = f"a {LOW_CONF_OPEN}b{LOW_CONF_CLOSE} c"
        assert strip_markers(text) == "a b c"

    def test_strip_markers_empty(self):
        assert strip_markers("") == ""
        assert strip_markers("no markers") == "no markers"

    def test_split_into_runs_empty(self):
        assert split_into_runs("") == []

    def test_split_into_runs_no_markers(self):
        assert split_into_runs("plain text") == [("plain text", False)]

    def test_split_into_runs_single_marker(self):
        text = f"hello {LOW_CONF_OPEN}world{LOW_CONF_CLOSE} bye"
        assert split_into_runs(text) == [
            ("hello ", False),
            ("world", True),
            (" bye", False),
        ]

    def test_split_into_runs_marker_at_start(self):
        text = f"{LOW_CONF_OPEN}hello{LOW_CONF_CLOSE} world"
        assert split_into_runs(text) == [
            ("hello", True),
            (" world", False),
        ]

    def test_split_into_runs_marker_at_end(self):
        text = f"hello {LOW_CONF_OPEN}world{LOW_CONF_CLOSE}"
        assert split_into_runs(text) == [
            ("hello ", False),
            ("world", True),
        ]

    def test_split_into_runs_back_to_back_markers(self):
        text = f"{LOW_CONF_OPEN}a{LOW_CONF_CLOSE}{LOW_CONF_OPEN}b{LOW_CONF_CLOSE}"
        assert split_into_runs(text) == [
            ("a", True),
            ("b", True),
        ]

    def test_split_into_runs_reconstructs_stripped_text(self):
        text = (
            f"Q.\tDr. {LOW_CONF_OPEN}Acebo{LOW_CONF_CLOSE} examined the "
            f"{LOW_CONF_OPEN}witness{LOW_CONF_CLOSE}."
        )
        runs = split_into_runs(text)
        joined = "".join(chunk for chunk, _ in runs)
        assert joined == strip_markers(text)


# ----------------------------------------------------------------------------
# validate_marker_round_trip
# ----------------------------------------------------------------------------


class TestValidateRoundTrip:
    def test_no_drift_reports_zero_dropped(self, caplog):
        with caplog.at_level(logging.WARNING):
            stats = validate_marker_round_trip(
                f"a {LOW_CONF_OPEN}b{LOW_CONF_CLOSE}",
                f"A {LOW_CONF_OPEN}B{LOW_CONF_CLOSE}",
            )
        assert stats == {"input_count": 1, "output_count": 1, "dropped": 0}
        assert not any("dropped" in r.message for r in caplog.records)

    def test_dropped_markers_logged(self, caplog):
        with caplog.at_level(logging.WARNING):
            stats = validate_marker_round_trip(
                f"a {LOW_CONF_OPEN}b{LOW_CONF_CLOSE} c {LOW_CONF_OPEN}d{LOW_CONF_CLOSE}",
                "A B C D",
            )
        assert stats == {"input_count": 2, "output_count": 0, "dropped": 2}
        assert any(
            "dropped 2 of 2" in r.message.lower() for r in caplog.records
        )

    def test_added_markers_do_not_count_as_dropped(self, caplog):
        # If Anthropic somehow ADDS markers (unlikely but possible),
        # `dropped` clamps at zero rather than going negative.
        stats = validate_marker_round_trip(
            "a b c",
            f"a {LOW_CONF_OPEN}b{LOW_CONF_CLOSE} c",
        )
        assert stats == {"input_count": 0, "output_count": 1, "dropped": 0}

    def test_never_raises_on_empty_input(self):
        stats = validate_marker_round_trip("", "")
        assert stats == {"input_count": 0, "output_count": 0, "dropped": 0}


# ----------------------------------------------------------------------------
# format_transcript integration — deepgram_words parameter
# ----------------------------------------------------------------------------


class _FakeMessages:
    def __init__(self, response_text: str = "OUTPUT") -> None:
        self.calls: list[dict] = []
        self.response_text = response_text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self.response_text)]
        )


class _FakeClient:
    def __init__(self, response_text: str = "OUTPUT") -> None:
        self.messages = _FakeMessages(response_text)


class TestFormatTranscriptWordsParam:
    def test_no_words_param_unchanged_behavior(self):
        client = _FakeClient(response_text="A.\tHello.")
        format_transcript("Speaker 0: hello", {}, client=client)
        sent = client.messages.calls[0]["messages"][0]["content"]
        # No markers in the sent message.
        assert LOW_CONF_OPEN not in sent

    def test_with_low_confidence_words_sends_marked_text(self):
        client = _FakeClient(
            response_text=f"A.\thello {LOW_CONF_OPEN}world{LOW_CONF_CLOSE}."
        )
        words = [_word("hello", 0.99), _word("world", 0.40)]
        format_transcript(
            "Speaker 0: hello world.",
            {},
            client=client,
            deepgram_words=words,
            low_confidence_threshold=0.85,
        )
        sent = client.messages.calls[0]["messages"][0]["content"]
        assert LOW_CONF_OPEN in sent
        assert f"{LOW_CONF_OPEN}world{LOW_CONF_CLOSE}" in sent

    def test_response_with_preserved_markers_returns_them(self):
        client = _FakeClient(
            response_text=f"A.\thello {LOW_CONF_OPEN}world{LOW_CONF_CLOSE}."
        )
        words = [_word("hello", 0.99), _word("world", 0.40)]
        result = format_transcript(
            "Speaker 0: hello world.",
            {},
            client=client,
            deepgram_words=words,
        )
        # Marker survives _postprocess_formatted_text.
        assert f"{LOW_CONF_OPEN}world{LOW_CONF_CLOSE}" in result

    def test_drift_is_logged_not_raised(self, caplog):
        # Client returns response with NO markers — drift case.
        client = _FakeClient(response_text="A.\thello world.")
        words = [_word("hello", 0.99), _word("world", 0.40)]
        with caplog.at_level(logging.WARNING):
            format_transcript(
                "Speaker 0: hello world.",
                {},
                client=client,
                deepgram_words=words,
            )
        # Pipeline completed (no exception). Drift logged.
        assert any("dropped" in r.message.lower() for r in caplog.records)

    def test_high_confidence_words_no_markers_sent(self):
        client = _FakeClient(response_text="A.\thello world.")
        # All confidences above threshold.
        words = [_word("hello", 0.99), _word("world", 0.99)]
        format_transcript(
            "Speaker 0: hello world.",
            {},
            client=client,
            deepgram_words=words,
        )
        sent = client.messages.calls[0]["messages"][0]["content"]
        assert LOW_CONF_OPEN not in sent
