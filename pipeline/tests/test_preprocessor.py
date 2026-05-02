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


def test_aggressive_tier_uses_speech_safe_filter_chain(monkeypatch, tmp_path):
    input_path, calls = _setup_normalize_mocks(monkeypatch, tmp_path)

    preprocessor.normalize_audio(str(input_path), config=preprocessor.AGGRESSIVE_CONFIG)

    ffmpeg_cmd = calls[0]
    filter_chain = ffmpeg_cmd[ffmpeg_cmd.index("-af") + 1]
    assert "pan=mono|c0=0.5c0+0.5c1" in filter_chain
    assert "highpass=f=80" in filter_chain
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in filter_chain
    assert "dynaudnorm" not in filter_chain
    assert "afftdn" not in filter_chain


def test_default_tier_does_not_include_dynaudnorm(monkeypatch, tmp_path):
    input_path, calls = _setup_normalize_mocks(monkeypatch, tmp_path)

    preprocessor.normalize_audio(str(input_path), config=preprocessor.DEFAULT_CONFIG)

    ffmpeg_cmd = calls[0]
    filter_chain = ffmpeg_cmd[ffmpeg_cmd.index("-af") + 1]
    assert "dynaudnorm" not in filter_chain


def test_hash_config_is_stable_for_same_config():
    config = {"a": 1, "b": {"c": True}}

    assert preprocessor._hash_config(config) == preprocessor._hash_config(
        {"b": {"c": True}, "a": 1}
    )


def test_cache_path_changes_when_config_changes(tmp_path, monkeypatch):
    input_path = tmp_path / "sample.wav"
    input_path.write_bytes(b"input")
    monkeypatch.setattr(preprocessor, "TEMP_DIR", str(tmp_path))

    default_path = preprocessor._cache_path(
        input_path, "Default (fair audio)", preprocessor.DEFAULT_CONFIG
    )
    aggressive_path = preprocessor._cache_path(
        input_path, "Aggressive (noisy/poor audio)", preprocessor.AGGRESSIVE_CONFIG
    )

    assert default_path != aggressive_path


def test_cache_path_changes_when_effective_setting_changes(tmp_path, monkeypatch):
    input_path = tmp_path / "sample.wav"
    input_path.write_bytes(b"input")
    monkeypatch.setattr(preprocessor, "TEMP_DIR", str(tmp_path))

    modified_config = dict(preprocessor.DEFAULT_CONFIG)
    modified_config["highpass_freq"] = 120

    original = preprocessor._cache_path(
        input_path, "Default (fair audio)", preprocessor.DEFAULT_CONFIG
    )
    changed = preprocessor._cache_path(
        input_path, "Default (fair audio)", modified_config
    )

    assert original != changed


def test_trim_long_silence_logs_full_ffmpeg_error_and_returns_input(
    monkeypatch, tmp_path
):
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


# ── Description-string honesty (regression test for the "pyannote lie") ─────
# Before 2026-04-25 the ENHANCED and RESCUE configs claimed "pyannote
# diarization" in their description strings, but the actual filter chain
# in _build_filter_chain() doesn't run pyannote — Deepgram does the
# diarization. The lie sent debugging down a half-day rabbit hole. These
# tests pin the descriptions to what the code actually does, so a future
# regression can't reintroduce the same false claim.


def test_no_quality_config_description_mentions_pyannote():
    # If the actual _build_filter_chain() ever invokes pyannote, this
    # test should be flipped to require the mention. Until then,
    # mentioning pyannote in a description is a lie.
    for tier_name, config in preprocessor.QUALITY_CONFIGS.items():
        if config is None:
            continue
        description = (config.get("description") or "").lower()
        assert "pyannote" not in description, (
            f"{tier_name!r} description claims pyannote runs, but the "
            f"filter chain produced by _build_filter_chain() does not. "
            f"Either wire pyannote up (see CLAUDE.md §17) or fix the "
            f"description: {description!r}"
        )


def test_enhanced_description_mentions_deepgram_diarization():
    description = preprocessor.ENHANCED_CONFIG["description"]
    assert "Deepgram" in description, (
        f"ENHANCED tier description should name the active diarizer, "
        f"got {description!r}"
    )


def test_rescue_description_mentions_deepgram_diarization():
    description = preprocessor.RESCUE_CONFIG["description"]
    assert "Deepgram" in description, (
        f"RESCUE tier description should name the active diarizer, "
        f"got {description!r}"
    )


def test_filter_chain_components_match_description_for_enhanced(monkeypatch, tmp_path):
    # The description says "highpass + loudnorm + Deepgram diarization".
    # The Deepgram step is downstream of FFmpeg, so what _build_filter_chain
    # produces should be exactly "pan=mono + highpass + loudnorm" (no
    # afftdn, no pyannote, no neural denoiser inline). This catches the
    # case where someone adds an FFmpeg step that the description doesn't
    # mention.
    input_path, calls = _setup_normalize_mocks(monkeypatch, tmp_path)
    preprocessor.normalize_audio(str(input_path), config=preprocessor.ENHANCED_CONFIG)

    ffmpeg_cmd = calls[0]
    filter_chain = ffmpeg_cmd[ffmpeg_cmd.index("-af") + 1]

    # Components the description claims:
    assert "pan=mono" in filter_chain  # always (mono mixdown)
    assert "highpass=f=80" in filter_chain  # description: "highpass"
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in filter_chain  # description: "loudnorm"

    # Components the description does NOT claim — must NOT appear:
    assert "afftdn" not in filter_chain
    assert "denoise" not in filter_chain
    assert "pyannote" not in filter_chain  # pyannote can't be in an FFmpeg
    # filter anyway, but pin it
