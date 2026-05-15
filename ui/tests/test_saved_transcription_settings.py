from __future__ import annotations

from ui.tab_transcribe import TranscribeTab


class _DummyVar:
    def __init__(self, value: str = ""):
        self.value = value

    def set(self, value: str) -> None:
        self.value = value


def test_apply_saved_transcription_settings_restores_intake_artifacts():
    tab = TranscribeTab.__new__(TranscribeTab)
    tab._confirmed_spellings = {"old": "value"}
    tab._pdf_keyterms = ["stale"]
    tab._speaker_map_suggestion = {}
    tab._saved_speaker_map = {}
    tab._model_var = _DummyVar()
    tab._quality_var = _DummyVar()
    tab._correction_mode = False

    TranscribeTab._apply_saved_transcription_settings(
        tab,
        {
            "model": "nova-3",
            "audio_quality": "Default (fair audio)",
            "confirmed_spellings": {"Koger": "Coger"},
            "deepgram_keyterms": ["Matthew Coger", "Cause Number"],
            "speaker_map_suggestion": {"deponent": "Chris Epley"},
            "ufm_fields": {"speaker_map": {"1": "THE WITNESS"}},
        },
    )

    assert tab._confirmed_spellings == {"Koger": "Coger"}
    assert tab._pdf_keyterms == ["Matthew Coger", "Cause Number"]
    assert tab._speaker_map_suggestion == {"deponent": "Chris Epley"}
    assert tab._saved_speaker_map == {1: "THE WITNESS"}
