"""
core/word_data_loader.py

Load Deepgram word-level timestamps and normalize confidence values for
transcript review, highlighting, and click-to-jump playback.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIDENCE_HIGH = 0.90
CONFIDENCE_MEDIUM = 0.80
CONFIDENCE_LOW = 0.70
CONFIDENCE_CRITICAL = 0.00

_IGNORE_SUFFIXES = (
    "_corrected",
    "_renamed",
    "_formatted",
)
_IGNORE_JSON_SUFFIXES = (
    "_raw.json",
    "_ufm_fields.json",
    "_corrections.json",
)


def _base_stem(path: str) -> str:
    stem = Path(path).stem
    changed = True
    while changed:
        changed = False
        for suffix in _IGNORE_SUFFIXES:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                changed = True
    return stem


def _find_json_for_transcript(transcript_path: str) -> str | None:
    transcript = Path(transcript_path)
    if not transcript.exists():
        return None

    folder = transcript.parent
    stem = _base_stem(transcript_path)
    json_files = [
        p for p in folder.glob("*.json")
        if not any(p.name.endswith(suffix) for suffix in _IGNORE_JSON_SUFFIXES)
    ]
    if not json_files:
        return None

    exact_candidates = [
        p for p in json_files
        if _base_stem(str(p)) == stem or p.stem == stem
    ]
    if exact_candidates:
        exact_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(exact_candidates[0])

    named_candidates = [
        p for p in json_files
        if stem.lower() in p.stem.lower()
    ]
    if named_candidates:
        named_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(named_candidates[0])

    json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(json_files[0])


def _extract_words(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    try:
        return payload["results"]["channels"][0]["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError):
        return payload.get("words", []) if isinstance(payload.get("words"), list) else []


def load_words_for_transcript(transcript_path: str) -> list[dict]:
    json_path = _find_json_for_transcript(transcript_path)
    if not json_path or not os.path.isfile(json_path):
        return []

    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return []

    words = []
    for word in _extract_words(payload):
        if not isinstance(word, dict):
            continue
        text = str(word.get("punctuated_word") or word.get("word") or "").strip()
        if not text:
            continue
        try:
            start = float(word.get("start", 0.0) or 0.0)
        except (TypeError, ValueError):
            start = 0.0
        try:
            end = float(word.get("end", start) or start)
        except (TypeError, ValueError):
            end = start
        try:
            confidence = float(word.get("confidence", 1.0) or 1.0)
        except (TypeError, ValueError):
            confidence = 1.0
        words.append(
            {
                "text": text,
                "start": start,
                "end": end,
                "confidence": max(0.0, min(1.0, confidence)),
            }
        )
    return words


def get_confidence_tier(confidence: float) -> str:
    value = float(confidence)
    if value >= CONFIDENCE_HIGH:
        return "high"
    if value >= CONFIDENCE_MEDIUM:
        return "medium"
    if value >= CONFIDENCE_LOW:
        return "low"
    return "critical"


def get_flagged_summary(words: list[dict]) -> dict[str, int]:
    summary = {
        "total": len(words),
        "high": 0,
        "medium": 0,
        "low": 0,
        "critical": 0,
        "flagged": 0,
    }
    for word in words:
        tier = get_confidence_tier(float(word.get("confidence", 1.0)))
        summary[tier] += 1
        if tier in {"low", "critical"}:
            summary["flagged"] += 1
    return summary
