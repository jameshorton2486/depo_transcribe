"""
pipeline/audio_quality.py

Audio quality analysis and stereo channel detection for the Depo-Pro
preprocessing pipeline.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from app_logging import get_logger

logger = get_logger(__name__)


@dataclass
class AudioAnalysis:
    """Results of audio quality analysis."""

    tier: str
    is_stereo: bool
    zoom_dual_mono: bool
    mono_strategy: str
    snr_db: float
    mean_volume_db: float
    max_volume_db: float
    clipping_ratio: float
    channel_count: int
    issues: list[str]


def _run_ffprobe_json(file_path: str) -> dict:
    """Get audio stream info from ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "a:0",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout or "{}")
    except Exception:
        return {}


def _get_volume_stats(file_path: str) -> dict:
    """Run ffmpeg volumedetect on the full file."""
    cmd = [
        "ffmpeg",
        "-i",
        file_path,
        "-af",
        "volumedetect",
        "-vn",
        "-f",
        "null",
        "NUL",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr or ""

    def _extract(key: str) -> float | None:
        match = re.search(rf"{key}: (-?\d+\.?\d*) dB", output)
        return float(match.group(1)) if match else None

    return {
        "mean_volume": _extract("mean_volume"),
        "max_volume": _extract("max_volume"),
    }


def _extract_channel_samples(file_path: str, channel: int, duration: float = 5.0) -> np.ndarray:
    """Extract the first few seconds of one channel as float32 samples."""
    cmd = [
        "ffmpeg",
        "-i",
        file_path,
        "-t",
        str(duration),
        "-af",
        f"pan=mono|c0=c{channel}",
        "-ar",
        "16000",
        "-f",
        "f32le",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        return np.array([], dtype=np.float32)
    return np.frombuffer(result.stdout, dtype=np.float32)


def _detect_stereo_strategy(file_path: str) -> Tuple[bool, str]:
    """
    For stereo files, detect if channels are duplicates (Zoom dual-mono).

    Returns:
        (zoom_dual_mono, mono_strategy)
    """
    left = _extract_channel_samples(file_path, channel=0)
    right = _extract_channel_samples(file_path, channel=1)
    if len(left) == 0 or len(right) == 0:
        return False, "average"

    min_len = min(len(left), len(right))
    left = left[:min_len]
    right = right[:min_len]

    if np.std(left) < 1e-6 and np.std(right) < 1e-6:
        return True, "extract_left"
    if np.std(left) < 1e-6:
        return True, "extract_right"
    if np.std(right) < 1e-6:
        return True, "extract_left"

    correlation = float(np.corrcoef(left, right)[0, 1])
    logger.info("[AudioQuality] Channel correlation: %.3f", correlation)

    if correlation > 0.8:
        rms_left = float(np.sqrt(np.mean(left ** 2)))
        rms_right = float(np.sqrt(np.mean(right ** 2)))
        strategy = "extract_left" if rms_left >= rms_right else "extract_right"
        logger.info(
            "[AudioQuality] Zoom dual-mono detected (corr=%.3f). "
            "Using %s (L-RMS=%.4f R-RMS=%.4f)",
            correlation,
            strategy,
            rms_left,
            rms_right,
        )
        return True, strategy

    logger.info("[AudioQuality] True stereo (corr=%.3f). Using channel average.", correlation)
    return False, "average"


def _estimate_snr(mean_db: float | None, max_db: float | None) -> float:
    """
    Estimate SNR from volumedetect output using headroom as a proxy.
    """
    if mean_db is None or max_db is None:
        return 15.0

    headroom = max_db - mean_db
    if mean_db > -25 and headroom > 8:
        return 28.0
    if mean_db > -35 and headroom > 5:
        return 20.0
    return 10.0


def _clipping_ratio(max_db: float | None) -> float:
    """Estimate clipping from max-volume proximity to 0 dBFS."""
    if max_db is None:
        return 0.0
    return max(0.0, 1.0 + max_db / 3.0)


def analyze_audio(file_path: str) -> AudioAnalysis:
    """
    Analyze audio file and return quality classification plus stereo strategy.
    """
    logger.info("[AudioQuality] Analyzing: %s", file_path)

    probe = _run_ffprobe_json(file_path)
    streams = probe.get("streams", [{}])
    stream = streams[0] if streams else {}
    channel_count = int(stream.get("channels", 1) or 1)
    is_stereo = channel_count >= 2

    vol = _get_volume_stats(file_path)
    mean_db = vol.get("mean_volume")
    max_db = vol.get("max_volume")

    zoom_dual_mono = False
    mono_strategy = "average"
    if is_stereo:
        zoom_dual_mono, mono_strategy = _detect_stereo_strategy(file_path)

    snr_db = _estimate_snr(mean_db, max_db)
    clipping = _clipping_ratio(max_db)

    issues: list[str] = []
    if mean_db is not None and mean_db < -40:
        issues.append(f"Very quiet audio (mean {mean_db:.1f} dB) — may need gain boost")
    if clipping > 0.5 and max_db is not None:
        issues.append(f"Near-clipping detected (max {max_db:.1f} dBFS)")
    if zoom_dual_mono:
        issues.append("Zoom dual-mono detected — extracting single channel to eliminate echo")

    if snr_db >= 25 and clipping < 0.3:
        tier = "CLEAN"
    elif snr_db >= 15:
        tier = "ENHANCED"
        issues.append(f"Estimated SNR {snr_db:.0f} dB — ENHANCED tier (Deepgram diarization)")
    else:
        tier = "RESCUE"
        issues.append(f"Estimated SNR {snr_db:.0f} dB — applying conservative denoising")

    result = AudioAnalysis(
        tier=tier,
        is_stereo=is_stereo,
        zoom_dual_mono=zoom_dual_mono,
        mono_strategy=mono_strategy,
        snr_db=snr_db,
        mean_volume_db=mean_db if mean_db is not None else -30.0,
        max_volume_db=max_db if max_db is not None else -3.0,
        clipping_ratio=clipping,
        channel_count=channel_count,
        issues=issues,
    )

    logger.info(
        "[AudioQuality] Result: tier=%s stereo=%s zoom_dual_mono=%s "
        "strategy=%s snr=%.1fdB mean=%.1fdB",
        tier,
        is_stereo,
        zoom_dual_mono,
        mono_strategy,
        snr_db,
        result.mean_volume_db,
    )
    for issue in issues:
        logger.info("[AudioQuality] Issue: %s", issue)

    return result
