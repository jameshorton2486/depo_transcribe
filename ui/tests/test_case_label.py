"""
Headless tests for TranscriptTab._update_case_label.

The case label shows "Case: {cause} ({last_name})" next to the Transcript
tab's title bar. Inputs are read out of self._job_config_data["ufm_fields"];
the formatter must handle missing fields gracefully (empty string for the
label, not a KeyError or "Case: None ()").

Tests use a SimpleNamespace + a stub _case_label that captures the most
recent .configure(text=...) call, so the full UI doesn't need to be
instantiated.
"""

from types import SimpleNamespace

from ui.tab_transcript import TranscriptTab


class _StubLabel:
    def __init__(self):
        self.text = None

    def configure(self, *, text):
        self.text = text


def _run(job_config_data):
    fake = SimpleNamespace(
        _job_config_data=job_config_data,
        _case_label=_StubLabel(),
    )
    TranscriptTab._update_case_label(fake)
    return fake._case_label.text


def test_cause_and_witness_renders_full_label():
    text = _run({"ufm_fields": {"cause_number": "23-104-CV", "witness_name": "Matthew Coger"}})
    assert text == "Case: 23-104-CV (Coger)"


def test_cause_only_drops_parens():
    text = _run({"ufm_fields": {"cause_number": "23-104-CV"}})
    assert text == "Case: 23-104-CV"


def test_witness_only_shows_parens_only():
    text = _run({"ufm_fields": {"witness_name": "Matthew Coger"}})
    assert text == "Case: (Coger)"


def test_empty_ufm_clears_label():
    text = _run({"ufm_fields": {}})
    assert text == ""


def test_missing_ufm_key_clears_label():
    text = _run({})
    assert text == ""


def test_empty_config_clears_label():
    text = _run({})
    assert text == ""


def test_single_token_witness_uses_full_name_as_last():
    text = _run({"ufm_fields": {"cause_number": "X", "witness_name": "Cher"}})
    assert text == "Case: X (Cher)"


def test_whitespace_around_cause_is_stripped():
    text = _run({"ufm_fields": {"cause_number": "  23-104-CV  ", "witness_name": "Matt Coger"}})
    assert text == "Case: 23-104-CV (Coger)"


def test_non_dict_ufm_fields_falls_back_to_empty():
    text = _run({"ufm_fields": "not a dict"})
    assert text == ""


def test_no_case_label_attribute_is_safe():
    # If _build_ui hasn't run yet, _update_case_label must not raise.
    fake = SimpleNamespace(_job_config_data={"ufm_fields": {"cause_number": "X"}})
    TranscriptTab._update_case_label(fake)  # no exception expected
