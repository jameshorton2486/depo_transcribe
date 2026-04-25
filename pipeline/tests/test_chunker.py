from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import chunker


# Use 1.5 × the configured limit so the chunker takes the multi-chunk
# path under whatever CHUNK_DURATION_SECONDS is currently set. Hard-coding
# 700s used to work when the limit was 600; the limit was raised in
# 2026-04 to fix Symptom A (cross-chunk speaker-ID merge corrupting
# witness diarization), which would have left these tests in the
# single-chunk path and they would silently stop exercising chunking.
_DURATION_FORCING_CHUNKS = chunker.CHUNK_DURATION_SECONDS + (chunker.CHUNK_DURATION_SECONDS // 2)


def test_chunk_audio_uses_seek_before_input_and_pcm_wav(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    commands = []

    monkeypatch.setattr(chunker, "TEMP_DIR", str(tmp_path))

    def fake_run(cmd, capture_output=False, text=False):
        commands.append(cmd)
        if cmd[0] == "ffprobe":
            # Probe must report a duration consistent with the chunk we
            # just produced. Use the per-chunk limit minus a sliver so
            # the minimum-size guard in chunker passes.
            return SimpleNamespace(
                returncode=0,
                stdout=f"{chunker.CHUNK_DURATION_SECONDS - 1}.0\n",
                stderr="",
            )
        Path(cmd[-1]).write_bytes(b"x" * 8192)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(chunker.subprocess, "run", fake_run)

    chunks = chunker.chunk_audio(
        str(audio_path), total_duration=float(_DURATION_FORCING_CHUNKS)
    )

    ffmpeg_cmd = commands[0]
    assert ffmpeg_cmd[0] == "ffmpeg"
    assert ffmpeg_cmd[ffmpeg_cmd.index("-ss") - 1] == "-y"
    assert ffmpeg_cmd.index("-ss") < ffmpeg_cmd.index("-i")
    assert ffmpeg_cmd[ffmpeg_cmd.index("-acodec") + 1] == "pcm_s16le"
    assert ffmpeg_cmd[ffmpeg_cmd.index("-ac") + 1] == "1"
    assert ffmpeg_cmd[ffmpeg_cmd.index("-ar") + 1] == str(chunker.TARGET_SAMPLE_RATE)
    assert len(chunks) >= 1


def test_chunk_audio_rejects_near_empty_chunk(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr(chunker, "TEMP_DIR", str(tmp_path))

    def fake_run(cmd, capture_output=False, text=False):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout="0.5\n", stderr="")
        Path(cmd[-1]).write_bytes(b"x" * 1024)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(chunker.subprocess, "run", fake_run)

    try:
        chunker.chunk_audio(
            str(audio_path), total_duration=float(_DURATION_FORCING_CHUNKS)
        )
        assert False, "Expected RuntimeError for invalid tiny chunk"
    except RuntimeError as exc:
        assert "too small to be valid" in str(exc) or "duration probe failed" in str(exc)
