"""
pipeline/chunker.py

Splits long audio files into overlapping chunks for Deepgram.

WHY CHUNKING IS NECESSARY:
  - Deepgram has a maximum file size limit and timeout on long files.
  - Long depositions (2-4 hours) must be split.
  - Overlapping chunks (20 seconds) prevent words at boundaries from being dropped.
  - The assembler deduplicates the overlap.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import List

from app_logging import get_logger
from config import (
    CHUNK_DURATION_SECONDS,
    CHUNK_OVERLAP_SECONDS,
    TARGET_SAMPLE_RATE,
    TEMP_DIR,
)

logger = get_logger(__name__)


@dataclass
class AudioChunk:
    index: int
    file_path: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    overlap_seconds: float


def _get_audio_duration_seconds(file_path: str) -> float:
    """Return audio duration from ffprobe, or 0.0 on failure."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float((result.stdout or "").strip())
    except (TypeError, ValueError):
        return 0.0


def _validate_chunk_file(
    chunk_path: str, expected_duration: float
) -> tuple[int, float]:
    """
    Fail fast on zero-byte or near-empty chunk outputs before Deepgram sees them.
    """
    chunk_size_bytes = os.path.getsize(chunk_path)
    actual_duration = _get_audio_duration_seconds(chunk_path)

    if chunk_size_bytes <= 4096:
        raise RuntimeError(
            f"Chunk output is too small to be valid: {os.path.basename(chunk_path)} "
            f"({chunk_size_bytes} bytes, expected ~{expected_duration:.1f}s)"
        )

    if expected_duration > 30 and actual_duration <= 1.0:
        raise RuntimeError(
            f"Chunk duration probe failed: {os.path.basename(chunk_path)} "
            f"(got {actual_duration:.2f}s, expected ~{expected_duration:.1f}s)"
        )

    return chunk_size_bytes, actual_duration


def chunk_audio(
    audio_path: str,
    total_duration: float,
    progress_callback=None,
) -> List[AudioChunk]:
    """
    Split audio into overlapping chunks if longer than CHUNK_DURATION_SECONDS.
    For short files returns a single-element list — no splitting.

    Returns:
        List of AudioChunk objects.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    if total_duration <= CHUNK_DURATION_SECONDS:
        if progress_callback:
            progress_callback(
                f"File is {total_duration:.0f}s — fits in single chunk, no split needed"
            )
        return [
            AudioChunk(
                index=0,
                file_path=audio_path,
                start_seconds=0.0,
                end_seconds=total_duration,
                duration_seconds=total_duration,
                overlap_seconds=0.0,
            )
        ]

    chunks: List[AudioChunk] = []
    total_chunk_size_bytes = 0
    start = 0.0
    chunk_index = 0

    while start < total_duration:
        end = min(start + CHUNK_DURATION_SECONDS, total_duration)
        is_last = end >= total_duration
        chunk_end = end if is_last else min(end + CHUNK_OVERLAP_SECONDS, total_duration)
        chunk_duration = chunk_end - start

        chunk_path = os.path.join(TEMP_DIR, f"chunk_{chunk_index:03d}.wav")

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            audio_path,
            "-t",
            str(chunk_duration),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-ac",
            "1",
            chunk_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg chunk {chunk_index} failed:\n{result.stderr}")

        chunk_size_bytes, actual_duration = _validate_chunk_file(
            chunk_path, chunk_duration
        )
        chunk_size_mb = chunk_size_bytes / (1024 * 1024)
        total_chunk_size_bytes += chunk_size_bytes
        chunk_readable = os.access(chunk_path, os.R_OK)
        chunk_name = os.path.basename(chunk_path)
        logger.info(
            "Chunk created index=%s path=%s size_mb=%.3f readable=%s start_seconds=%.1f end_seconds=%.1f duration_seconds=%.1f actual_duration=%.2f",
            chunk_index,
            chunk_path,
            chunk_size_mb,
            chunk_readable,
            start,
            chunk_end,
            chunk_duration,
            actual_duration,
        )
        print(f"[CHUNK] {chunk_name}: {chunk_duration:.0f}s - {chunk_size_mb:.3f} MB")

        chunks.append(
            AudioChunk(
                index=chunk_index,
                file_path=chunk_path,
                start_seconds=start,
                end_seconds=chunk_end,
                duration_seconds=chunk_duration,
                overlap_seconds=0.0 if is_last else CHUNK_OVERLAP_SECONDS,
            )
        )

        if progress_callback:
            progress_callback(
                f"Created chunk {chunk_index + 1}: "
                f"{start:.0f}s – {chunk_end:.0f}s ({chunk_duration:.0f}s)"
            )

        start = end
        chunk_index += 1

    if progress_callback:
        progress_callback(f"Audio split into {len(chunks)} chunks")
    logger.info(
        "Chunking complete chunk_count=%s total_chunk_size_mb=%.1f",
        len(chunks),
        total_chunk_size_bytes / (1024 * 1024),
    )
    print(
        f"[CHUNK] Total: {len(chunks)} chunks - {total_chunk_size_bytes / (1024 * 1024):.1f} MB combined"
    )

    return chunks


def cleanup_chunks(chunks: List[AudioChunk]) -> None:
    """Delete all temp chunk files. Does not delete the normalized file."""
    for chunk in chunks:
        try:
            if "chunk_" in chunk.file_path and os.path.exists(chunk.file_path):
                os.remove(chunk.file_path)
        except OSError:
            pass
