from clean_format import formatter


class DummyRespPart:
    type = "text"

    def __init__(self, text):
        self.text = text


class DummyClient:
    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        idx = len(self.calls)
        return type("R", (), {"content": [DummyRespPart(f"Q.\tchunk {idx}")]})


def test_chunking_for_long_transcript():
    raw = "\n\n".join([f"Speaker 0: block {i}" for i in range(20)])
    chunks = formatter._split_blocks(raw, max_chars=60)
    assert len(chunks) > 1


def test_case_meta_included_in_message():
    client = DummyClient()
    case_meta = {"cause_number": "123", "witness_name": "Jane Doe"}
    result = formatter.format_transcript("Speaker 0: hello", case_meta, client=client)
    assert "cause_number" in client.calls[0]["messages"][0]["content"]
    assert result == "Q.\tchunk 1"
