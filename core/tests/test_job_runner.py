from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_run_transcription_job_uses_and_persists_keyterms(monkeypatch, tmp_path):
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

    assert "Matthew Coger" in captured["transcribe_kwargs"]["keyterms"]
    assert captured["merge_kwargs"]["deepgram_keyterms"] == ["Matthew Coger"]
    assert results[0]["success"] is True


def test_run_transcription_job_transcribes_both_dual_channels(monkeypatch, tmp_path):
    import core.job_runner as job_runner

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")

    captured: dict = {"transcribed_paths": []}

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
    monkeypatch.setattr("pipeline.preprocessor.is_stereo_dual_channel", lambda _path: True)

    def _fake_normalize(path, *args, **kwargs):
        stem = Path(path).stem
        return str(tmp_path / f"{stem}_normalized.wav")

    monkeypatch.setattr("pipeline.preprocessor.normalize_audio", _fake_normalize)
    monkeypatch.setattr(
        "pipeline.preprocessor.split_stereo_channels",
        lambda *args, **kwargs: (str(tmp_path / "left.wav"), str(tmp_path / "right.wav")),
    )

    def _fake_chunk_audio(path, *args, **kwargs):
        stem = Path(path).stem
        return [SimpleNamespace(file_path=str(tmp_path / f"{stem}_chunk.wav"), start_seconds=0.0, end_seconds=60.0)]

    monkeypatch.setattr("pipeline.chunker.chunk_audio", _fake_chunk_audio)
    monkeypatch.setattr("pipeline.chunker.cleanup_chunks", lambda _chunks: None)

    def _fake_transcribe_chunk(file_path, **kwargs):
        captured["transcribed_paths"].append(Path(file_path).name)
        transcript = "Question" if "left" in file_path else "Answer"
        return {
            "raw": {"file": file_path},
            "utterances": [{"speaker": 0, "transcript": transcript, "start": 0.0, "end": 1.0}],
            "words": [{"word": transcript.lower(), "speaker": 0, "start": 0.0, "end": 1.0}],
            "transcript": transcript,
        }

    monkeypatch.setattr("pipeline.transcriber.transcribe_chunk", _fake_transcribe_chunk)
    monkeypatch.setattr(
        "pipeline.assembler.reassemble_chunks",
        lambda results, _offsets: {
            "transcript": results[0]["transcript"],
            "utterances": results[0]["utterances"],
            "words": results[0]["words"],
            "raw_chunks": [results[0]["raw"]],
        },
    )
    monkeypatch.setattr(
        "pipeline.assembler.merge_channel_assemblies",
        lambda assemblies: {
            "transcript": "Speaker 0: Question\n\nSpeaker 1: Answer",
            "utterances": [
                {"speaker": 0, "speaker_label": "Speaker 0", "transcript": "Question", "start": 0.0, "end": 1.0},
                {"speaker": 1, "speaker_label": "Speaker 1", "transcript": "Answer", "start": 0.0, "end": 1.0},
            ],
            "words": [
                {"word": "question", "speaker": 0, "start": 0.0, "end": 1.0},
                {"word": "answer", "speaker": 1, "start": 0.0, "end": 1.0},
            ],
            "raw_chunks": [{"channel": 0, "raw": {}}, {"channel": 1, "raw": {}}],
        },
    )
    monkeypatch.setattr(
        "core.job_config_manager.merge_and_save",
        lambda *_args, **_kwargs: tmp_path / "case" / "source_docs" / "job_config.json",
    )

    results = []
    job_runner.run_transcription_job(
        audio_path=str(audio_path),
        model="nova-3",
        quality="Default",
        utt_split=1.2,
        base_dir=str(tmp_path),
        keyterms=["Matthew Coger"],
        done_callback=lambda result: results.append(result),
    )

    assert captured["transcribed_paths"] == ["left_normalized_chunk.wav", "right_normalized_chunk.wav"]
    assert results[0]["success"] is True
