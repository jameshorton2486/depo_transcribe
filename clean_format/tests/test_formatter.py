from __future__ import annotations

from types import SimpleNamespace

from clean_format.formatter import (
    _postprocess_formatted_text,
    build_user_message,
    format_transcript,
    split_transcript,
)


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        chunk_number = len(self.calls)
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"LABEL:\tchunk {chunk_number}")]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


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

    assert "THE REPORTER:\tDr. Bianca Caram is here." in result
    assert "MR. DUNNELL:\tBilly Dunnell here on behalf of Dr. Karam." in result
    assert "THE VIDEOGRAPHER:\tThe time is 8:12 a.m." in result
    assert "Q.\tDid Dr. Brittany Anders speak with Ms. Kuipers?" in result


def test_postprocess_formatted_text_uses_two_spaces_after_sentence_endings():
    result = _postprocess_formatted_text("A.\tYes. no? maybe.")
    assert result == "A.\tYes.  no?  maybe."


def test_postprocess_formatted_text_normalizes_interruption_dashes():
    result = _postprocess_formatted_text(
        "Q.\tOkay — if you need a break - let me know."
    )
    assert result == "Q.\tOkay -- if you need a break - let me know."
