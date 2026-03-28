"""
pipeline/transcriber.py

Sends audio chunks to Deepgram and returns structured word/utterance data.

Supported models: nova-3, nova-3-medical

All requests use direct HTTP via httpx, with or without keyterms.
"""

import os
import time
from typing import Any, Dict

import httpx

from app_logging import get_logger
from config import (
    DEEPGRAM_CONNECTION_TIMEOUT,
    DEEPGRAM_READ_TIMEOUT,
    DEEPGRAM_WRITE_TIMEOUT,
)
from core.keyterm_extractor import MAX_KEYTERMS
from core.transcript_merger import merge_utterances

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10

ALLOWED_MODELS = {"nova-3", "nova-3-medical"}


def _transcribe_direct(
    audio_file_path: str,
    model: str = "nova-3",
    utt_split: float = 1.2,
    keyterms: list = None,
    progress_callback=None,
) -> dict:
    """
    Direct HTTP POST to Deepgram API.
    Used for every transcription request, with or without keyterms.
    """
    import urllib.parse as _parse

    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY is not set.")

    keyterms = list(keyterms or [])[:MAX_KEYTERMS]
    logger.info(
        "[Transcriber] Keyterm breakdown  total=%d sending=%d",
        len(keyterms or []),
        min(len(keyterms or []), 100),
    )

    params = {
        "model": model,
        "language": "en",
        "smart_format": "true",
        "punctuate": "true",
        "paragraphs": "true",
        "diarize": "true",
        "utterances": "true",
        "filler_words": "true",
        "numerals": "true",
        "dictation": "false",
        "profanity_filter": "false",
        "utt_split": str(utt_split),
    }
    query = _parse.urlencode(params)
    if keyterms:
        for kt in keyterms:
            query += "&keyterm=" + _parse.quote(str(kt), safe="")

    url = f"https://api.deepgram.com/v1/listen?{query}"
    chunk_name = os.path.basename(audio_file_path)

    logger.info(
        "Deepgram direct HTTP call chunk=%s model=%s keyterms=%s",
        chunk_name, model, len(keyterms or []),
    )

    if progress_callback:
        progress_callback(f"Sending to Deepgram: {chunk_name}")

    with open(audio_file_path, "rb") as f:
        buffer = f.read()

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.time()
        try:
            resp = httpx.post(
                url,
                content=buffer,
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type": "audio/*",
                },
                timeout=httpx.Timeout(
                    timeout=DEEPGRAM_READ_TIMEOUT,
                    connect=DEEPGRAM_CONNECTION_TIMEOUT,
                    read=DEEPGRAM_READ_TIMEOUT,
                    write=DEEPGRAM_WRITE_TIMEOUT,
                ),
            )
            resp.raise_for_status()
            raw = resp.json()

            alt = raw["results"]["channels"][0]["alternatives"][0]
            words = [
                {
                    "word":            w.get("word", ""),
                    "start":           w.get("start", 0),
                    "end":             w.get("end", 0),
                    "confidence":      w.get("confidence", 0),
                    "speaker":         w.get("speaker"),
                    "punctuated_word": w.get("punctuated_word", w.get("word", "")),
                }
                for w in alt.get("words", [])
            ]

            raw_utterances = [
                {
                    "speaker":    u.get("speaker"),
                    "start":      u.get("start", 0),
                    "end":        u.get("end", 0),
                    "transcript": u.get("transcript", ""),
                    "confidence": u.get("confidence", 0),
                    "words": [
                        {
                            "word":       w.get("word", ""),
                            "start":      w.get("start", 0),
                            "end":        w.get("end", 0),
                            "confidence": w.get("confidence", 0),
                            "speaker":    w.get("speaker"),
                        }
                        for w in u.get("words", [])
                    ],
                }
                for u in raw["results"].get("utterances", [])
            ]
            utterances = merge_utterances(
                raw_utterances,
                gap_threshold_seconds=1.5,
                min_word_count=2,
            )

            elapsed = time.time() - t0
            logger.info(
                "Deepgram direct OK chunk=%s elapsed=%.2fs words=%s utterances=%s raw_utterances=%s",
                chunk_name, elapsed, len(words), len(utterances), len(raw_utterances),
            )

            if progress_callback:
                progress_callback(f"Done: {len(words)} words, {len(utterances)} utterances")

            return {
                "words":      words,
                "utterances": utterances,
                "transcript": alt.get("transcript", ""),
                "raw":        raw,
            }

        except Exception as exc:
            last_exc = exc
            elapsed = time.time() - t0
            is_timeout = (
                isinstance(exc, httpx.TimeoutException)
                or "timed out" in str(exc).lower()
            )
            logger.error(
                "Direct attempt %s/%s FAILED chunk=%s elapsed=%.2fs error=%s",
                attempt, MAX_RETRIES, chunk_name, elapsed, exc,
            )
            if attempt < MAX_RETRIES and is_timeout:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            break

    raise RuntimeError(
        f"Deepgram transcription failed after {MAX_RETRIES} attempts: {last_exc}"
    )


def transcribe_chunk(
    audio_file_path: str,
    model: str = "nova-3",
    utt_split: float = 1.2,
    keyterms: list = None,
    progress_callback=None,
) -> Dict[str, Any]:
    """
    Transcribe one audio chunk via Deepgram.

    Uses direct HTTP for all requests so the Deepgram SDK is not required.

    Returns:
        {
            "words":      list of word dicts with timestamps,
            "utterances": list of speaker-grouped utterance dicts,
            "transcript": full plain-text string,
            "raw":        complete Deepgram response as dict,
        }

    Raises:
        RuntimeError on failure after all retries.
    """
    if model not in ALLOWED_MODELS:
        raise ValueError(
            f"Model '{model}' is not allowed. "
            f"Use one of: {sorted(ALLOWED_MODELS)}"
        )

    keyterms = list(keyterms or [])[:MAX_KEYTERMS]
    logger.info(
        "Sending %s keyterms to Deepgram (direct path): %s",
        len(keyterms), keyterms[:10],
    )
    return _transcribe_direct(
        audio_file_path,
        model=model,
        utt_split=utt_split,
        keyterms=keyterms,
        progress_callback=progress_callback,
    )
