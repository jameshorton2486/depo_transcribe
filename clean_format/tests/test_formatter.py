from __future__ import annotations

from types import SimpleNamespace

from clean_format.formatter import build_user_message, format_transcript, split_transcript


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        chunk_number = len(self.calls)
        return SimpleNamespace(content=[SimpleNamespace(text=f"LABEL:\tchunk {chunk_number}")])


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_split_transcript_chunks_large_input_on_block_boundaries():
    raw_text = "\n\n".join(f"Speaker 0: block {index} " + ("x" * 80) for index in range(20))
    chunks = split_transcript(raw_text, max_chunk_chars=500)
    assert len(chunks) > 1


def test_format_transcript_includes_case_meta_in_user_message():
    client = _FakeClient()
    case_meta = {"witness_name": "Bianca Caram", "reporter_name": "Miah Bardot"}
    format_transcript("Speaker 0: hello", case_meta, client=client)
    message = client.messages.calls[0]["messages"][0]["content"]
    assert '"witness_name": "Bianca Caram"' in message


def test_build_user_message_labels_chunk_position():
    message = build_user_message("Speaker 0: hello", {"cause_number": "DC-25-13430"}, 2, 4)
    assert "Transcript chunk 2 of 4" in message
