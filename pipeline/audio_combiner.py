"""
pipeline/audio_combiner.py

Combine 1-N audio (or video-with-audio) files into a single output
before transcription. Supports the multi-session deposition workflow
where one deposition is recorded as several files (recorder file-size
limits, breaks, technical interruptions).

Two paths:
- All inputs share codec + sample_rate + channels → concat demuxer with
  -c copy (lossless, no re-encode, fast).
- Inputs differ → concat filter, re-encode to PCM WAV at the project's
  TARGET_SAMPLE_RATE (24kHz mono, 16-bit) so the downstream preprocessor
  + chunker get a known-shape file.

The 24kHz choice mirrors `config.TARGET_SAMPLE_RATE` because the project
relies on 4-8kHz sibilant preservation for legal name disambiguation
(see CLAUDE.md Section 7). Do NOT lower this to 16kHz "for Deepgram" —
that's a documented architectural decision.

Single file passes through via shutil.copy() (no symlinks: Windows
requires elevation, and a copy is cheap relative to typical deposition
audio sizes).

Layer note: this module belongs in `pipeline/` because it is audio
preparation, not text correction. It MUST NOT make Deepgram/HTTP calls,
classify text, or know about UFM rules.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app_logging import get_logger
from config import TARGET_SAMPLE_RATE

logger = get_logger(__name__)


@dataclass
class CombineResult:
    success: bool
    output_path: Path | None
    duration_seconds: float
    lossless: bool
    method: str  # "concat_demuxer" | "concat_filter" | "passthrough"
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def probe_audio_format(file_path: Path) -> dict:
    """
    Probe codec/sample_rate/channels/bit_rate/duration/format_name via
    ffprobe. Raises FileNotFoundError if the file doesn't exist; raises
    RuntimeError if ffprobe fails or returns malformed JSON.
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe not found on PATH. Install FFmpeg.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffprobe timed out probing {file_path}") from exc

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {file_path}: {result.stderr.strip()}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"ffprobe returned malformed JSON for {file_path}: {exc}"
        ) from exc

    fmt = payload.get("format", {}) or {}
    streams = payload.get("streams", []) or []
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise RuntimeError(f"No audio stream in {file_path}")
    audio = audio_streams[0]

    def _to_int(val, default=0):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def _to_float(val, default=0.0):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    return {
        "codec_name": str(audio.get("codec_name") or ""),
        "sample_rate": _to_int(audio.get("sample_rate")),
        "channels": _to_int(audio.get("channels")),
        # bit_rate may live on stream or format — prefer stream, fall back.
        "bit_rate": _to_int(audio.get("bit_rate") or fmt.get("bit_rate")),
        # Duration may be in stream or format. Format is more reliable for
        # multi-stream containers; stream wins for plain audio.
        "duration": _to_float(audio.get("duration") or fmt.get("duration")),
        "format_name": str(fmt.get("format_name") or ""),
    }


def formats_match(formats: list[dict]) -> bool:
    """
    True iff all formats share codec_name, sample_rate, and channels.
    bit_rate intentionally not compared — small bitrate drift between
    files from the same recorder is common and doesn't break -c copy.
    """
    if len(formats) < 2:
        return True
    first = formats[0]
    keys = ("codec_name", "sample_rate", "channels")
    for other in formats[1:]:
        for key in keys:
            if first.get(key) != other.get(key):
                return False
    return True


def _escape_concat_path(path: Path) -> str:
    """
    Escape a path for ffmpeg's concat demuxer filelist format. The
    demuxer reads `file 'PATH'` lines and treats `'` as the string
    delimiter, so embedded apostrophes must be escaped as `'\\''` (close
    quote, escaped quote, reopen quote). Backslashes are left alone —
    Windows paths work fine inside single-quoted filelist entries.
    """
    return str(path).replace("'", r"'\''")


def _summed_duration(formats: list[dict]) -> float:
    return sum(float(f.get("duration", 0.0) or 0.0) for f in formats)


def combine_audio_files(
    input_paths: list[Path],
    output_path: Path,
) -> CombineResult:
    """
    Combine 1-N audio files into output_path.

    Behavior:
    - 0 files: ValueError
    - 1 file: passthrough — shutil.copy to output_path; method="passthrough"
    - 2+ files, formats match: concat demuxer with -c copy (lossless)
    - 2+ files, formats differ: concat filter, re-encode to WAV at
      TARGET_SAMPLE_RATE mono PCM. Output extension forced to .wav with
      a warning if the requested output_path didn't already use .wav.

    Output directory is created if missing.
    """
    if not input_paths:
        raise ValueError("input_paths is empty — at least one file required")

    inputs = [Path(p) for p in input_paths]
    missing = [str(p) for p in inputs if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"Input file(s) not found: {', '.join(missing)}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "[AudioCombiner] Combining %d audio file(s) into %s",
        len(inputs),
        output_path,
    )

    # ── Single-file passthrough ──────────────────────────────────────────
    if len(inputs) == 1:
        src = inputs[0]
        try:
            shutil.copy(src, output_path)
        except Exception as exc:
            logger.error("[AudioCombiner] Passthrough copy failed: %s", exc)
            return CombineResult(
                success=False,
                output_path=None,
                duration_seconds=0.0,
                lossless=True,
                method="passthrough",
                error=f"Copy failed: {exc}",
            )
        try:
            duration = probe_audio_format(output_path).get("duration", 0.0)
        except Exception:
            duration = 0.0
        logger.info("[AudioCombiner] Passthrough complete (lossless=True)")
        return CombineResult(
            success=True,
            output_path=output_path,
            duration_seconds=duration,
            lossless=True,
            method="passthrough",
        )

    # ── Probe all inputs to decide demuxer vs filter ─────────────────────
    try:
        formats = [probe_audio_format(p) for p in inputs]
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("[AudioCombiner] Probe failed: %s", exc)
        return CombineResult(
            success=False,
            output_path=None,
            duration_seconds=0.0,
            lossless=False,
            method="",
            error=f"Probe failed: {exc}",
        )

    total_duration = _summed_duration(formats)
    timeout_seconds = max(300, int(total_duration * 2))

    if formats_match(formats):
        return _combine_demuxer(inputs, output_path, total_duration, timeout_seconds)
    return _combine_filter(inputs, output_path, total_duration, timeout_seconds)


def _combine_demuxer(
    inputs: list[Path],
    output_path: Path,
    total_duration: float,
    timeout_seconds: int,
) -> CombineResult:
    """Lossless concat via ffmpeg's concat demuxer (-c copy)."""
    filelist = output_path.parent / f".{output_path.stem}_filelist.txt"
    try:
        # UTF-8 so non-ASCII filenames (accented chars, etc.) survive.
        with open(filelist, "w", encoding="utf-8") as fh:
            for path in inputs:
                fh.write(f"file '{_escape_concat_path(path.resolve())}'\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(filelist),
            "-c",
            "copy",
            str(output_path),
        ]
        logger.info("[AudioCombiner] Using concat_demuxer (lossless=True)")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return CombineResult(
                success=False,
                output_path=None,
                duration_seconds=total_duration,
                lossless=True,
                method="concat_demuxer",
                error=(f"ffmpeg concat demuxer timed out after {timeout_seconds}s"),
            )

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            logger.error("[AudioCombiner] concat_demuxer failed: %s", stderr)
            return CombineResult(
                success=False,
                output_path=None,
                duration_seconds=total_duration,
                lossless=True,
                method="concat_demuxer",
                error=f"ffmpeg failed: {stderr[:500]}",
            )

        try:
            actual_duration = probe_audio_format(output_path).get(
                "duration", total_duration
            )
        except Exception:
            actual_duration = total_duration
        logger.info(
            "[AudioCombiner] concat_demuxer complete: duration=%.2fs",
            actual_duration,
        )
        return CombineResult(
            success=True,
            output_path=output_path,
            duration_seconds=actual_duration,
            lossless=True,
            method="concat_demuxer",
        )
    finally:
        try:
            if filelist.exists():
                filelist.unlink()
        except Exception as cleanup_exc:
            logger.warning(
                "[AudioCombiner] Could not delete temp filelist %s: %s",
                filelist,
                cleanup_exc,
            )


def _combine_filter(
    inputs: list[Path],
    output_path: Path,
    total_duration: float,
    timeout_seconds: int,
) -> CombineResult:
    """Re-encode concat via ffmpeg's concat filter — for mismatched formats."""
    warnings: list[str] = []

    # Force .wav extension since we're producing PCM WAV. Track the
    # rename so the caller knows the path may have moved.
    final_output = output_path
    if final_output.suffix.lower() != ".wav":
        new_path = final_output.with_suffix(".wav")
        warnings.append(
            f"Output extension changed from {final_output.suffix} to .wav "
            f"because re-encoding produces PCM WAV."
        )
        logger.info(
            "[AudioCombiner] Forcing .wav extension for re-encode path: %s",
            new_path,
        )
        final_output = new_path

    cmd: list[str] = ["ffmpeg", "-y"]
    for path in inputs:
        cmd.extend(["-i", str(path)])
    n = len(inputs)
    filter_complex = (
        "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
    )
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            str(final_output),
        ]
    )

    logger.info(
        "[AudioCombiner] Using concat_filter (lossless=False, target_sr=%d)",
        TARGET_SAMPLE_RATE,
    )
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return CombineResult(
            success=False,
            output_path=None,
            duration_seconds=total_duration,
            lossless=False,
            method="concat_filter",
            warnings=warnings,
            error=f"ffmpeg concat filter timed out after {timeout_seconds}s",
        )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.error("[AudioCombiner] concat_filter failed: %s", stderr)
        return CombineResult(
            success=False,
            output_path=None,
            duration_seconds=total_duration,
            lossless=False,
            method="concat_filter",
            warnings=warnings,
            error=f"ffmpeg failed: {stderr[:500]}",
        )

    try:
        actual_duration = probe_audio_format(final_output).get(
            "duration", total_duration
        )
    except Exception:
        actual_duration = total_duration
    logger.info(
        "[AudioCombiner] concat_filter complete: duration=%.2fs",
        actual_duration,
    )
    return CombineResult(
        success=True,
        output_path=final_output,
        duration_seconds=actual_duration,
        lossless=False,
        method="concat_filter",
        warnings=warnings,
    )
