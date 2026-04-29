from clean_format import formatter


class DummyRespPart:
    type = "text"

    def __init__(self, text):
        self.text = text


class DummyClient:
    def __init__(self, text):
        self.messages = self
        self.text = text

    def create(self, **kwargs):
        return type("R", (), {"content": [DummyRespPart(self.text)]})


def test_speaker_labels_preserved_from_model_output():
    expected = "THE VIDEOGRAPHER:\tToday's date is April 9, 2026.\n\nBY MS. SMITH:\n\nQ.\tPlease state your name.\n\nA.\tBianca Caram."
    client = DummyClient(expected)
    meta = {"witness_name": "Bianca Caram", "reporter_name": "Jane Reporter"}
    output = formatter.format_transcript("Speaker 0: hi", meta, client=client)
    assert "THE VIDEOGRAPHER:\t" in output
    assert "Q.\tPlease state your name." in output
