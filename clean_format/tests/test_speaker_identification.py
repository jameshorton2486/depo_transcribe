from __future__ import annotations

from types import SimpleNamespace

from clean_format.formatter import format_transcript


class _StaticMessages:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=self.response_text)])


class _StaticClient:
    def __init__(self, response_text: str) -> None:
        self.messages = _StaticMessages(response_text)


def test_formatter_returns_mocked_speaker_labels():
    raw_text = (
        "Speaker 0: Today's date is April 9, 2026.\n\nSpeaker 1: Raise your right hand."
    )
    client = _StaticClient(
        "THE VIDEOGRAPHER:\tToday's date is April 9, 2026.\n\nTHE COURT REPORTER:\tRaise your right hand."
    )
    result = format_transcript(
        raw_text, {"witness_name": "Bianca Caram"}, client=client
    )
    assert "THE VIDEOGRAPHER:" in result
