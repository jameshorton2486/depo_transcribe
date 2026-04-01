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

QUALITY TIERS:
  Clean    — highpass + loudnorm only (good studio or quiet room recordings)
  Default  — highpass + afftdn -25dB + loudnorm (Zoom/phone calls, fair audio)
  Aggressive — highpass + afftdn -20dB + loudnorm (noisy environments)

AUTO-DETECT DECISION LOGIC (legal transcript optimized):
  - VERY low bitrate (<32 kbps) OR extremely compressed audio → AGGRESSIVE
  - Moderate compression OR unknown dynamic range → DEFAULT (safe fallback)
  - High dynamic range (>18 dB) + good bitrate → CLEAN

  IMPORTANT: If dynamic_range is unavailable we do NOT assume clean audio.
  We fall back to DEFAULT to preserve speech accuracy and avoid
  over-aggressive denoising decisions.

CACHING:
  Output filenames include the tier name so that changing quality settings
  always produces a fresh file rather than reusing a stale cached WAV.
  Example: normalized_depo_audio_default.wav
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
    "Auto-detect (recommended)": None,
    "Clean (good/excellent audio)": CLEAN_CONFIG,
    "Default (fair audio)": DEFAULT_CONFIG,
    "Aggressive (noisy/poor audio)": AGGRESSIVE_CONFIG,
}

AUTO_DETECT_KEY = "Auto-detect (recommended)"

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".mp4", ".mov", ".avi",
    ".mkv", ".flac", ".ogg", ".aac", ".wma", ".webm",
}


def _tier_slug(tier_name: str) -> str:
    """Convert a tier description to a safe filename component."""
    return (
        tier_name.lower()
        .split(":")[0]
        .split("(")[0]
        .strip()
        .replace(" ", "_")
    )


def auto_detect_quality(input_path: str) -> tuple[dict, str]:
    """
    Analyse the audio file and return the most appropriate quality config.

    Uses FFprobe bitrate + FFmpeg volumedetect to measure dynamic range.
    Biased toward DEFAULT to protect legal transcript verbatim accuracy —
    aggressive denoising can damage names and consonants.

    Returns:
        (config_dict, tier_name_string)
    """
    info = get_audio_info(input_path)
    format_info = info.get("format", {})

    try:
        bitrate_bps = int(format_info.get("bit_rate", 0) or 0)
        bitrate_kbps = bitrate_bps // 1000
    except (ValueError, TypeError):
        bitrate_kbps = 0

    very_poor_bitrate = bitrate_kbps > 0 and bitrate_kbps < 32
    poor_bitrate = bitrate_kbps > 0 and bitrate_kbps < 64

    logger.info("[Preprocessor] Auto-detect: bitrate=%d kbps", bitrate_kbps)

    dynamic_range = None
    try:
        vol_cmd = [
            "ffmpeg", "-i", str(input_path),
            "-af", "volumedetect",
            "-f", "null", "-",
        ]
        vol_result = subprocess.run(
            vol_cmd, capture_output=True, text=True, timeout=60
        )
        stderr = vol_result.stderr or ""

        mean_vol = None
        max_vol = None
        for line in stderr.splitlines():
            if "mean_volume" in line:
                try:
                    mean_vol = float(line.split(":")[1].strip().split()[0])
                except (IndexError, ValueError):
                    pass
            if "max_volume" in line:
                try:
                    max_vol = float(line.split(":")[1].strip().split()[0])
                except (IndexError, ValueError):
                    pass

        if mean_vol is not None and max_vol is not None:
            dynamic_range = abs(max_vol - mean_vol)
            logger.info(
                "[Preprocessor] Auto-detect: mean_vol=%.1f max_vol=%.1f dynamic_range=%.1f dB",
                mean_vol, max_vol, dynamic_range,
            )

    except Exception as exc:
        logger.warning("[Preprocessor] volumedetect failed: %s", exc)

    if very_poor_bitrate:
        tier_name = "Aggressive (noisy/poor audio)"
        config = AGGRESSIVE_CONFIG
    elif dynamic_range is not None and dynamic_range < 6:
        tier_name = "Aggressive (noisy/poor audio)"
        config = AGGRESSIVE_CONFIG
    elif poor_bitrate or dynamic_range is None or dynamic_range < 18:
        tier_name = "Default (fair audio)"
        config = DEFAULT_CONFIG
    else:
        tier_name = "Clean (good/excellent audio)"
        config = CLEAN_CONFIG

    logger.info("[Preprocessor] Auto-detect result: %s", tier_name)
    return config, tier_name


def normalize_audio(
    input_path: str,
    config: dict = None,
    auto_detect: bool = False,
    progress_callback=None,
) -> str:
    """
    Normalize an audio or video file to a clean WAV suitable for Deepgram.

    Args:
        input_path:        Path to the source audio/video file.
        config:            Quality config dict (CLEAN_CONFIG etc.).
                           If None and auto_detect is False, DEFAULT_CONFIG is used.
        auto_detect:       If True, run auto_detect_quality() to choose config.
                           Callers should prefer resolving quality before calling
                           this function and passing the result as config=.
        progress_callback: Optional callable for status messages.

    Returns:
        Path to the normalized WAV output file.

    Raises:
        RuntimeError: If FFmpeg is not installed or normalization fails.

    CACHING NOTE:
        The output filename includes a slug derived from the tier name so that
        switching quality settings always triggers a fresh normalization rather
        than reusing a stale cached WAV from a previous tier.
    """
    tier_name = "unknown"

    if auto_detect:
        config, tier_name = auto_detect_quality(str(input_path))
        logger.info("[Preprocessor] Auto-detected tier: %s", tier_name)
    elif config is None:
        config = DEFAULT_CONFIG
        tier_name = "Default (fair audio)"
        logger.info("[Preprocessor] No config supplied — using DEFAULT as safe fallback")
    else:
        for name, cfg in QUALITY_CONFIGS.items():
            if cfg is not None and cfg.get("description") == config.get("description"):
                tier_name = name
                break
        if tier_name == "unknown":
            tier_name = config.get("description", "custom")

    logger.info("[Preprocessor] Normalizing: %s  config=%s", Path(input_path).name, config["description"])
    if progress_callback:
        progress_callback(f"Normalizing audio: {config['description']}")

    os.makedirs(TEMP_DIR, exist_ok=True)

    input_path = Path(input_path)

    slug = _tier_slug(tier_name)
    output_filename = f"normalized_{input_path.stem}_{slug}.wav"
    output_path = os.path.join(TEMP_DIR, output_filename)

    if (
        os.path.exists(output_path)
        and os.path.getmtime(output_path) >= os.path.getmtime(str(input_path))
    ):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(
            "[Preprocessor] Cache hit — skipping normalization: %s (%.1f MB)",
            output_path, size_mb,
        )
        if progress_callback:
            progress_callback(f"Using cached normalized audio ({size_mb:.1f} MB)  [{tier_name}]")
        return output_path

    filters = [f"highpass=f={config['highpass_freq']}"]

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

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("[Preprocessor] FFmpeg failed: %s", result.stderr[:300])
        raise RuntimeError(f"FFmpeg normalization failed:\n{result.stderr}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(
        "[Preprocessor] Output: %s  tier=%s  size_mb=%.1f",
        output_path, tier_name, size_mb,
    )
    if progress_callback:
        progress_callback(f"Audio normalized: {size_mb:.1f} MB  [{tier_name}]")

    audio_info = get_audio_info(output_path)
    fmt = audio_info.get("format", {})
    streams = audio_info.get("streams", [])
    astream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    logger.info(
        "[Preprocessor] ffprobe post-norm: duration=%s sr=%s ch=%s bitrate=%s codec=%s",
        fmt.get("duration", "?"),
        astream.get("sample_rate", "?"),
        astream.get("channels", "?"),
        fmt.get("bit_rate", "?"),
        astream.get("codec_name", "?"),
    )

    return output_path


def get_audio_info(file_path: str) -> dict:
    """Return FFprobe metadata for an audio file as a dict."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries", "stream=codec_name,sample_rate,channels,codec_type",
        "-of", "json",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            "[Preprocessor] FFprobe failed for %s: %s",
            file_path, result.stderr.strip()[:300],
        )
        return {}
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        logger.warning("[Preprocessor] FFprobe returned invalid JSON for %s", file_path)
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
            "error": (
                f"Unsupported format: {ext}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        }

    duration = get_audio_duration(file_path)
    if duration <= 0:
        return {
            "valid": False, "duration": 0, "format": ext,
            "error": (
                "Could not determine audio duration. "
                "File may be corrupt or FFmpeg is not installed."
            ),
        }

    return {"valid": True, "duration": duration, "format": ext.lstrip("."), "error": None}


def check_ffmpeg() -> bool:
    """Return True if FFmpeg is available on the system PATH."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False
