"""
pipeline/vad_trimmer.py

Silero VAD-based silence trimmer for deposition audio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app_logging import get_logger

logger = get_logger(__name__)

SILERO_THRESHOLD = 0.35
MIN_SPEECH_MS = 100
MIN_SILENCE_MS = 700
SPEECH_PAD_MS = 300
SAMPLE_RATE = 16000


@dataclass
class TrimResult:
    output_path: str
    original_duration_s: float
    trimmed_duration_s: float
    silence_removed_s: float
    speech_segment_count: int
    was_trimmed: bool


def trim_silence(input_wav_path: str, output_path: str | None = None) -> TrimResult:
    """
    Trim long dead-air silence from a WAV file using Silero VAD.
    """
    import shutil

    import torchaudio
    from silero_vad import collect_chunks, get_speech_timestamps, load_silero_vad

    if output_path is None:
        base = os.path.splitext(input_wav_path)[0]
        output_path = base + "_vad.wav"

    logger.info("[VADTrimmer] Loading audio: %s", os.path.basename(input_wav_path))

    wav, sr = torchaudio.load(input_wav_path)
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != SAMPLE_RATE:
        wav = torchaudio.functional.resample(wav, sr, SAMPLE_RATE)
    wav = wav.squeeze()

    original_duration = len(wav) / SAMPLE_RATE
    model = load_silero_vad()

    timestamps = get_speech_timestamps(
        wav,
        model,
        threshold=SILERO_THRESHOLD,
        min_speech_duration_ms=MIN_SPEECH_MS,
        min_silence_duration_ms=MIN_SILENCE_MS,
        speech_pad_ms=SPEECH_PAD_MS,
        sampling_rate=SAMPLE_RATE,
        return_seconds=False,
    )

    if not timestamps:
        logger.warning("[VADTrimmer] No speech detected — preserving original file as-is.")
        shutil.copy2(input_wav_path, output_path)
        return TrimResult(
            output_path=output_path,
            original_duration_s=round(original_duration, 2),
            trimmed_duration_s=round(original_duration, 2),
            silence_removed_s=0.0,
            speech_segment_count=0,
            was_trimmed=False,
        )

    trimmed = collect_chunks(timestamps, wav)
    torchaudio.save(output_path, trimmed.unsqueeze(0), SAMPLE_RATE)

    trimmed_duration = len(trimmed) / SAMPLE_RATE
    silence_removed = max(0.0, original_duration - trimmed_duration)

    logger.info(
        "[VADTrimmer] Trimmed: %.1fs → %.1fs (removed %.1fs silence, %d speech segments)",
        original_duration,
        trimmed_duration,
        silence_removed,
        len(timestamps),
    )

    return TrimResult(
        output_path=output_path,
        original_duration_s=round(original_duration, 2),
        trimmed_duration_s=round(trimmed_duration, 2),
        silence_removed_s=round(silence_removed, 2),
        speech_segment_count=len(timestamps),
        was_trimmed=True,
    )
