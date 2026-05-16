"""Tests for clean_format.formatter — canonical UFM / Miah Bardot contract.

Canonical output shape (locked by clean_format/prompt.py VERBATIM_TRANSCRIPT_REMINDER):
  Q/A           : \\tQ.\\t{text}      /     \\tA.\\t{text}
  Speaker       : \\t\\t\\t{LABEL}:  {text}     (two spaces after colon)
  Parenthetical : \\t\\t\\t\\t({text}.)
  Honorifics    : MR.  / MS.  / DR.  (two spaces after the period)
  Reporter      : THE REPORTER       (never "COURT REPORTER", never "THE COURT REPORTER")
  Videographer  : THE VIDEOGRAPHER   (never bare "VIDEOGRAPHER")

The formatter accepts both canonical input (already conforming) and legacy
intermediate shape ("Q.\\t…", "LABEL:\\t…") and always emits canonical.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from clean_format.formatter import (
    ContentLossError,
    OutputTruncatedError,
    _count_input_utterances,
    _count_output_utterances,
    _postprocess_formatted_text,
    build_user_message,
    format_transcript,
    format_transcript_with_status,
    split_transcript,
)

# _write_cleanup_status_sidecar lives in ui.tab_transcribe and may not be
# available in older snapshots of the tree. Guard the import so the rest of
# the suite runs cleanly; the dependent test is skipped if unavailable.
try:
    from ui.tab_transcribe import _write_cleanup_status_sidecar
except ImportError:  # pragma: no cover
    _write_cleanup_status_sidecar = None  # type: ignore[assignment]


class _FakeMessages:
    def __init__(self, text: str | None = None, stop_reason: str | None = None) -> None:
        self.calls: list[dict] = []
        self._text = text
        self._stop_reason = stop_reason

    def create(self, **kwargs):
        self.calls.append(kwargs)
        chunk_number = len(self.calls)
        payload = self._text if self._text is not None else f"LABEL:\tchunk {chunk_number}"
        return SimpleNamespace(
            content=[SimpleNamespace(text=payload)],
            stop_reason=self._stop_reason,
        )


class _FakeClient:
    def __init__(self, text: str | None = None, stop_reason: str | None = None) -> None:
        self.messages = _FakeMessages(text=text, stop_reason=stop_reason)


class _EchoMessages:
    """Echoes the chunk body back as the model response.

    Used by the verbatim-preservation tests below to verify that the cleanup
    pipeline does not silently mutate filler words, stutters, repeated words,
    or false-start dashes. These are LEGAL NON-NEGOTIABLES for court-reporter
    output (UFM §3.7, §3.8 and Morson's chapters on verbatim fidelity).
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = kwargs["messages"][0]["content"]
        marker = "Transcript chunk "
        body_start = content.find(marker)
        newline = content.find("\n", body_start)
        text = content[newline + 1:].rstrip()
        return SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            stop_reason="end_turn",
        )


class _EchoClient:
    def __init__(self) -> None:
        self.messages = _EchoMessages()


# ── split_transcript ──────────────────────────────────────────────────────────


def test_split_transcript_chunks_large_input_on_block_boundaries():
    raw_text = "\n\n".join(
        f"Speaker 0: block {index} " + ("x" * 80) for index in range(20)
    )
    chunks = split_transcript(raw_text, max_chunk_chars=500)
    assert len(chunks) > 1


# ── build_user_message / format_transcript plumbing ───────────────────────────


def test_format_transcript_includes_case_meta_in_user_message():
    client = _FakeClient()
    case_meta = {"witness_name": "Bianca Caram", "reporter_name": "Miah Bardot"}
    format_transcript("Speaker 0: hello", case_meta, client=client)
    message = client.messages.calls[0]["messages"][0]["content"]
    assert '"witness_name": "Bianca Caram"' in message


def test_build_user_message_labels_chunk_position():
    message = build_user_message(
        "Speaker 0: hello", {"cause_number": "DC-25-13430"}, 2, 4
    )
    assert "Transcript chunk 2 of 4" in message


# ── _postprocess_formatted_text: canonical contract ───────────────────────────


def test_postprocess_emits_canonical_qa_with_leading_tab():
    """Canonical Q/A is `\\tQ.\\t…` / `\\tA.\\t…` — one leading tab."""
    assert _postprocess_formatted_text("Q.\tWhat is your name?") == \
           "\tQ.\tWhat is your name?"
    assert _postprocess_formatted_text("A.\tBianca Caram.") == \
           "\tA.\tBianca Caram."


def test_postprocess_emits_canonical_speaker_three_tabs_two_spaces_after_colon():
    """Canonical speaker colloquy is `\\t\\t\\tLABEL:  text` — 3 tabs, 2 spaces after colon."""
    result = _postprocess_formatted_text("THE WITNESS:\tYes.")
    assert result == "\t\t\tTHE WITNESS:  Yes."


def test_postprocess_normalizes_honorific_to_double_space_after_period():
    """Canonical honorifics MR./MS./DR. take two spaces after the period in labels."""
    assert _postprocess_formatted_text("MR. DUNNELL:\tObjection. Form.") == \
           "\t\t\tMR.  DUNNELL:  Objection.  Form."
    assert _postprocess_formatted_text("MS. MALONEY:\tWhat year was this?") == \
           "\t\t\tMS.  MALONEY:  What year was this?"
    assert _postprocess_formatted_text("DR. KARAM:\tI am.") == \
           "\t\t\tDR.  KARAM:  I am."


def test_postprocess_normalizes_court_reporter_variants_to_the_reporter():
    """COURT REPORTER, THE COURT REPORTER, THE REPORTER all collapse to canonical THE REPORTER."""
    assert _postprocess_formatted_text("COURT REPORTER:\tCause Number C-1628.") == \
           "\t\t\tTHE REPORTER:  Cause Number C-1628."
    assert _postprocess_formatted_text("THE COURT REPORTER:\tPlease raise your right hand.") == \
           "\t\t\tTHE REPORTER:  Please raise your right hand."
    assert _postprocess_formatted_text("THE REPORTER:\tAlready normalized.") == \
           "\t\t\tTHE REPORTER:  Already normalized."


def test_postprocess_normalizes_bare_videographer_to_the_videographer():
    """Bare VIDEOGRAPHER and THE VIDEOGRAPHER both collapse to canonical THE VIDEOGRAPHER."""
    assert _postprocess_formatted_text("VIDEOGRAPHER:\tThe time is 08:12 a.m.") == \
           "\t\t\tTHE VIDEOGRAPHER:  The time is 8:12 a.m."
    assert _postprocess_formatted_text("THE VIDEOGRAPHER:\tToday is 05/07/2026.") == \
           "\t\t\tTHE VIDEOGRAPHER:  Today is 05/07/2026."


def test_postprocess_rescues_dunnell_misattributed_to_videographer():
    """VIDEOGRAPHER block saying 'Billy Dunnell here on behalf of…' is relabeled to MR.  DUNNELL."""
    result = _postprocess_formatted_text(
        "VIDEOGRAPHER:\tBilly Dunnell here on behalf of Dr. Karam."
    )
    assert result == "\t\t\tMR.  DUNNELL:  Billy Dunnell here on behalf of Dr. Karam."


def test_postprocess_emits_canonical_parenthetical_four_tabs():
    """Canonical parentheticals are `\\t\\t\\t\\t(text.)` — four leading tabs."""
    assert _postprocess_formatted_text("(The witness was sworn.)") == \
           "\t\t\t\t(The witness was sworn.)"


def test_postprocess_preserves_by_lines_and_examination_headers():
    """BY-lines and EXAMINATION headers are flush left with no transformation."""
    assert _postprocess_formatted_text("BY MR. GARZA:") == "BY MR. GARZA:"
    assert _postprocess_formatted_text("EXAMINATION") == "EXAMINATION"
    assert _postprocess_formatted_text("FURTHER EXAMINATION") == "FURTHER EXAMINATION"


def test_postprocess_round_trips_already_canonical_input():
    """Canonical input should pass through unchanged (idempotency)."""
    assert _postprocess_formatted_text("\tQ.\tAlready canonical.") == \
           "\tQ.\tAlready canonical."
    assert _postprocess_formatted_text("\t\t\tMS.  MALONEY:  Already canonical.") == \
           "\t\t\tMS.  MALONEY:  Already canonical."
    assert _postprocess_formatted_text("\t\t\t\t(Already canonical.)") == \
           "\t\t\t\t(Already canonical.)"


def test_postprocess_applies_label_and_title_rules_across_full_block():
    """Multi-line block: verify canonical Q/A and speaker shape across all lines."""
    text = (
        "COURT REPORTER:\tDr. Bianca Caram is here.\n"
        "VIDEOGRAPHER:\tBilly Dunnell here on behalf of Dr. Karam.\n"
        "VIDEOGRAPHER:\tThe time is 08:12 a.m.\n"
        "Q.\tDid Dr. Brittany Anders speak with Ms. Kuipers?"
    )

    result = _postprocess_formatted_text(text)

    assert "\t\t\tTHE REPORTER:  Dr. Bianca Caram is here." in result
    assert "\t\t\tMR.  DUNNELL:  Billy Dunnell here on behalf of Dr. Karam." in result
    assert "\t\t\tTHE VIDEOGRAPHER:  The time is 8:12 a.m." in result
    assert "\tQ.\tDid Dr. Brittany Anders speak with Ms. Kuipers?" in result


def test_postprocess_uses_two_spaces_after_sentence_endings():
    result = _postprocess_formatted_text("A.\tYes. no? maybe.")
    assert result == "\tA.\tYes.  no?  maybe."


def test_postprocess_normalizes_interruption_dashes():
    result = _postprocess_formatted_text(
        "Q.\tOkay — if you need a break - let me know."
    )
    assert result == "\tQ.\tOkay -- if you need a break - let me know."


# ── format_transcript: stop-reason and content-loss gates ────────────────────


def test_format_transcript_raises_output_truncated_error_on_max_tokens(caplog):
    """When the model returns stop_reason='max_tokens', the formatter aborts."""
    client = _FakeClient(text="Q.\tpartial output.", stop_reason="max_tokens")
    raw_text = "Speaker 0: " + " ".join(f"word{i}" for i in range(120))
    with pytest.raises(OutputTruncatedError) as exc_info:
        format_transcript(raw_text, {}, client=client)
    assert exc_info.value.chunk_index == 1
    assert "max_tokens" in caplog.text


def test_format_transcript_allows_non_truncated_stop_reason():
    """Non-truncated stop reasons (end_turn, etc.) pass through normally."""
    client = _FakeClient(stop_reason="end_turn")
    result = format_transcript("Speaker 0: hello", {}, client=client)
    # _FakeMessages emits "LABEL:\tchunk 1" → postprocess canonicalizes it
    assert result == "\t\t\tLABEL:  chunk 1"


def test_format_transcript_raises_content_loss_error_below_threshold():
    """Content-loss gate aborts when retention drops below MIN_UTTERANCE_RETENTION_DOCUMENT."""
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(50))  # 50/100 = 50% << 85%
    client = _FakeClient(text=output)
    with pytest.raises(ContentLossError):
        format_transcript(raw_text, {}, client=client)


def test_content_loss_gate_allows_ratio_above_threshold():
    """At-or-above threshold retention passes through."""
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(95))  # 95% ≥ 85%
    client = _FakeClient(text=output)
    result = format_transcript(raw_text, {}, client=client)
    expected = "\n".join(f"\t\t\tLABEL:  line {n}" for n in range(95))
    assert result == expected


def test_content_loss_gate_skips_zero_input_utterances():
    """No 'Speaker N:' lines in input → gate is skipped (division-by-zero safety)."""
    client = _FakeClient()
    result = format_transcript("plain text with no speaker labels", {}, client=client)
    assert result == "\t\t\tLABEL:  chunk 1"


def test_format_transcript_with_status_returns_success_schema():
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(100))
    client = _FakeClient(text=output)
    result, status = format_transcript_with_status(raw_text, {}, client=client)
    expected = "\n".join(f"\t\t\tLABEL:  line {n}" for n in range(100))
    assert result == expected
    assert status["success"] is True
    assert status["failure_reason"] is None
    assert status["input_utterance_count"] == 100
    assert status["output_utterance_count"] == 100
    assert status["utterance_retention_ratio"] == 1.0
    assert status["chunk_count"] >= 1


# ── Verbatim fidelity (LEGAL NON-NEGOTIABLES) ─────────────────────────────────
# Per Texas UFM §3.7, §3.8 and Morson's English Guide: filler words, stutters,
# repeated words, and false starts must be preserved verbatim. The cleanup
# pipeline must never silently mutate them. These tests exercise the
# end-to-end path with an echo client so any regression in the postprocess
# pipeline that strips, modifies, or normalizes verbatim speech is caught.


def test_format_transcript_preserves_filler_words():
    result = format_transcript("Speaker 0: Uh, yes, ma'am.", {}, client=_EchoClient())
    assert "Uh, yes, ma'am." in result


def test_format_transcript_preserves_stutters():
    result = format_transcript(
        "Speaker 0: I -- I don't remember.", {}, client=_EchoClient()
    )
    assert "I -- I don't remember." in result


def test_format_transcript_preserves_repeated_words():
    result = format_transcript(
        "Speaker 0: Well, well, I think so.", {}, client=_EchoClient()
    )
    assert "Well, well, I think so." in result


def test_format_transcript_preserves_false_starts():
    result = format_transcript(
        "Speaker 0: It was on Tues-- Wednesday.", {}, client=_EchoClient()
    )
    assert "Tues-- Wednesday" in result


# ── Utterance-count regex sanity ──────────────────────────────────────────────


def test_utterance_count_regex_matches_speaker_fixture_shape():
    raw_text = "\n\n".join(f"Speaker {n % 4}: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(70))
    assert _count_input_utterances(raw_text) == 100
    assert _count_output_utterances(output) == 70


# ── ContentLossError raise paths ──────────────────────────────────────────────


def test_format_transcript_with_status_forced_content_loss(monkeypatch):
    """Threshold-raising variant: monkeypatch the gate to 0.99 so 95% retention fails."""
    monkeypatch.setattr(
        "clean_format.formatter.MIN_UTTERANCE_RETENTION_DOCUMENT", 0.99
    )
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(95))
    with pytest.raises(ContentLossError):
        format_transcript_with_status(raw_text, {}, client=_FakeClient(text=output))


# ── Cleanup status sidecar serialization ──────────────────────────────────────


@pytest.mark.skipif(
    _write_cleanup_status_sidecar is None,
    reason="ui.tab_transcribe._write_cleanup_status_sidecar not present in this snapshot",
)
def test_write_cleanup_status_sidecar_writes_failure_schema(tmp_path):
    status = {
        "schema_version": "1.0",
        "timestamp_utc": "2026-05-15T03:42:11Z",
        "case_folder": str(tmp_path),
        "model": "claude-sonnet-4-6",
        "success": False,
        "failure_reason": "content_loss",
        "input_utterance_count": 100,
        "output_utterance_count": 70,
        "utterance_retention_ratio": 0.7,
        "chunk_count": None,
        "chunks_truncated": [],
        "errors": ["Content loss detected"],
    }
    _write_cleanup_status_sidecar(tmp_path, status)
    saved = json.loads(
        (tmp_path / "cleanup_status.json").read_text(encoding="utf-8")
    )
    assert set(saved) == set(status)
    assert saved["success"] is False
    assert saved["failure_reason"] == "content_loss"
    assert isinstance(saved["errors"], list)
    assert saved["errors"][0]
