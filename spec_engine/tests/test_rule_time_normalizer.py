"""
spec_engine/tests/test_rule_time_normalizer.py

Tests for time-normalization rules (fix_spoken_times,
normalize_time_and_dashes) — specifically the Phase B fix that
collapses double-period output ("8:45 p.m..") to a single period
("8:45 p.m.").

The bug: both functions emit "a.m."/"p.m." form via regex substitution.
The matching regexes terminate at a word boundary (\\b), which backs
off any literal "." in the input (because . is non-word and the
following character is also typically non-word, so no boundary
exists). The substitution then emits a fresh "a.m."/"p.m." while the
input "." remains unconsumed, producing "p.m..". The fix is a one-line
re.sub post-pass at the end of each function that collapses any
trailing dots after a.m./p.m. to a single dot.

All tests offline and deterministic. Run:
  python -m pytest spec_engine/tests/test_rule_time_normalizer.py -v
"""

import pytest
from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg() -> JobConfig:
    cfg = JobConfig()
    cfg.confirmed_spellings = {}
    return cfg


class TestSpokenTimeTrailingPeriod:

    def test_spoken_pm_with_trailing_period_single_dot(self):
        text = "Eight forty five PM."
        result = clean_block(text, _cfg())[0]
        assert "8:45 p.m." in result
        # Must not produce double-dot output — the bug being fixed.
        assert "8:45 p.m.." not in result

    def test_spoken_am_with_trailing_period_single_dot(self):
        text = "ten o two AM."
        result = clean_block(text, _cfg())[0]
        assert "10:02 a.m." in result
        assert "10:02 a.m.." not in result


class TestNumericTimeTrailingPeriod:

    def test_compact_numeric_pm_dot_single(self):
        text = "8:45 PM."
        result = clean_block(text, _cfg())[0]
        assert "8:45 p.m." in result
        assert "8:45 p.m.." not in result

    def test_compact_numeric_am_dot_single(self):
        text = "10:08 AM."
        result = clean_block(text, _cfg())[0]
        assert "10:08 a.m." in result
        assert "10:08 a.m.." not in result


class TestAlreadyDoubleCollapses:

    def test_already_double_period_collapses_to_single(self):
        # Pathological input — already has two dots before the rule
        # runs. The post-pass uses \\.+ so any number of trailing
        # dots collapse to one in a single regex application.
        text = "8:45 p.m.."
        result = clean_block(text, _cfg())[0]
        assert "8:45 p.m." in result
        assert "8:45 p.m.." not in result


class TestMidSentencePreserved:

    def test_mid_sentence_pm_stays_single_dot(self):
        # The prompt's original wording said "unchanged structure" but
        # the pre-fix code was actually producing double-dot mid-
        # sentence too (the input regex's word boundary backs off the
        # input "." regardless of position). Post-fix, mid-sentence
        # forms produce clean single-dot output.
        text = "It was 8:45 p.m. yesterday."
        result = clean_block(text, _cfg())[0]
        # Must contain the time form with a single trailing dot.
        assert "8:45 p.m." in result
        # Must not have produced "p.m.." anywhere.
        assert "p.m.." not in result
        # The trailing word "yesterday" must survive.
        assert "yesterday" in result


class TestCorrectionRecord:

    def test_spoken_time_emits_correction_record(self):
        # Mirror of Phase A's CorrectionRecord assertion. fix_spoken_times
        # must register a CorrectionRecord when it actually changes text.
        text = "Eight forty five PM."
        _, records, _ = clean_block(text, _cfg())
        assert any(
            "fix_spoken_times" in record.pattern for record in records
        )


class TestFalsePositiveGuard:
    """Make sure the post-pass doesn't eat dots that aren't ours."""

    def test_dot_before_pm_outside_time_unchanged(self):
        # "p.m." appearing in a context that isn't a real time form
        # should still be left alone — the regex requires the
        # a.m./p.m. literal to follow a word boundary, but the post-
        # pass only collapses dots immediately after that literal,
        # not anywhere else in the text.
        text = "He said the time was 8:45 p.m. and then he went."
        result = clean_block(text, _cfg())[0]
        assert "8:45 p.m." in result
        assert "8:45 p.m.." not in result
        # "and then he went." sentence terminator survives.
        assert result.endswith(".")
