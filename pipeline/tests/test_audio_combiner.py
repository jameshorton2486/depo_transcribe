"""
pipeline/tests/test_audio_combiner.py

Real ffmpeg-based tests for the audio combiner. Fixtures are generated
on the fly via ffmpeg's lavfi sine source — never committed as binaries.

Skip cleanly when ffmpeg isn't on PATH so CI without ffmpeg doesn't fail.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.audio_combiner import (
    CombineResult,
    _escape_concat_path,
    combine_audio_files,
    formats_match,
    probe_audio_format,
)
from ui._components import AUDIO_VIDEO_EXTENSIONS

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _make_audio(
    path: Path,
    duration_s: float = 1.0,
    sample_rate: int = 44100,
    channels: int = 2,
    codec: str = "libmp3lame",
    extra_args: list[str] | None = None,
) -> Path:
    """Synthesize a sine-wave file via ffmpeg's lavfi source."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    layout = "stereo" if channels == 2 else "mono"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration_s}:sample_rate={sample_rate}",
        "-ac",
        str(channels),
        "-channel_layout",
        layout,
        "-c:a",
        codec,
    ]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(str(path))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg fixture generation failed for {path}: {result.stderr}"
        )
    return path


def _make_silent_video_with_audio(path: Path, duration_s: float = 1.0) -> Path:
    """Synthesize an MP4 with both video (color bars) and audio tracks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=64x48:d={duration_s}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration_s}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg video fixture generation failed: {result.stderr}")
    return path


# ── Pure helper tests (no ffmpeg required) ───────────────────────────────────


def test_formats_match_single_format():
    assert formats_match([{"codec_name": "mp3", "sample_rate": 44100, "channels": 2}])


def test_formats_match_identical():
    fmt = {"codec_name": "mp3", "sample_rate": 44100, "channels": 2}
    assert formats_match([fmt, fmt, fmt])


def test_formats_match_different_codec():
    a = {"codec_name": "mp3", "sample_rate": 44100, "channels": 2}
    b = {"codec_name": "aac", "sample_rate": 44100, "channels": 2}
    assert not formats_match([a, b])


def test_formats_match_different_sample_rate():
    a = {"codec_name": "mp3", "sample_rate": 44100, "channels": 2}
    b = {"codec_name": "mp3", "sample_rate": 22050, "channels": 2}
    assert not formats_match([a, b])


def test_formats_match_ignores_bit_rate_drift():
    a = {"codec_name": "mp3", "sample_rate": 44100, "channels": 2, "bit_rate": 128000}
    b = {"codec_name": "mp3", "sample_rate": 44100, "channels": 2, "bit_rate": 192000}
    assert formats_match([a, b])


def test_escape_concat_path_no_apostrophe():
    p = Path("/tmp/clean_path/file.mp3")
    assert _escape_concat_path(p) == str(p)


def test_escape_concat_path_with_apostrophe():
    p = Path("/tmp/O'Brien/session.mp3")
    escaped = _escape_concat_path(p)
    # Embedded ' becomes '\'' so the demuxer reads it back as a literal '
    assert "O'\\''Brien" in escaped


def test_empty_list_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        combine_audio_files([], tmp_path / "out.mp3")


def test_audio_video_extensions_constant_unchanged():
    """Regression guard for the move from tab_transcribe.py to _components.py.
    If the supported extensions ever change, that's a deliberate edit and
    this test should be updated alongside it."""
    assert AUDIO_VIDEO_EXTENSIONS == (
        ("Audio / Video files", "*.mp3 *.mp4 *.wav *.m4a *.mov *.avi *.mkv *.flac"),
        ("All files", "*.*"),
    )


# ── ffmpeg-backed tests ──────────────────────────────────────────────────────


@requires_ffmpeg
def test_passthrough_single_file(tmp_path):
    src = _make_audio(tmp_path / "single.mp3", duration_s=1.0)
    out = tmp_path / "result.mp3"
    result = combine_audio_files([src], out)

    assert result.success is True
    assert result.method == "passthrough"
    assert result.lossless is True
    assert result.output_path == out
    assert out.is_file()
    assert result.duration_seconds == pytest.approx(1.0, abs=0.1)


@requires_ffmpeg
def test_concat_demuxer_same_format_mp3(tmp_path):
    a = _make_audio(tmp_path / "a.mp3", duration_s=1.0)
    b = _make_audio(tmp_path / "b.mp3", duration_s=1.0)
    out = tmp_path / "combined.mp3"

    result = combine_audio_files([a, b], out)

    assert result.success is True
    assert result.method == "concat_demuxer"
    assert result.lossless is True
    assert out.is_file()
    assert result.duration_seconds == pytest.approx(2.0, abs=0.2)


@requires_ffmpeg
def test_concat_demuxer_three_files(tmp_path):
    paths = [_make_audio(tmp_path / f"part{i}.mp3", duration_s=0.7) for i in range(3)]
    out = tmp_path / "combined.mp3"

    result = combine_audio_files(paths, out)

    assert result.success is True
    assert result.method == "concat_demuxer"
    assert result.lossless is True
    assert result.duration_seconds == pytest.approx(2.1, abs=0.2)


@requires_ffmpeg
def test_concat_filter_different_codecs(tmp_path):
    mp3 = _make_audio(tmp_path / "a.mp3", duration_s=1.0, codec="libmp3lame")
    m4a = _make_audio(
        tmp_path / "b.m4a",
        duration_s=1.0,
        codec="aac",
        extra_args=["-f", "mp4"],
    )
    out = tmp_path / "combined.wav"

    result = combine_audio_files([mp3, m4a], out)

    assert result.success is True
    assert result.method == "concat_filter"
    assert result.lossless is False
    assert result.output_path is not None
    assert result.output_path.suffix == ".wav"

    # Output must be valid PCM WAV at TARGET_SAMPLE_RATE mono
    fmt = probe_audio_format(result.output_path)
    assert fmt["codec_name"] == "pcm_s16le"
    from config import TARGET_SAMPLE_RATE

    assert fmt["sample_rate"] == TARGET_SAMPLE_RATE
    assert fmt["channels"] == 1


@requires_ffmpeg
def test_concat_filter_different_sample_rates(tmp_path):
    a = _make_audio(tmp_path / "high.mp3", duration_s=1.0, sample_rate=44100)
    b = _make_audio(tmp_path / "low.mp3", duration_s=1.0, sample_rate=22050)
    out = tmp_path / "combined.wav"

    result = combine_audio_files([a, b], out)

    assert result.success is True
    assert result.method == "concat_filter"
    assert result.lossless is False


@requires_ffmpeg
def test_missing_file_raises(tmp_path):
    real = _make_audio(tmp_path / "real.mp3", duration_s=0.5)
    fake = tmp_path / "does_not_exist.mp3"
    with pytest.raises(FileNotFoundError) as exc:
        combine_audio_files([real, fake], tmp_path / "out.mp3")
    assert str(fake) in str(exc.value)


@requires_ffmpeg
def test_apostrophe_in_filename(tmp_path):
    a = _make_audio(tmp_path / "O'Brien_session1.mp3", duration_s=0.7)
    b = _make_audio(tmp_path / "O'Brien_session2.mp3", duration_s=0.7)
    out = tmp_path / "combined.mp3"

    result = combine_audio_files([a, b], out)

    assert result.success is True, f"failed: {result.error}"
    assert result.method == "concat_demuxer"
    assert result.lossless is True
    assert out.is_file()


@requires_ffmpeg
def test_unicode_filename(tmp_path):
    # Acute-accented e — common in legal names (e.g., Peña, José)
    a = _make_audio(tmp_path / "café_session1.mp3", duration_s=0.7)
    b = _make_audio(tmp_path / "café_session2.mp3", duration_s=0.7)
    out = tmp_path / "combined.mp3"

    result = combine_audio_files([a, b], out)

    assert result.success is True, f"failed: {result.error}"
    assert result.method == "concat_demuxer"


@requires_ffmpeg
def test_warning_on_extension_change(tmp_path):
    """When re-encode path runs but caller asked for a non-WAV extension,
    we override to .wav and surface a warning."""
    mp3 = _make_audio(tmp_path / "a.mp3", duration_s=1.0, codec="libmp3lame")
    m4a = _make_audio(
        tmp_path / "b.m4a",
        duration_s=1.0,
        codec="aac",
        extra_args=["-f", "mp4"],
    )
    requested = tmp_path / "combined.mp3"  # caller asked for .mp3

    result = combine_audio_files([mp3, m4a], requested)

    assert result.success is True
    assert result.output_path is not None
    assert result.output_path.suffix == ".wav"
    assert result.output_path != requested
    assert any("extension changed" in w.lower() for w in result.warnings)


@requires_ffmpeg
def test_wav_inputs_demuxer_duration_matches(tmp_path):
    """Edge case: -c copy with WAV inputs preserves only the first file's
    RIFF header. Verify the resulting duration via ffprobe still matches
    the sum of inputs (within a small tolerance) — if it doesn't, that's
    a real problem we need to know about before shipping."""
    a = _make_audio(
        tmp_path / "a.wav",
        duration_s=1.0,
        sample_rate=24000,
        channels=1,
        codec="pcm_s16le",
    )
    b = _make_audio(
        tmp_path / "b.wav",
        duration_s=1.0,
        sample_rate=24000,
        channels=1,
        codec="pcm_s16le",
    )
    out = tmp_path / "combined.wav"

    result = combine_audio_files([a, b], out)

    assert result.success is True
    assert result.method == "concat_demuxer"
    assert result.duration_seconds == pytest.approx(2.0, abs=0.2), (
        f"WAV concat duration drift: got {result.duration_seconds}s, "
        f"expected ~2.0s. RIFF header may not be reflecting concatenated "
        f"data length."
    )


@requires_ffmpeg
def test_creates_output_dir_if_missing(tmp_path):
    a = _make_audio(tmp_path / "a.mp3", duration_s=0.5)
    b = _make_audio(tmp_path / "b.mp3", duration_s=0.5)
    out = tmp_path / "nested" / "deeper" / "combined.mp3"

    result = combine_audio_files([a, b], out)

    assert result.success is True
    assert out.is_file()


@requires_ffmpeg
def test_filelist_cleaned_up_on_success(tmp_path):
    a = _make_audio(tmp_path / "a.mp3", duration_s=0.5)
    b = _make_audio(tmp_path / "b.mp3", duration_s=0.5)
    out = tmp_path / "combined.mp3"

    combine_audio_files([a, b], out)

    leftovers = list(tmp_path.glob(".*_filelist.txt"))
    assert leftovers == [], f"temp filelist leaked: {leftovers}"


@requires_ffmpeg
def test_probe_audio_format_returns_expected_keys(tmp_path):
    src = _make_audio(tmp_path / "probe_me.mp3", duration_s=1.0)
    fmt = probe_audio_format(src)

    for key in (
        "codec_name",
        "sample_rate",
        "channels",
        "bit_rate",
        "duration",
        "format_name",
    ):
        assert key in fmt, f"missing key {key} in {fmt}"
    assert fmt["sample_rate"] == 44100
    assert fmt["channels"] == 2
    assert fmt["duration"] == pytest.approx(1.0, abs=0.1)


@requires_ffmpeg
def test_probe_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        probe_audio_format(tmp_path / "nonexistent.mp3")
