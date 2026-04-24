"""
pipeline/transcriber.py

Sends audio chunks to Deepgram and returns structured word/utterance data.

Supported models: nova-3, nova-3-medical

All requests use direct HTTP via httpx.
"""

import os
import subprocess
import time
from typing import Any, Dict

import httpx

from app_logging import get_logger
from config import (
    DEEPGRAM_CONNECTION_TIMEOUT,
    DEEPGRAM_READ_TIMEOUT,
    DEEPGRAM_WRITE_TIMEOUT,
)
from core.transcript_merger import merge_utterances

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10

ALLOWED_MODELS = {"nova-3", "nova-3-medical"}

NEAR_SILENT_THRESHOLD_DB = -55.0
REQUEST_DEBUG_PREFIX = "DEEPGRAM PARAMS:"
RAW_UTTERANCE_DEBUG_PREFIX = "RAW UTTERANCE SAMPLE:"
MERGED_UTTERANCE_DEBUG_PREFIX = "MERGED UTTERANCE SAMPLE:"
REQUIRED_DEEPGRAM_FLAGS = {
    "utterances": "true",
    "diarize": "true",
    "paragraphs": "false",
}


def _is_near_silent(file_path: str) -> bool:
    """
    Return True when ffmpeg volumedetect reports no speech above the threshold.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", file_path,
                "-af", "volumedetect",
                "-vn", "-sn", "-dn",
                "-f", "null", os.devnull,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stderr.splitlines():
            if "max_volume" in line:
                try:
                    max_vol = float(line.split(":")[1].strip().split()[0])
                    return max_vol < NEAR_SILENT_THRESHOLD_DB
                except (IndexError, ValueError):
                    continue
    except Exception as exc:
        logger.warning("volumedetect failed for %s: %s", file_path, exc)
    return False


def normalize_params(params: dict) -> dict:
    return {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in params.items()
    }


def enforce_required_deepgram_flags(params: dict) -> dict:
    enforced = dict(params)
    enforced.update(REQUIRED_DEEPGRAM_FLAGS)
    return enforced


def validate_deepgram_params(params: dict) -> dict:
    """
    Deepgram boolean query params must be lowercase strings: "true"/"false".
    Reject stale TitleCase values before they become request-time surprises.
    """
    validated = {}
    for key, value in params.items():
        if isinstance(value, list):
            items = []
            for item in value:
                if isinstance(item, str) and item in {"True", "False"}:
                    raise ValueError(
                        f"Invalid Deepgram param {key}={item!r}; use lowercase 'true'/'false'."
                    )
                items.append(item)
            validated[key] = items
            continue

        if isinstance(value, str) and value in {"True", "False"}:
            raise ValueError(
                f"Invalid Deepgram param {key}={value!r}; use lowercase 'true'/'false'."
            )
        validated[key] = value
    return validated


def _transcribe_direct(
    audio_file_path: str,
    model: str = "nova-3",
    utt_split: float = 1.2,
    keyterms: list = None,
    progress_callback=None,
) -> dict:
    """
    Direct HTTP POST to Deepgram API.
    Used for every transcription request.
    """
    import urllib.parse as _parse

    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY is not set.")

    # Legal transcript constraints:
    # - filler_words must stay on for verbatim compliance (uh/um are legal record)
    # - smart_format stays OFF to avoid Deepgram rewriting dates/currency
    # - numerals must stay OFF — spec_engine owns all number normalization
    # - utt_split must honor the caller-provided parameter
    # - paragraphs stays OFF so downstream formatting owns transcript structure
    # - utterances=True is required — correction_runner checks for this key
    # - preserve the current return contract; expose extra debug context without
    #   changing downstream behavior
    normalized_keyterms = [
        str(term).strip() for term in (keyterms or []) if str(term).strip()
    ]

    params = normalize_params({
        "model":        model,
        "language":     "en",
        "smart_format": False,
        "diarize":      True,
        "punctuate":    True,
        "paragraphs":   False,
        "utterances":   True,
        "utt_split":    utt_split,
        "filler_words": True,
        "numerals":     False,
    })
    params = enforce_required_deepgram_flags(params)
    params = validate_deepgram_params(params)

    if normalized_keyterms:
        params.setdefault("keyterm", []).extend(normalized_keyterms)
    query = _parse.urlencode(params, doseq=True)

    url = f"https://api.deepgram.com/v1/listen?{query}"
    chunk_name = os.path.basename(audio_file_path)

    logger.info("Deepgram direct HTTP call chunk=%s params=%s", chunk_name, params)
    print(REQUEST_DEBUG_PREFIX, params)

    if progress_callback:
        progress_callback(f"Sending to Deepgram: {chunk_name}")

    with open(audio_file_path, "rb") as f:
        buffer = f.read()

    if _is_near_silent(audio_file_path):
        logger.warning(
            "Skipping near-silent chunk=%s (max_volume < %.0fdB) — likely a recess or break.",
            chunk_name,
            NEAR_SILENT_THRESHOLD_DB,
        )
        if progress_callback:
            progress_callback(f"Skipped silent chunk: {chunk_name} (recess/break detected)")
        return {"words": [], "utterances": [], "transcript": "", "raw": {}}

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.time()
        try:
            resp = httpx.post(
                url,
                content=buffer,
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type":  "audio/*",
                },
                timeout=httpx.Timeout(
                    timeout=DEEPGRAM_READ_TIMEOUT,
                    connect=DEEPGRAM_CONNECTION_TIMEOUT,
                    read=DEEPGRAM_READ_TIMEOUT,
                    write=DEEPGRAM_WRITE_TIMEOUT,
                ),
            )
            if resp.status_code != 200:
                logger.error("Deepgram returned status %s: %s", resp.status_code, resp.text[:1024])
            resp.raise_for_status()
            raw = resp.json()
            results = raw.get("results") or {}
            raw_utterances = results.get("utterances")
            if not isinstance(raw_utterances, list) or not raw_utterances:
                logger.error("Deepgram response missing utterances: %s", raw)
                raise ValueError("Deepgram returned no utterances; transcription cannot proceed.")

            logger.info("Utterances received: %s", len(raw_utterances))
            print(f"Utterances received: {len(raw_utterances)}")

            alt = results["channels"][0]["alternatives"][0]
            words = [
                {
                    "word":            w.get("word", ""),
                    "start":           w.get("start", 0),
                    "end":             w.get("end", 0),
                    "confidence":      w.get("confidence", 0),
                    "speaker":         w.get("speaker"),
                    "punctuated_word": w.get("punctuated_word", w.get("word", "")),
                    "type":            w.get("type", "word"),
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
                            "type":       w.get("type", "word"),
                        }
                        for w in u.get("words", [])
                    ],
                }
                for u in raw_utterances
            ]
            utterances = merge_utterances(
                raw_utterances,
                gap_threshold_seconds=1.5,
                min_word_count=2,
            )

            logger.debug("%s %s", RAW_UTTERANCE_DEBUG_PREFIX, raw_utterances[:2])
            logger.debug("%s %s", MERGED_UTTERANCE_DEBUG_PREFIX, utterances[:2])

            elapsed = time.time() - t0
            logger.info(
                "Deepgram direct OK chunk=%s elapsed=%.2fs words=%s utterances=%s raw_utterances=%s",
                chunk_name, elapsed, len(words), len(utterances), len(raw_utterances),
            )

            if progress_callback:
                progress_callback(f"Done: {len(words)} words, {len(utterances)} utterances")

            return {
                "words":            words,
                "utterances":       utterances,
                "raw_utterances":   raw_utterances,
                "transcript":       alt.get("transcript", ""),
                "raw":              raw,
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
            "words":          list of word dicts with timestamps,
            "utterances":     merged speaker-grouped utterance dicts,
            "raw_utterances": Deepgram utterances before local merge heuristics,
            "transcript":     full plain-text string,
            "raw":            complete Deepgram response as dict,
        }

    Raises:
        RuntimeError on failure after all retries.
    """
    if model not in ALLOWED_MODELS:
        raise ValueError(
            f"Model '{model}' is not allowed. "
            f"Use one of: {sorted(ALLOWED_MODELS)}"
        )

    return _transcribe_direct(
        audio_file_path,
        model=model,
        utt_split=utt_split,
        keyterms=keyterms,
        progress_callback=progress_callback,
    )
