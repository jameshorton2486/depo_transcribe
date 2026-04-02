from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_run_transcription_job_does_not_use_or_persist_keyterms(monkeypatch, tmp_path):
    import core.job_runner as job_runner

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")

    captured: dict = {}

    monkeypatch.setattr(
        job_runner,
        "resolve_or_create_case",
        lambda *args, **kwargs: (str(tmp_path / "case"), {"errors": [], "created": []}),
    )

    monkeypatch.setattr("pipeline.preprocessor.check_ffmpeg", lambda: True)
    monkeypatch.setattr(
        "pipeline.preprocessor.validate_audio_file",
        lambda _path: {"valid": True, "duration": 60.0, "format": "wav"},
    )
    monkeypatch.setattr(
        "pipeline.preprocessor.normalize_audio",
        lambda *args, **kwargs: str(tmp_path / "normalized.wav"),
    )
    monkeypatch.setattr(
        "pipeline.chunker.chunk_audio",
        lambda *args, **kwargs: [
            SimpleNamespace(file_path=str(tmp_path / "chunk.wav"), start_seconds=0.0, end_seconds=60.0)
        ],
    )
    monkeypatch.setattr("pipeline.chunker.cleanup_chunks", lambda _chunks: None)

    def _fake_transcribe_chunk(*args, **kwargs):
        captured["transcribe_kwargs"] = kwargs
        return {"raw": {}, "utterances": [{"speaker": 1, "transcript": "Test testimony."}], "words": []}

    monkeypatch.setattr("pipeline.transcriber.transcribe_chunk", _fake_transcribe_chunk)
    monkeypatch.setattr(
        "pipeline.assembler.reassemble_chunks",
        lambda _results, _offsets: {
            "transcript": "Test testimony.",
            "utterances": [{"speaker": 1, "speaker_label": "Speaker 1", "transcript": "Test testimony."}],
            "words": [],
        },
    )

    def _fake_merge_and_save(_case_root, **kwargs):
        captured["merge_kwargs"] = kwargs
        return tmp_path / "case" / "source_docs" / "job_config.json"

    monkeypatch.setattr("core.job_config_manager.merge_and_save", _fake_merge_and_save)

    results = []
    job_runner.run_transcription_job(
        audio_path=str(audio_path),
        model="nova-3",
        quality="Default",
        utt_split=1.2,
        base_dir=str(tmp_path),
        keyterms=["Matthew Coger"],
        confirmed_spellings={"Koger": "Coger"},
        ufm_fields={"cause_number": "2025-CI-19595"},
        done_callback=lambda result: results.append(result),
    )

    assert (
        "keyterms" not in captured["transcribe_kwargs"]
        and "deepgram_keyterms" not in captured["merge_kwargs"]
        and results[0]["success"] is True
    )
