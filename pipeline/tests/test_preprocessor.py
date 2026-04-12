from pathlib import Path
from types import SimpleNamespace

from pipeline import preprocessor


def _setup_normalize_mocks(monkeypatch, tmp_path):
    input_path = tmp_path / "sample.wav"
    input_path.write_bytes(b"input")

    monkeypatch.setattr(preprocessor, "TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(preprocessor, "get_audio_info", lambda _: {})
    monkeypatch.setattr(preprocessor.os.path, "getsize", lambda _: 1024 * 1024)

    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"normalized")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(preprocessor.subprocess, "run", fake_run)
    return input_path, calls


def test_aggressive_tier_includes_dynaudnorm(monkeypatch, tmp_path):
    input_path, calls = _setup_normalize_mocks(monkeypatch, tmp_path)

    preprocessor.normalize_audio(str(input_path), config=preprocessor.AGGRESSIVE_CONFIG)

    ffmpeg_cmd = calls[0]
    filter_chain = ffmpeg_cmd[ffmpeg_cmd.index("-af") + 1]
    assert "dynaudnorm=p=0.9:m=100" in filter_chain


def test_default_tier_does_not_include_dynaudnorm(monkeypatch, tmp_path):
    input_path, calls = _setup_normalize_mocks(monkeypatch, tmp_path)

    preprocessor.normalize_audio(str(input_path), config=preprocessor.DEFAULT_CONFIG)

    ffmpeg_cmd = calls[0]
    filter_chain = ffmpeg_cmd[ffmpeg_cmd.index("-af") + 1]
    assert "dynaudnorm" not in filter_chain


def test_hash_config_is_stable_for_same_config():
    config = {"a": 1, "b": {"c": True}}

    assert preprocessor._hash_config(config) == preprocessor._hash_config({"b": {"c": True}, "a": 1})


def test_cache_path_changes_when_config_changes(tmp_path, monkeypatch):
    input_path = tmp_path / "sample.wav"
    input_path.write_bytes(b"input")
    monkeypatch.setattr(preprocessor, "TEMP_DIR", str(tmp_path))

    default_path = preprocessor._cache_path(input_path, "Default (fair audio)", preprocessor.DEFAULT_CONFIG)
    aggressive_path = preprocessor._cache_path(input_path, "Aggressive (noisy/poor audio)", preprocessor.AGGRESSIVE_CONFIG)

    assert default_path != aggressive_path


def test_cache_path_changes_when_effective_setting_changes(tmp_path, monkeypatch):
    input_path = tmp_path / "sample.wav"
    input_path.write_bytes(b"input")
    monkeypatch.setattr(preprocessor, "TEMP_DIR", str(tmp_path))

    modified_config = dict(preprocessor.DEFAULT_CONFIG)
    modified_config["highpass_freq"] = 120

    original = preprocessor._cache_path(input_path, "Default (fair audio)", preprocessor.DEFAULT_CONFIG)
    changed = preprocessor._cache_path(input_path, "Default (fair audio)", modified_config)

    assert original != changed


def test_trim_long_silence_logs_full_ffmpeg_error_and_returns_input(monkeypatch, tmp_path):
    input_path = tmp_path / "sample.wav"
    input_path.write_bytes(b"input")

    monkeypatch.setattr(preprocessor, "get_audio_duration", lambda _: 120.0)

    logged = {}

    def fake_error(message, detail):
        logged["message"] = message
        logged["detail"] = detail

    monkeypatch.setattr(preprocessor.logger, "error", fake_error)
    monkeypatch.setattr(
        preprocessor.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ffmpeg full error detail\nline two of stderr",
        ),
    )

    result = preprocessor.trim_long_silence(str(input_path))

    assert result == str(input_path)
    assert logged["message"] == "[Preprocessor] Silence trimming failed: %s"
    assert logged["detail"] == "ffmpeg full error detail\nline two of stderr"
