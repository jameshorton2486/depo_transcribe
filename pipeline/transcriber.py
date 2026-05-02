"""
pipeline/transcriber.py

Sends audio chunks to Deepgram and returns structured word/utterance data.

Supported models: nova-3, nova-3-medical

All requests use direct HTTP via httpx.
"""

import os
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

import httpx

from app_logging import get_logger
from config import (
    DEEPGRAM_CONNECTION_TIMEOUT,
    DEEPGRAM_READ_TIMEOUT,
    DEEPGRAM_WRITE_TIMEOUT,
)

logger = get_logger(__name__)

STRICT_MERGE = True
SKIP_SILENCE = False
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10
MERGE_GAP_THRESHOLD_SECONDS = 0.6
# Lowered from 3 → 1 so a single-word legitimate witness response (e.g. "Yes.")
# is not absorbed into the surrounding attorney block during merge.
MERGE_MIN_WORD_COUNT = 1
LOW_CONFIDENCE_THRESHOLD = 0.85
# Tightened from 0.5 → 0.2. True Deepgram speaker bounces are sub-200ms;
# 0.5s is long enough for a real "Yes." or "No." witness response, which
# this heuristic was wrongly erasing in depositions.
SHORT_GLITCH_MAX_DURATION_SECONDS = 0.2
SENTENCE_ENDINGS = (".", "?", "!")

# Legitimate short witness responses — depositions are full of these. If the
# middle utterance in an A→B→A pattern is one of these words, treat it as a
# real speaker turn, not a Deepgram glitch.
SHORT_ANSWER_WHITELIST = frozenset({
    "yes", "no", "yeah", "yep", "nope", "nah",
    "correct", "right", "sure", "okay", "ok",
    "true", "false",
    "uh-huh", "mm-hmm", "uh-uh", "mm-mm",
})


def _is_short_answer(utterance: dict) -> bool:
    """True if utterance text is a single canonical witness response word."""
    text = (utterance.get("transcript") or "").strip().lower()
    text = text.rstrip(".,;:?!").strip()
    return text in SHORT_ANSWER_WHITELIST

ALLOWED_MODELS = {"nova-3", "nova-3-medical"}

NEAR_SILENT_THRESHOLD_DB = -55.0
REQUEST_DEBUG_PREFIX = "DEEPGRAM PARAMS:"
REQUIRED_DEEPGRAM_FLAGS = {
    "utterances": "true",
    "diarize": "true",
    "paragraphs": "false",
    "punctuate": "true",
    "smart_format": "true",
    "numerals": "true",
    "utt_split": "0.5",
}

# Transient HTTP failures that should trigger a retry. 401/403 are excluded
# — a bad API key will never become good by retrying.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# httpx exception types that indicate transient network problems.
_RETRYABLE_HTTPX_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
)

# Shape of the return dict shared by every code path (including silence-skip)
# so downstream consumers never hit KeyError on merged_utterances/raw_utterances.
_EMPTY_RESULT: Dict[str, Any] = {
    "words": [],
    "utterances": [],
    "merged_utterances": [],
    "raw_utterances": [],
    "transcript": "",
    "raw": {},
}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _probe_max_volume_db(file_path: str) -> float | None:
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
            if "max_volume" not in line:
                continue
            try:
                return float(line.split(":")[1].strip().split()[0])
            except (IndexError, ValueError):
                continue
    except Exception as exc:
        logger.warning("volumedetect failed for %s: %s", file_path, exc)
    return None


def _is_near_silent(file_path: str, max_volume: float | None = None) -> bool:
    """
    Return True when ffmpeg volumedetect reports no speech above the threshold.
    """
    if max_volume is None:
        max_volume = _probe_max_volume_db(file_path)
    return max_volume is not None and max_volume < NEAR_SILENT_THRESHOLD_DB


def _sentence_ends(text: str) -> bool:
    stripped = (text or "").rstrip()
    return bool(stripped) and stripped.endswith(SENTENCE_ENDINGS)


def _utterance_duration(utterance: dict) -> float:
    start = _coerce_float(utterance.get("start", 0.0))
    end = _coerce_float(utterance.get("end", 0.0))
    return max(0.0, end - start)


def _is_short_glitch(prev_item: dict | None, item: dict, next_item: dict | None) -> bool:
    if not prev_item or not next_item:
        return False

    speaker = item.get("speaker")
    prev_speaker = prev_item.get("speaker")
    next_speaker = next_item.get("speaker")
    if speaker is None or prev_speaker is None or next_speaker is None:
        return False
    if prev_speaker != next_speaker or speaker == prev_speaker:
        return False
    if _utterance_duration(item) >= SHORT_GLITCH_MAX_DURATION_SECONDS:
        return False
    # Never override a real witness response. "Yes.", "No.", "Correct.",
    # etc. are legitimate speaker turns in depositions, not glitches.
    if _is_short_answer(item):
        return False

    prev_gap = _coerce_float(item.get("start", 0.0)) - _coerce_float(prev_item.get("end", 0.0))
    next_gap = _coerce_float(next_item.get("start", 0.0)) - _coerce_float(item.get("end", 0.0))
    return prev_gap <= MERGE_GAP_THRESHOLD_SECONDS and next_gap <= MERGE_GAP_THRESHOLD_SECONDS


def _annotate_confidence(utterance: dict) -> dict:
    annotated = dict(utterance)
    confidence = _coerce_float(annotated.get("confidence", 0.0))
    annotated["confidence"] = confidence
    annotated["low_confidence"] = confidence < LOW_CONFIDENCE_THRESHOLD
    return annotated


def smooth_speakers(utterances: list) -> list:
    """
    Smooth single-utterance speaker flip glitches before merge.
    """
    if len(utterances) < 3:
        return [dict(u) for u in utterances]

    smoothed = [dict(u) for u in utterances]
    for index in range(1, len(smoothed) - 1):
        current = smoothed[index]
        prev_item = smoothed[index - 1]
        next_item = smoothed[index + 1]

        current_speaker = current.get("speaker")
        prev_speaker = prev_item.get("speaker")
        next_speaker = next_item.get("speaker")
        if current_speaker is None or prev_speaker is None or next_speaker is None:
            continue
        if prev_speaker != next_speaker or current_speaker == prev_speaker:
            continue
        if _utterance_duration(current) >= SHORT_GLITCH_MAX_DURATION_SECONDS:
            continue
        # Same whitelist guard as _is_short_glitch — protect real short
        # witness responses ("Yes.", "No.") from being smoothed away.
        if _is_short_answer(current):
            continue

        prev_gap = _coerce_float(current.get("start", 0.0)) - _coerce_float(prev_item.get("end", 0.0))
        next_gap = _coerce_float(next_item.get("start", 0.0)) - _coerce_float(current.get("end", 0.0))
        if prev_gap <= MERGE_GAP_THRESHOLD_SECONDS and next_gap <= MERGE_GAP_THRESHOLD_SECONDS:
            logger.debug(
                "Smoothing speaker glitch index=%s speaker=%s -> %s text=%r",
                index,
                current_speaker,
                prev_speaker,
                current.get("transcript", ""),
            )
            current["speaker"] = prev_speaker

    return smoothed


def merge_utterances(
    raw_utterances: list,
    gap_threshold_seconds: float = MERGE_GAP_THRESHOLD_SECONDS,
    min_word_count: int = MERGE_MIN_WORD_COUNT,
) -> list:
    """
    Deterministically merge Deepgram utterances without crossing speakers.
    """
    if not raw_utterances:
        return []

    ordered = sorted(
        (_annotate_confidence(u) for u in raw_utterances),
        key=lambda u: (
            _coerce_float(u.get("start", 0.0)),
            _coerce_float(u.get("end", 0.0)),
            str(u.get("speaker")),
        ),
    )

    for index, item in enumerate(ordered):
        if _is_short_glitch(
            ordered[index - 1] if index > 0 else None,
            item,
            ordered[index + 1] if index + 1 < len(ordered) else None,
        ):
            logger.debug(
                "Ignoring short speaker-glitch utterance at index=%s speaker=%s text=%r",
                index,
                item.get("speaker"),
                item.get("transcript", ""),
            )
            item["speaker"] = ordered[index - 1]["speaker"]

    merged: list[dict] = []
    current = dict(ordered[0])
    current["words"] = list(current.get("words", []))

    for nxt in ordered[1:]:
        next_item = dict(nxt)
        next_item["words"] = list(next_item.get("words", []))

        current_speaker = current.get("speaker")
        next_speaker = next_item.get("speaker")
        current_text = (current.get("transcript") or "").strip()
        next_text = (next_item.get("transcript") or "").strip()

        if not current_text:
            current = next_item
            continue
        if not next_text:
            continue
        if (
            current_speaker is None
            or next_speaker is None
            or current_speaker != next_speaker
        ):
            merged.append(current)
            current = next_item
            continue

        gap = _coerce_float(next_item.get("start", 0.0)) - _coerce_float(current.get("end", 0.0))
        current_words = current.get("words", [])
        next_words = next_item.get("words", [])
        current_word_count = len(current_words) or len(current_text.split())
        next_word_count = len(next_words) or len(next_text.split())
        current_confidence = _coerce_float(current.get("confidence", 0.0))
        next_confidence = _coerce_float(next_item.get("confidence", 0.0))

        if current_text == next_text:
            logger.debug(
                "Skipping duplicate utterance speaker=%s text=%r",
                current_speaker,
                next_text,
            )
            continue

        if gap > gap_threshold_seconds:
            merged.append(current)
            current = next_item
            continue

        if STRICT_MERGE:
            if current_confidence < LOW_CONFIDENCE_THRESHOLD or next_confidence < LOW_CONFIDENCE_THRESHOLD:
                merged.append(current)
                current = next_item
                continue
            if _sentence_ends(current_text):
                merged.append(current)
                current = next_item
                continue

        if current_word_count < min_word_count or next_word_count < min_word_count:
            if gap >= 0.6:
                merged.append(current)
                current = next_item
                continue

        combined_text = f"{current_text.rstrip()} {next_text.lstrip()}".strip()
        combined_words = current_words + next_words
        current = {
            **current,
            **next_item,
            "start": current.get("start", 0.0),
            "end": next_item.get("end", current.get("end", 0.0)),
            "transcript": combined_text,
            "words": combined_words,
            "confidence": min(current_confidence, next_confidence) if combined_words else min(current_confidence, next_confidence),
            "low_confidence": min(current_confidence, next_confidence) < LOW_CONFIDENCE_THRESHOLD,
        }

    merged.append(current)
    return merged


def _write_debug_snapshots(audio_file_path: str, raw_utterances: list, merged_utterances: list) -> None:
    try:
        chunk_path = Path(audio_file_path)
        raw_path = chunk_path.with_name(f"{chunk_path.stem}_raw_utterances.json")
        merged_path = chunk_path.with_name(f"{chunk_path.stem}_merged_utterances.json")

        payload = {
            "chunk": chunk_path.name,
            "raw_utterances": raw_utterances,
        }
        raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        payload = {
            "chunk": chunk_path.name,
            "merged_utterances": merged_utterances,
        }
        merged_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to write utterance debug snapshots for %s: %s", audio_file_path, exc)


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


def _is_retryable_error(exc: Exception, status_code: int | None = None) -> bool:
    """
    Decide whether a failed Deepgram call warrants a retry.

    Retries: httpx timeout/network/protocol/connect errors, and HTTP
    429/5xx responses (server-side transients).
    Does not retry: 401/403 (auth — never recovers) or ValueError raised
    by this module (programming/data error — never recovers).
    """
    if status_code is not None:
        if status_code in {401, 403}:
            return False
        if status_code in _RETRYABLE_STATUS_CODES:
            return True

    if isinstance(exc, _RETRYABLE_HTTPX_ERRORS):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES

    if isinstance(exc, ValueError):
        return False

    # Unknown exception — retry conservatively so a transient issue is not
    # reported as a hard failure on attempt 1.
    return True


def _transcribe_direct(
    audio_file_path: str,
    model: str = "nova-3",
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

    # Deepgram request defaults:
    # - filler_words stays off to match Playground transcript defaults
    # - utterances=True is required — correction_runner checks for this key
    # - utt_split controls silence length before Deepgram starts a new utterance
    #   and is intentionally tighter for deposition Q/A turn boundaries
    # - preserve the current return contract; expose extra debug context without
    #   changing downstream behavior
    normalized_keyterms = [
        str(term).strip() for term in (keyterms or []) if str(term).strip()
    ]

    params = normalize_params({
        "model":        model,
        "language":     "en",
        "smart_format": True,
        "diarize":      True,
        "punctuate":    True,
        "paragraphs":   False,
        "utterances":   True,
        "utt_split":    "0.8",
        "filler_words": False,
        "numerals":     True,
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
    logger.info("Processing chunk: %s", chunk_name)

    if progress_callback:
        progress_callback(f"Sending to Deepgram: {chunk_name}")

    with open(audio_file_path, "rb") as f:
        buffer = f.read()

    max_volume = _probe_max_volume_db(audio_file_path)
    logger.info("Chunk volume: %s dB", "unknown" if max_volume is None else f"{max_volume:.2f}")
    if _is_near_silent(audio_file_path, max_volume=max_volume):
        logger.warning(
            "Near-silent chunk detected — processing anyway (safe mode). chunk=%s threshold=%.0fdB",
            chunk_name,
            NEAR_SILENT_THRESHOLD_DB,
        )
        if SKIP_SILENCE:
            logger.info("Chunk included: NO (skip-silence mode enabled)")
            if progress_callback:
                progress_callback(f"Skipped silent chunk: {chunk_name} (safe skip mode)")
            return dict(_EMPTY_RESULT)
        logger.info("Chunk included: YES")
    else:
        logger.info("Chunk included: YES")

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.time()
        try:
            timeout = httpx.Timeout(
                connect=DEEPGRAM_CONNECTION_TIMEOUT,
                read=DEEPGRAM_READ_TIMEOUT,
                write=DEEPGRAM_WRITE_TIMEOUT,
                pool=None,
            )
            resp = httpx.post(
                url,
                content=buffer,
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type":  "audio/*",
                },
                timeout=timeout,
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

            channels = results.get("channels")
            if not channels or not isinstance(channels, list):
                raise RuntimeError(
                    f"Deepgram response missing 'channels'. "
                    f"chunk={chunk_name}  keys={list(results.keys())}"
                )
            alternatives = channels[0].get("alternatives")
            if not alternatives or not isinstance(alternatives, list):
                raise RuntimeError(
                    f"Deepgram response missing 'alternatives' in channel[0]. "
                    f"chunk={chunk_name}"
                )
            alt = alternatives[0]
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
            raw_utterances = [_annotate_confidence(u) for u in raw_utterances]
            raw_utterances = smooth_speakers(raw_utterances)
            utterances = merge_utterances(
                raw_utterances,
                gap_threshold_seconds=MERGE_GAP_THRESHOLD_SECONDS,
                min_word_count=MERGE_MIN_WORD_COUNT,
            )
            utterances = [_annotate_confidence(u) for u in utterances]

            if not utterances:
                raise ValueError("No utterances returned — pipeline failure")

            logger.debug("RAW UTTERANCES COUNT: %s", len(raw_utterances))
            logger.debug("MERGED UTTERANCES COUNT: %s", len(utterances))
            for i in range(min(5, len(raw_utterances))):
                logger.debug("RAW %s: %s", i, raw_utterances[i]["transcript"])
            for i in range(min(5, len(utterances))):
                logger.debug("MERGED %s: %s", i, utterances[i]["transcript"])

            _write_debug_snapshots(audio_file_path, raw_utterances, utterances)

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
                "merged_utterances": utterances,
                "raw_utterances":   raw_utterances,
                "transcript":       alt.get("transcript", ""),
                "raw":              raw,
            }

        except Exception as exc:
            last_exc = exc
            elapsed = time.time() - t0
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(exc, httpx.WriteTimeout):
                size_mb = len(buffer) / (1024 * 1024)
                remaining_attempts = MAX_RETRIES - attempt
                logger.warning(
                    "Deepgram WriteTimeout on chunk %s (%.1f MB) - attempt %d/%d, remaining=%d, write_timeout=%ds, retrying in %ds",
                    chunk_name,
                    size_mb,
                    attempt,
                    MAX_RETRIES,
                    remaining_attempts,
                    DEEPGRAM_WRITE_TIMEOUT,
                    RETRY_DELAY_SECONDS,
                )
            logger.error(
                "Direct attempt %s/%s FAILED chunk=%s elapsed=%.2fs "
                "status=%s error=%s",
                attempt, MAX_RETRIES, chunk_name, elapsed, status, exc,
            )
            if attempt < MAX_RETRIES and _is_retryable_error(exc, status):
                if progress_callback:
                    progress_callback(
                        f"Deepgram error ({type(exc).__name__}) - "
                        f"retrying in {RETRY_DELAY_SECONDS}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            break

    raise RuntimeError(
        f"Deepgram transcription failed after {MAX_RETRIES} attempts: {last_exc}"
    )


def transcribe_chunk(
    audio_file_path: str,
    model: str = "nova-3",
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
        keyterms=keyterms,
        progress_callback=progress_callback,
    )
