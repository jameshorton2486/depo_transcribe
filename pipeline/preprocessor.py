"""
pipeline/preprocessor.py

Normalizes audio/video files using FFmpeg before Deepgram transcription.
"""

from __future__ import annotations

import hashlib
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
    "afftdn": False,  # OFF — Deepgram handles noise better than afftdn
    "description": "CLEAN: highpass + loudnorm only (good audio)",
}

ENHANCED_CONFIG = {
    "highpass_freq": 80,
    "loudnorm": True,
    "afftdn": False,  # OFF — Deepgram nova-3 outperforms afftdn for diarization
    # Description matches what _build_filter_chain() actually emits — no
    # pyannote runs, only the FFmpeg filters listed here. Deepgram
    # (transcriber.py: diarize=true) is the diarization engine.
    "description": "ENHANCED: highpass + loudnorm + Deepgram diarization",
}

RESCUE_CONFIG = {
    "highpass_freq": 80,
    "loudnorm": True,
    "afftdn": False,  # OFF — noisereduce handles this in job_runner
    "noisereduce": True,
    # Description matches what _build_filter_chain() + job_runner.py emit.
    # noisereduce is a separate pre-Deepgram pass; pyannote is NOT in the
    # active path despite the dead module at pipeline/pyannote_diarizer.py.
    "description": "RESCUE: highpass + loudnorm + noisereduce + Deepgram diarization",
}

QUALITY_CONFIGS = {
    "Auto-detect (recommended)": None,
    "CLEAN (good/excellent audio)": CLEAN_CONFIG,
    "ENHANCED (fair audio)": ENHANCED_CONFIG,
    "RESCUE (noisy/poor audio)": RESCUE_CONFIG,
}

AUTO_DETECT_KEY = "Auto-detect (recommended)"

# Compatibility aliases for older callers/tests.
DEFAULT_CONFIG = ENHANCED_CONFIG
AGGRESSIVE_CONFIG = RESCUE_CONFIG
QUALITY_CONFIGS.update({
    "Clean (good/excellent audio)": CLEAN_CONFIG,
    "Default (fair audio)": DEFAULT_CONFIG,
    "Aggressive (noisy/poor audio)": AGGRESSIVE_CONFIG,
    "Default": DEFAULT_CONFIG,
    "Aggressive": AGGRESSIVE_CONFIG,
    "Clean": CLEAN_CONFIG,
})

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


def _hash_config(config_dict: dict) -> str:
    """Return a deterministic short hash for the effective preprocessing config."""
    payload = json.dumps(config_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:8]


def _build_active_config(config: dict, tier_name: str) -> dict:
    """Return the full effective preprocessing config that influences audio output."""
    return {
        "tier_name": tier_name,
        "target_sample_rate": TARGET_SAMPLE_RATE,
        "channels": 1,
        "audio_codec": "pcm_s16le",
        "video_disabled": True,
        "filters": dict(config),
    }


def _legacy_cache_path(input_path: Path, tier_name: str) -> str:
    """Return the pre-hash cache path for compatibility with older cache files."""
    slug = _tier_slug(tier_name)
    path_hash = hashlib.md5(str(input_path.resolve()).encode()).hexdigest()[:8]
    return os.path.join(TEMP_DIR, f"normalized_{input_path.stem}_{slug}_{path_hash}.wav")


def _cache_path(input_path: Path, tier_name: str, config: dict) -> str:
    """Return the deterministic cache path for the effective preprocessing config."""
    slug = _tier_slug(tier_name)
    path_hash = hashlib.md5(str(input_path.resolve()).encode()).hexdigest()[:8]
    config_hash = _hash_config(_build_active_config(config, tier_name))
    return os.path.join(
        TEMP_DIR,
        f"normalized_{input_path.stem}_{slug}_{path_hash}_{config_hash}.wav",
    )


def _resolve_tier_name(config: dict) -> str:
    for name, candidate in QUALITY_CONFIGS.items():
        if candidate is config:
            return name
        if candidate is not None and candidate.get("description") == config.get("description"):
            return name
    return config.get("description", "custom")


def _build_filter_chain(config: dict, audio_analysis=None) -> str:
    if audio_analysis and getattr(audio_analysis, "is_stereo", False):
        if audio_analysis.mono_strategy == "extract_left":
            channel_filter = "pan=mono|c0=c0"
        elif audio_analysis.mono_strategy == "extract_right":
            channel_filter = "pan=mono|c0=c1"
        else:
            channel_filter = "pan=mono|c0=0.5c0+0.5c1"
    else:
        channel_filter = "pan=mono|c0=0.5c0+0.5c1"

    filters = [channel_filter, f"highpass=f={config['highpass_freq']}"]

    if config.get("loudnorm"):
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    return ",".join(filters)


def is_stereo_dual_channel(file_path: str) -> bool:
    """
    Return True if the file is stereo with meaningfully different channels.
    """
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", file_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(probe.stdout or "{}")
        streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
        if not streams or streams[0].get("channels", 1) < 2:
            return False

        vol_result = subprocess.run(
            [
                "ffmpeg", "-i", file_path,
                "-filter_complex",
                "[0:a]channelsplit=channel_layout=stereo[L][R];"
                "[L]volumedetect[lv];[R]volumedetect[rv]",
                "-map", "[lv]", "-f", "null", os.devnull,
                "-map", "[rv]", "-f", "null", os.devnull,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        means = []
        for line in vol_result.stderr.splitlines():
            if "mean_volume" in line:
                try:
                    means.append(float(line.split(":")[1].strip().split()[0]))
                except (IndexError, ValueError):
                    continue
        if len(means) < 2:
            return False
        diff = abs(means[0] - means[1])
        logger.info(
            "[Preprocessor] Stereo channel difference: %.2f dB (%.2f vs %.2f)",
            diff,
            means[0],
            means[1],
        )
        return diff > 0.5
    except Exception as exc:
        logger.debug("[Preprocessor] Stereo detection failed: %s", exc)
        return False


def split_stereo_channels(
    file_path: str,
    output_dir: str,
    progress_callback=None,
) -> tuple[str, str]:
    """
    Split a stereo input into two mono WAV files.
    """
    stem = Path(file_path).stem
    left_path = str(Path(output_dir) / f"{stem}_ch0_left.wav")
    right_path = str(Path(output_dir) / f"{stem}_ch1_right.wav")

    if progress_callback:
        progress_callback("Splitting stereo channels for dual-mono transcription…")

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", file_path,
            "-filter_complex", "[0:a]channelsplit=channel_layout=stereo[L][R]",
            "-map", "[L]", "-ar", str(TARGET_SAMPLE_RATE), "-ac", "1", left_path,
            "-map", "[R]", "-ar", str(TARGET_SAMPLE_RATE), "-ac", "1", right_path,
        ],
        capture_output=True,
        check=True,
    )

    if progress_callback:
        progress_callback(
            f"Channels split: left → {Path(left_path).name}, right → {Path(right_path).name}"
        )
    return left_path, right_path


def auto_detect_quality(input_path: str) -> tuple[dict, str]:
    """
    Analyse the audio file and return the most appropriate quality config.
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
            "ffmpeg", "-t", "120",
            "-i", str(input_path),
            "-af", "volumedetect",
            "-f", "null", "-",
        ]
        vol_result = subprocess.run(vol_cmd, capture_output=True, text=True, timeout=120)
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
                mean_vol,
                max_vol,
                dynamic_range,
            )
    except Exception as exc:
        logger.warning("[Preprocessor] volumedetect failed: %s", exc)

    if very_poor_bitrate:
        tier_name = "RESCUE (noisy/poor audio)"
        config = RESCUE_CONFIG
    elif dynamic_range is not None and dynamic_range < 6:
        tier_name = "RESCUE (noisy/poor audio)"
        config = RESCUE_CONFIG
    elif poor_bitrate or dynamic_range is None or dynamic_range < 18:
        tier_name = "ENHANCED (fair audio)"
        config = ENHANCED_CONFIG
    else:
        tier_name = "CLEAN (good/excellent audio)"
        config = CLEAN_CONFIG

    logger.info("[Preprocessor] Auto-detect result: %s", tier_name)
    return config, tier_name


def normalize_audio(
    input_path: str,
    config: dict = None,
    auto_detect: bool = False,
    progress_callback=None,
    audio_analysis=None,
) -> str:
    """
    Normalize an audio or video file to a clean WAV suitable for Deepgram.
    """
    if auto_detect:
        config, tier_name = auto_detect_quality(str(input_path))
        logger.info("[Preprocessor] Auto-detected tier: %s", tier_name)
    elif config is None:
        config = ENHANCED_CONFIG
        tier_name = "ENHANCED (fair audio)"
        logger.info("[Preprocessor] No config supplied — using ENHANCED as safe fallback")
    else:
        tier_name = _resolve_tier_name(config)

    logger.info("[Preprocessor] Normalizing: %s  config=%s", Path(input_path).name, config["description"])
    if progress_callback:
        progress_callback(f"Normalizing audio: {config['description']}")

    os.makedirs(TEMP_DIR, exist_ok=True)

    input_path = Path(input_path)
    output_path = _cache_path(input_path, tier_name, config)
    legacy_output_path = _legacy_cache_path(input_path, tier_name)

    if os.path.exists(output_path) and os.path.getmtime(output_path) >= os.path.getmtime(str(input_path)):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(
            "[Preprocessor] Cache hit — skipping normalization: %s (%.1f MB)",
            output_path,
            size_mb,
        )
        if progress_callback:
            progress_callback(f"Using cached normalized audio ({size_mb:.1f} MB)  [{tier_name}]")
        return output_path

    if os.path.exists(legacy_output_path) and os.path.getmtime(legacy_output_path) >= os.path.getmtime(str(input_path)):
        logger.info(
            "[Preprocessor] Legacy cache present but config-sensitive cache required: %s",
            legacy_output_path,
        )

    filter_chain = _build_filter_chain(config, audio_analysis=audio_analysis)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "-ac",
        "1",
        "-af",
        filter_chain,
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("[Preprocessor] FFmpeg failed: %s", result.stderr[:300])
        raise RuntimeError(f"FFmpeg normalization failed:\n{result.stderr}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info("[Preprocessor] Output: %s  tier=%s  size_mb=%.1f", output_path, tier_name, size_mb)
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


def trim_long_silence(input_path: str) -> str:
    """
    Remove long silent passages (>20s) while keeping speech intact.

    Returns a path to the trimmed file (or the original input if trimming skipped).
    """
    input_path = Path(input_path)
    duration = get_audio_duration(str(input_path))
    logger.info("[Preprocessor] Silence trimming check: %s duration=%.1f", input_path.name, duration)
    if duration <= 60:
        return str(input_path)

    trimmed_path = input_path.with_name(f"{input_path.stem}_trimmed.wav")
    if trimmed_path.exists() and trimmed_path.stat().st_mtime >= input_path.stat().st_mtime:
        trimmed_duration = get_audio_duration(str(trimmed_path))
        removed = max(0.0, duration - trimmed_duration)
        logger.info("Silence trimming removed %.1f seconds (cached)", removed)
        return str(trimmed_path)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", "afftdn=nf=-25,silenceremove=stop_periods=-1:stop_duration=20:stop_threshold=-50dB:stop_silence=2",
        str(trimmed_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.error("[Preprocessor] Silence trimming failed: %s", stderr or "unknown ffmpeg error")
        return str(input_path)

    trimmed_duration = get_audio_duration(str(trimmed_path))
    removed = max(0.0, duration - trimmed_duration)
    logger.info(
        "[Preprocessor] Silence trimming removed %.1f seconds (%s -> %s)",
        removed, input_path.name, trimmed_path.name,
    )
    logger.info("Silence trimming removed %.1f seconds", removed)
    return str(trimmed_path)


def validate_audio_file(file_path: str) -> dict:
    """
    Validate that the input file is a supported audio/video format.
    """
    path = Path(file_path)

    if not path.exists():
        return {"valid": False, "duration": 0, "format": "", "error": "File not found"}

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {
            "valid": False,
            "duration": 0,
            "format": ext,
            "error": (
                f"Unsupported format: {ext}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        }

    duration = get_audio_duration(file_path)
    if duration <= 0:
        return {
            "valid": False,
            "duration": 0,
            "format": ext,
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
