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


def test_run_transcription_job_uses_audio_analysis_single_path(monkeypatch, tmp_path):
    import core.job_runner as job_runner

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")

    captured: dict = {"transcribed_paths": [], "normalize_kwargs": None, "aligned": False}

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

    analysis = SimpleNamespace(
        tier="ENHANCED",
        is_stereo=True,
        zoom_dual_mono=True,
        mono_strategy="extract_left",
        issues=["Zoom dual-mono detected"],
    )
    monkeypatch.setattr("pipeline.audio_quality.analyze_audio", lambda _path: analysis)

    def _fake_normalize(path, *args, **kwargs):
        captured["normalize_kwargs"] = kwargs
        stem = Path(path).stem
        return str(tmp_path / f"{stem}_normalized.wav")

    monkeypatch.setattr("pipeline.preprocessor.normalize_audio", _fake_normalize)
    monkeypatch.setattr(
        "pipeline.vad_trimmer.trim_silence",
        lambda path, output_path=None: SimpleNamespace(
            output_path=str(tmp_path / "audio_normalized_vad.wav"),
            original_duration_s=60.0,
            trimmed_duration_s=55.0,
            silence_removed_s=5.0,
            speech_segment_count=3,
            was_trimmed=True,
        ),
    )

    def _fake_chunk_audio(path, *args, **kwargs):
        stem = Path(path).stem
        return [SimpleNamespace(file_path=str(tmp_path / f"{stem}_chunk.wav"), start_seconds=0.0, end_seconds=60.0)]

    monkeypatch.setattr("pipeline.chunker.chunk_audio", _fake_chunk_audio)
    monkeypatch.setattr("pipeline.chunker.cleanup_chunks", lambda _chunks: None)

    def _fake_transcribe_chunk(file_path, **kwargs):
        captured["transcribed_paths"].append(Path(file_path).name)
        return {
            "raw": {"file": file_path},
            "utterances": [{"speaker": 0, "transcript": "Question", "start": 0.0, "end": 1.0}],
            "words": [{"word": "question", "speaker": 0, "start": 0.0, "end": 1.0}],
            "transcript": "Question",
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
        "pipeline.pyannote_diarizer.diarize",
        lambda _path: [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}],
    )
    monkeypatch.setattr(
        "pipeline.pyannote_diarizer.align_speakers",
        lambda utterances, _segments: captured.__setitem__("aligned", True) or utterances,
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

    assert captured["normalize_kwargs"]["audio_analysis"] is analysis
    assert captured["transcribed_paths"] == ["audio_normalized_vad_chunk.wav"]
    assert captured["aligned"] is True
    assert results[0]["success"] is True
    assert results[0]["audio_tier"] == "ENHANCED"


def test_run_transcription_job_chunks_processed_vad_audio_not_original(monkeypatch, tmp_path):
    import core.job_runner as job_runner

    audio_path = tmp_path / "original_audio.wav"
    audio_path.write_bytes(b"fake")

    captured: dict = {"chunk_audio_path": None, "transcribed_path": None}

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
        "pipeline.audio_quality.analyze_audio",
        lambda _path: SimpleNamespace(
            tier="CLEAN",
            is_stereo=False,
            zoom_dual_mono=False,
            mono_strategy="average",
            issues=[],
        ),
    )
    monkeypatch.setattr(
        "pipeline.preprocessor.normalize_audio",
        lambda *args, **kwargs: str(tmp_path / "normalized.wav"),
    )
    monkeypatch.setattr(
        "pipeline.vad_trimmer.trim_silence",
        lambda path, output_path=None: SimpleNamespace(
            output_path=str(tmp_path / "normalized_vad.wav"),
            original_duration_s=60.0,
            trimmed_duration_s=55.0,
            silence_removed_s=5.0,
            speech_segment_count=4,
            was_trimmed=True,
        ),
    )

    def _fake_chunk_audio(path, *args, **kwargs):
        captured["chunk_audio_path"] = path
        return [
            SimpleNamespace(
                file_path=str(tmp_path / "normalized_vad_chunk.wav"),
                start_seconds=0.0,
                end_seconds=60.0,
            )
        ]

    monkeypatch.setattr("pipeline.chunker.chunk_audio", _fake_chunk_audio)
    monkeypatch.setattr("pipeline.chunker.cleanup_chunks", lambda _chunks: None)

    def _fake_transcribe_chunk(file_path, **kwargs):
        captured["transcribed_path"] = file_path
        return {
            "raw": {"file": file_path},
            "utterances": [{"speaker": 0, "transcript": "Test", "start": 0.0, "end": 1.0}],
            "words": [{"word": "test", "speaker": 0, "start": 0.0, "end": 1.0}],
            "transcript": "Test",
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
        "core.job_config_manager.merge_and_save",
        lambda *_args, **_kwargs: tmp_path / "case" / "source_docs" / "job_config.json",
    )

    results = []
    job_runner.run_transcription_job(
        audio_path=str(audio_path),
        model="nova-3",
        quality="CLEAN (good/excellent audio)",
        utt_split=1.2,
        base_dir=str(tmp_path),
        done_callback=lambda result: results.append(result),
    )

    assert captured["chunk_audio_path"] == str(tmp_path / "normalized_vad.wav")
    assert captured["transcribed_path"] == str(tmp_path / "normalized_vad_chunk.wav")
    assert captured["chunk_audio_path"] != str(audio_path)
    assert results[0]["success"] is True
