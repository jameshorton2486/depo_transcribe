"""Tests for filename-sanitizing helpers in clean_format/docx_writer.py."""

from __future__ import annotations

import pytest

from clean_format.docx_writer import (
    _format_date_for_filename,
    sanitize_filename_component,
)


class TestSanitizeFilenameComponent:
    def test_strips_colon(self):
        assert sanitize_filename_component("8:00 a.m.") == "800 a.m"

    def test_strips_forward_slash(self):
        assert sanitize_filename_component("4/9/2026") == "492026"

    def test_strips_backslash(self):
        assert sanitize_filename_component(r"file\name") == "filename"

    def test_strips_asterisk(self):
        assert sanitize_filename_component("witness*name") == "witnessname"

    def test_strips_remaining_illegal_chars(self):
        # <, >, ", |, ? are also illegal on Windows
        assert sanitize_filename_component('a<b>c"d|e?f') == "abcdef"

    def test_strips_control_chars(self):
        # \x00-\x1f range; tab, newline, NUL all in range
        assert sanitize_filename_component("hello\tworld\nfoo\x00bar") == "helloworldfoobar"

    def test_strips_leading_and_trailing_dot(self):
        assert sanitize_filename_component(".hidden.") == "hidden"

    def test_strips_trailing_dot_after_substitution(self):
        # The real bug: "April 9, 2026 at 8:00 a.m." → strip `:` → "...a.m."
        # → trailing dot removed so the resulting stem doesn't end in `.`
        assert sanitize_filename_component("April 9 2026 at 8:00 a.m.") == "April 9 2026 at 800 a.m"

    def test_collapses_whitespace_runs(self):
        # Note: tabs/newlines are stripped first (they're in the control-char
        # class), so the whitespace-collapse step only sees spaces.
        assert sanitize_filename_component("foo   bar    baz") == "foo bar baz"

    def test_strips_surrounding_whitespace(self):
        assert sanitize_filename_component("  foo  ") == "foo"

    def test_empty_string_falls_back_to_document(self):
        assert sanitize_filename_component("") == "document"

    def test_only_illegal_chars_falls_back_to_document(self):
        assert sanitize_filename_component(":::") == "document"

    def test_only_dots_falls_back_to_document(self):
        assert sanitize_filename_component("...") == "document"

    def test_none_input_falls_back_to_document(self):
        # The helper accepts the falsy `value or ""` path; verify it
        # doesn't blow up on None even though the type annotation says str.
        assert sanitize_filename_component(None) == "document"  # type: ignore[arg-type]

    def test_real_world_karam_filename_stem(self):
        # The exact stem produced by the bug we just fixed.
        bad = "KARAM3_Deposition_April 9 2026 at 8:00 a.m."
        assert sanitize_filename_component(bad) == "KARAM3_Deposition_April 9 2026 at 800 a.m"


class TestFormatDateForFilename:
    def test_intake_with_at_time_suffix(self):
        # The exact input that produced the ADS bug. Strip `at 8:00 a.m.`
        # then parse `April 9, 2026` as `%B %d, %Y`.
        assert _format_date_for_filename("April 9, 2026 at 8:00 a.m.") == "2026-04-09"

    def test_iso_date_passes_through(self):
        assert _format_date_for_filename("2026-04-09") == "2026-04-09"

    def test_us_slash_date(self):
        assert _format_date_for_filename("4/9/2026") == "2026-04-09"

    def test_full_month_date(self):
        assert _format_date_for_filename("April 9, 2026") == "2026-04-09"

    def test_at_suffix_with_alternative_time_form(self):
        # Match `at` regardless of what follows.
        assert _format_date_for_filename("4/9/2026 at noon") == "2026-04-09"

    def test_unparseable_falls_back_to_string_replace(self):
        # No format matches and no `at` to strip; fall back to the legacy
        # behavior: replace `/` with `-`, drop `,` entirely. Downstream
        # gets something usable rather than a parse error.
        assert _format_date_for_filename("garbage/date,here") == "garbage-datehere"

    def test_empty_string_returns_empty(self):
        assert _format_date_for_filename("") == ""
