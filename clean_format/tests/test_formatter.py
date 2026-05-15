from __future__ import annotations

import json
import logging
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
from ui.tab_transcribe import _write_cleanup_status_sidecar


class _FakeMessages:
    def __init__(self, *, stop_reason: str = "", text: str | None = None) -> None:
        self.calls: list[dict] = []
        self.stop_reason = stop_reason
        self.text = text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        chunk_number = len(self.calls)
        return SimpleNamespace(
            content=[
                SimpleNamespace(text=self.text or f"LABEL:\tchunk {chunk_number}")
            ],
            stop_reason=self.stop_reason,
        )


class _FakeClient:
    def __init__(self, *, stop_reason: str = "", text: str | None = None) -> None:
        self.messages = _FakeMessages(stop_reason=stop_reason, text=text)


class _EchoMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = kwargs["messages"][0]["content"]
        marker = "Transcript chunk "
        body_start = content.find(marker)
        newline = content.find("\n", body_start)
        text = content[newline + 1 :].rstrip()
        return SimpleNamespace(content=[SimpleNamespace(text=text)], stop_reason="end_turn")


class _EchoClient:
    def __init__(self) -> None:
        self.messages = _EchoMessages()


def test_split_transcript_chunks_large_input_on_block_boundaries():
    raw_text = "\n\n".join(
        f"Speaker 0: block {index} " + ("x" * 80) for index in range(20)
    )
    chunks = split_transcript(raw_text, max_chunk_chars=500)
    assert len(chunks) > 1


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


def test_postprocess_formatted_text_applies_label_and_title_rules():
    text = (
        "COURT REPORTER:\tDoctor Bianca Caram is here.\n"
        "VIDEOGRAPHER:\tBilly Dunnell here on behalf of Doctor Karam.\n"
        "VIDEOGRAPHER:\tThe time is 08:12 a.m.\n"
        "Q.\tDid Doctor Brittany Anders speak with Miss Kuipers?"
    )

    result = _postprocess_formatted_text(text)

    assert "THE REPORTER:\tDoctor Bianca Caram is here." in result
    assert "MR. DUNNELL:\tBilly Dunnell here on behalf of Doctor Karam." in result
    assert "THE VIDEOGRAPHER:\tThe time is 8:12 a.m." in result
    assert "Q.\tDid Doctor Brittany Anders speak with Miss Kuipers?" in result


def test_postprocess_formatted_text_normalizes_the_court_reporter_label():
    result = _postprocess_formatted_text(
        "THE COURT REPORTER:\tPlease raise your right hand."
    )
    assert result == "THE REPORTER:\tPlease raise your right hand."


def test_postprocess_formatted_text_preserves_single_space_in_mr_label():
    result = _postprocess_formatted_text("MR. DUNNELL:\tstate your appearance.")
    assert result == "MR. DUNNELL:\tstate your appearance."


def test_postprocess_formatted_text_uses_two_spaces_after_sentence_endings():
    result = _postprocess_formatted_text("A.\tYes. no? maybe.")
    assert result == "A.\tYes.  no?  maybe."


def test_postprocess_formatted_text_normalizes_interruption_dashes():
    result = _postprocess_formatted_text(
        "Q.\tOkay — if you need a break - let me know."
    )
    assert result == "Q.\tOkay -- if you need a break - let me know."


def test_format_transcript_raises_output_truncated_error_on_max_tokens(caplog):
    client = _FakeClient(stop_reason="max_tokens")
    with caplog.at_level(logging.ERROR), pytest.raises(OutputTruncatedError):
        format_transcript("Speaker 0: hello", {}, client=client)
    assert "stop_reason=max_tokens" in caplog.text


def test_format_transcript_allows_non_truncated_stop_reason():
    client = _FakeClient(stop_reason="end_turn")
    result = format_transcript("Speaker 0: hello", {}, client=client)
    assert result == "LABEL:\tchunk 1"


def test_content_loss_gate_allows_ratio_above_threshold():
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(95))
    result = format_transcript(raw_text, {}, client=_FakeClient(text=output))
    assert result == output


def test_content_loss_gate_raises_below_threshold():
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(70))
    with pytest.raises(ContentLossError):
        format_transcript(raw_text, {}, client=_FakeClient(text=output))


def test_content_loss_gate_skips_zero_input_utterances():
    result = format_transcript("plain text with no speaker labels", {}, client=_FakeClient())
    assert result == "LABEL:\tchunk 1"


def test_utterance_count_regex_matches_speaker_fixture_shape():
    raw_text = "\n\n".join(f"Speaker {n % 4}: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(70))
    assert _count_input_utterances(raw_text) == 100
    assert _count_output_utterances(output) == 70


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


def test_format_transcript_with_status_returns_success_schema():
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(100))
    result, status = format_transcript_with_status(
        raw_text, {}, client=_FakeClient(text=output)
    )
    assert result == output
    assert status == {
        "schema_version": "1.0",
        "model": "claude-sonnet-4-6",
        "success": True,
        "failure_reason": None,
        "input_utterance_count": 100,
        "output_utterance_count": 100,
        "utterance_retention_ratio": 1.0,
        "chunk_count": 1,
        "chunks_truncated": [],
        "errors": [],
    }


def test_format_transcript_with_status_forced_content_loss(monkeypatch):
    monkeypatch.setattr("clean_format.formatter.MIN_UTTERANCE_RETENTION_DOCUMENT", 0.99)
    raw_text = "\n\n".join(f"Speaker 0: line {n}" for n in range(100))
    output = "\n".join(f"LABEL:\tline {n}" for n in range(95))
    with pytest.raises(ContentLossError):
        format_transcript_with_status(raw_text, {}, client=_FakeClient(text=output))


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
    saved = json.loads((tmp_path / "cleanup_status.json").read_text(encoding="utf-8"))
    assert set(saved) == set(status)
    assert saved["success"] is False
    assert saved["failure_reason"] == "content_loss"
    assert isinstance(saved["errors"], list)
    assert saved["errors"][0]
