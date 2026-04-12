"""
pipeline/pyannote_diarizer.py

GPU-accelerated pyannote.audio speaker diarization for Depo-Pro.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from app_logging import get_logger

logger = get_logger(__name__)

MIN_SPEAKERS = 2
MAX_SPEAKERS = 6
MODEL_NAME = "pyannote/speaker-diarization-3.1"

_pipeline_cache = None


def _load_pipeline():
    """Load the pyannote pipeline once per session."""
    global _pipeline_cache
    if _pipeline_cache is not None:
        return _pipeline_cache

    try:
        import torch
        from pyannote.audio import Pipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("[Pyannote] Loading %s on %s", MODEL_NAME, device)

        pipeline = Pipeline.from_pretrained(
            MODEL_NAME,
            token=os.getenv("HF_TOKEN"),
        )
        if device == "cuda":
            pipeline = pipeline.to(torch.device("cuda"))
            logger.info("[Pyannote] GPU acceleration active")
        else:
            logger.warning(
                "[Pyannote] No CUDA GPU found — running on CPU. "
                "Expect 15-30 min processing time for 30-min audio."
            )

        _pipeline_cache = pipeline
        return pipeline
    except Exception as exc:
        logger.error("[Pyannote] Failed to load pipeline: %s", exc)
        raise


def diarize(audio_path: str) -> Optional[List[Dict]]:
    """
    Run pyannote diarization and return normalized speaker segments.
    """
    try:
        pipeline = _load_pipeline()

        logger.info("[Pyannote] Diarizing: %s", os.path.basename(audio_path))
        diarization = pipeline(
            audio_path,
            min_speakers=MIN_SPEAKERS,
            max_speakers=MAX_SPEAKERS,
        )

        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "speaker": speaker,
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
            })

        unique_speakers = sorted({segment["speaker"] for segment in segments})
        logger.info(
            "[Pyannote] Complete: %d segments, speakers: %s",
            len(segments),
            unique_speakers,
        )
        return segments
    except Exception as exc:
        logger.error("[Pyannote] Diarization failed: %s — using Deepgram labels", exc)
        return None


def align_speakers(
    deepgram_utterances: List[Dict],
    pyannote_segments: List[Dict],
) -> List[Dict]:
    """
    Replace Deepgram speaker IDs with pyannote-aligned speaker IDs.
    """
    if not pyannote_segments:
        return deepgram_utterances

    speaker_labels = sorted({segment["speaker"] for segment in pyannote_segments})
    label_to_int = {label: index for index, label in enumerate(speaker_labels)}

    replaced = 0
    for utterance in deepgram_utterances:
        u_start = float(utterance.get("start", 0.0))
        u_end = float(utterance.get("end", 0.0))

        best_speaker = None
        best_overlap = 0.1

        for segment in pyannote_segments:
            overlap = max(
                0.0,
                min(u_end, segment["end"]) - max(u_start, segment["start"]),
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = segment["speaker"]

        if best_speaker is not None:
            utterance["speaker"] = label_to_int[best_speaker]
            replaced += 1

    logger.info(
        "[Pyannote] Speaker alignment: %d/%d utterances updated",
        replaced,
        len(deepgram_utterances),
    )
    return deepgram_utterances
