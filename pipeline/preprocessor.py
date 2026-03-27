"""
pipeline/preprocessor.py

Normalizes audio/video files using FFmpeg before Deepgram transcription.

WHAT THIS DOES AND WHY:
  1. Converts any audio/video format (MP4, MOV, M4A, MP3, FLAC, etc.) to WAV.
  2. Resamples to 24 kHz — preserves the consonant frequency band (4-8 kHz)
     critical for legal speech accuracy (names, case numbers, plural endings).
  3. Converts to mono — Deepgram diarization works on mono.
  4. Applies loudnorm — EBU R128 loudness normalization.
  5. Applies highpass filter at 80 Hz — removes desk rumble, HVAC hum.
  6. Does NOT apply arnndn neural denoising on clean recordings — it strips
     phonetic cues and INCREASES word error rate on clean audio.
"""

import json
import os
import subprocess
from pathlib import Path

from app_logging import get_logger
from config import TARGET_SAMPLE_RATE, TEMP_DIR

logger = get_logger(__name__)

CLEAN_CONFIG = {
    "highpass_freq": 80,
    "loudnorm": True,
    "afftdn": False,
    "description": "Clean audio: highpass + loudnorm only",
}

DEFAULT_CONFIG = {
    "highpass_freq": 80,
    "loudnorm": True,
    "afftdn": True,
    "afftdn_nf": -25,
    "description": "Fair audio: highpass + afftdn spectral denoising + loudnorm",
}

AGGRESSIVE_CONFIG = {
    "highpass_freq": 100,
    "loudnorm": True,
    "afftdn": True,
    "afftdn_nf": -20,
    "description": "Poor audio: aggressive denoising + loudnorm",
}

QUALITY_CONFIGS = {
    "Clean (good/excellent audio)": CLEAN_CONFIG,
    "Default (fair audio)": DEFAULT_CONFIG,
    "Aggressive (noisy/poor audio)": AGGRESSIVE_CONFIG,
}

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".mp4", ".mov", ".avi",
    ".mkv", ".flac", ".ogg", ".aac", ".wma", ".webm",
}


def normalize_audio(input_path: str, config: dict = None, progress_callback=None) -> str:
    """
    Normalize an audio or video file to a clean WAV suitable for Deepgram.

    Returns:
        Path to the normalized WAV output file.

    Raises:
        RuntimeError: If FFmpeg is not installed or normalization fails.
    """
    if config is None:
        config = CLEAN_CONFIG
    print(f"[AUDIO] Normalizing: {Path(input_path).name}")
    print(f"[AUDIO] Config: {config['description']}")

    os.makedirs(TEMP_DIR, exist_ok=True)

    input_path = Path(input_path)
    output_filename = f"normalized_{input_path.stem}.wav"
    output_path = os.path.join(TEMP_DIR, output_filename)

    filters = []
    filters.append(f"highpass=f={config['highpass_freq']}")

    if config.get("afftdn"):
        nf = config.get("afftdn_nf", -25)
        filters.append(f"afftdn=nf={nf}")

    if config.get("loudnorm"):
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    filter_chain = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", "1",
        "-af", filter_chain,
        output_path,
    ]

    if progress_callback:
        progress_callback(f"Normalizing audio: {config['description']}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[AUDIO] ERROR: {result.stderr[:200]}")
        raise RuntimeError(f"FFmpeg normalization failed:\n{result.stderr}")

    if progress_callback:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        progress_callback(f"Audio normalized: {size_mb:.1f} MB")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[AUDIO] Output: {output_path} ({size_mb:.1f} MB)")
    logger.info("Normalized audio output path=%s size_mb=%.1f", output_path, size_mb)

    audio_info = get_audio_info(output_path)
    format_info = audio_info.get("format", {})
    streams = audio_info.get("streams", [])
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    duration = format_info.get("duration", "unknown")
    sample_rate = audio_stream.get("sample_rate", "unknown")
    channels = audio_stream.get("channels", "unknown")
    logger.info(
        "Normalized audio ffprobe duration_seconds=%s sample_rate=%s channels=%s bit_rate=%s codec=%s",
        duration,
        sample_rate,
        channels,
        format_info.get("bit_rate", "unknown"),
        audio_stream.get("codec_name", "unknown"),
    )

    return output_path


def get_audio_info(file_path: str) -> dict:
    """Return FFprobe metadata for an audio file as a dict."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,codec_type",
        "-of",
        "json",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            "FFprobe metadata lookup failed for path=%s stderr=%s",
            file_path,
            result.stderr.strip()[:300],
        )
        return {}

    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        logger.warning("FFprobe returned invalid JSON for path=%s", file_path)
        return {}


def get_audio_duration(file_path: str) -> float:
    """Get the duration of an audio file in seconds using FFprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def validate_audio_file(file_path: str) -> dict:
    """
    Validate that the input file is a supported audio/video format.

    Returns:
        { "valid": bool, "duration": float, "format": str, "error": str|None }
    """
    path = Path(file_path)

    if not path.exists():
        return {"valid": False, "duration": 0, "format": "", "error": "File not found"}

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {
            "valid": False, "duration": 0, "format": ext,
            "error": f"Unsupported format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        }

    duration = get_audio_duration(file_path)
    if duration <= 0:
        return {
            "valid": False, "duration": 0, "format": ext,
            "error": "Could not determine audio duration. File may be corrupt or FFmpeg is not installed.",
        }

    return {"valid": True, "duration": duration, "format": ext.lstrip("."), "error": None}


def check_ffmpeg() -> bool:
    """Return True if FFmpeg is available on the system PATH."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False
