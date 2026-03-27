"""
pipeline/transcriber.py

Sends audio chunks to Deepgram and returns structured word/utterance data.

Supported models: nova-3, nova-3-medical

Two code paths:
  - SDK path:    no keyterms → uses deepgram-sdk PrerecordedOptions
  - Direct path: keyterms present → bypasses SDK, POSTs via httpx with keyterm= params
    (SDK only exposes `keywords` which Nova-3 rejects; the API wants `keyterm`)
"""

import os
import time
import traceback
from typing import Any, Dict

import httpx

from app_logging import get_logger
from config import (
    DEEPGRAM_CHUNK_SIZE_LIMIT_MB,
    DEEPGRAM_CONNECTION_TIMEOUT,
    DEEPGRAM_READ_TIMEOUT,
    DEEPGRAM_WRITE_TIMEOUT,
)

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10

ALLOWED_MODELS = {"nova-3", "nova-3-medical"}


def _get_client():
    """Return a configured Deepgram SDK client."""
    try:
        from deepgram import DeepgramClient, DeepgramClientOptions
    except ImportError as exc:
        raise ImportError(
            "deepgram-sdk is not installed. Run: pip install deepgram-sdk"
        ) from exc

    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY is not set. Add it to your .env file.")

    config = DeepgramClientOptions(
        api_key=api_key,
        options={
            "timeout_connection": DEEPGRAM_CONNECTION_TIMEOUT,
            "timeout_read":       DEEPGRAM_READ_TIMEOUT,
            "timeout_write":      DEEPGRAM_WRITE_TIMEOUT,
        },
    )
    return DeepgramClient(api_key, config=config)


def _transcribe_direct(
    audio_file_path: str,
    model: str = "nova-3",
    utt_split: float = 0.85,
    keyterms: list = None,
    progress_callback=None,
) -> dict:
    """
    Direct HTTP POST to Deepgram API.
    Used when keyterms are provided because the SDK does not support
    the keyterm= parameter that Nova-3 requires.
    """
    import json as _json
    import urllib.parse as _parse

    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY is not set.")

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
        for kt in keyterms[:200]:
            query += "&keyterm=" + _parse.quote(str(kt), safe="")

    url = f"https://api.deepgram.com/v1/listen?{query}"
    chunk_name = os.path.basename(audio_file_path)

    logger.info(
        "Deepgram direct HTTP call chunk=%s model=%s keyterms=%s",
        chunk_name, model, len(keyterms or []),
    )

    if progress_callback:
        progress_callback(f"Sending to Deepgram (with keyterms): {chunk_name}")

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

            utterances = [
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

            elapsed = time.time() - t0
            logger.info(
                "Deepgram direct OK chunk=%s elapsed=%.2fs words=%s utterances=%s",
                chunk_name, elapsed, len(words), len(utterances),
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
    utt_split: float = 0.85,
    keyterms: list = None,
    progress_callback=None,
) -> Dict[str, Any]:
    """
    Transcribe one audio chunk via Deepgram.

    Routes to direct HTTP when keyterms are provided (SDK does not support
    the keyterm= parameter). Otherwise uses the SDK.

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

    # Use direct HTTP when keyterms are provided (SDK does not support keyterm=)
    if keyterms:
        return _transcribe_direct(
            audio_file_path,
            model=model,
            utt_split=utt_split,
            keyterms=keyterms,
            progress_callback=progress_callback,
        )

    # SDK path when no keyterms
    try:
        from deepgram import PrerecordedOptions
    except ImportError as exc:
        raise ImportError("deepgram-sdk is not installed.") from exc

    options = PrerecordedOptions(
        model=model,
        language="en",
        smart_format=True,
        punctuate=True,
        paragraphs=True,
        diarize=True,
        utterances=True,
        filler_words=True,
        numerals=True,
        dictation=False,
        profanity_filter=False,
        utt_split=utt_split,
    )

    chunk_name     = os.path.basename(audio_file_path)
    chunk_size_mb  = os.path.getsize(audio_file_path) / (1024 * 1024)

    if chunk_size_mb > DEEPGRAM_CHUNK_SIZE_LIMIT_MB:
        logger.warning(
            "Chunk may exceed safe upload limit: %s (%.1f MB > %s MB)",
            chunk_name, chunk_size_mb, DEEPGRAM_CHUNK_SIZE_LIMIT_MB,
        )

    if progress_callback:
        progress_callback(f"Sending to Deepgram: {chunk_name}")

    client  = _get_client()
    timeout = httpx.Timeout(
        timeout=DEEPGRAM_READ_TIMEOUT,
        connect=DEEPGRAM_CONNECTION_TIMEOUT,
        read=DEEPGRAM_READ_TIMEOUT,
        write=DEEPGRAM_WRITE_TIMEOUT,
    )

    with open(audio_file_path, "rb") as f:
        buffer = f.read()

    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Deepgram attempt %s/%s chunk=%s model=%s", attempt, MAX_RETRIES, chunk_name, model)
        t0 = time.time()

        try:
            response = client.listen.prerecorded.v("1").transcribe_file(
                {"buffer": buffer},
                options,
                timeout=timeout,
            )
            elapsed = time.time() - t0

            alt   = response.results.channels[0].alternatives[0]
            words = [
                {
                    "word":            w.word,
                    "start":           w.start,
                    "end":             w.end,
                    "confidence":      w.confidence,
                    "speaker":         getattr(w, "speaker", None),
                    "punctuated_word": getattr(w, "punctuated_word", w.word),
                }
                for w in (alt.words or [])
            ]

            utterances = []
            if response.results.utterances:
                for u in response.results.utterances:
                    utterances.append({
                        "speaker":    u.speaker,
                        "start":      u.start,
                        "end":        u.end,
                        "transcript": u.transcript,
                        "confidence": u.confidence,
                        "words": [
                            {
                                "word":       w.word,
                                "start":      w.start,
                                "end":        w.end,
                                "confidence": w.confidence,
                                "speaker":    getattr(w, "speaker", None),
                            }
                            for w in (u.words or [])
                        ],
                    })

            logger.info(
                "Deepgram OK chunk=%s elapsed=%.2fs words=%s utterances=%s",
                chunk_name, elapsed, len(words), len(utterances),
            )

            if progress_callback:
                progress_callback(f"Done: {len(words)} words, {len(utterances)} utterances")

            return {
                "words":       words,
                "utterances":  utterances,
                "transcript":  alt.transcript or "",
                "raw":         response.to_dict(),
            }

        except Exception as exc:
            last_exc   = exc
            elapsed    = time.time() - t0
            is_timeout = isinstance(exc, httpx.TimeoutException) or "timed out" in str(exc).lower()

            logger.error(
                "Deepgram attempt %s/%s FAILED chunk=%s elapsed=%.2fs error=%s",
                attempt, MAX_RETRIES, chunk_name, elapsed, exc,
            )

            if attempt < MAX_RETRIES and is_timeout:
                logger.warning("Timeout -- retrying in %ss", RETRY_DELAY_SECONDS)
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            break

    raise RuntimeError(
        f"Deepgram transcription failed after {MAX_RETRIES} attempts: {last_exc}"
    )
