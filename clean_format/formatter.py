"""Anthropic-backed transcript cleanup for clean-format output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.config import AI_MODEL
from config import ANTHROPIC_API_KEY, LOW_CONFIDENCE_THRESHOLD
from clean_format.prompt import CLEAN_FORMAT_SYSTEM_PROMPT
from clean_format.low_confidence_markers import (
    inject_markers,
    validate_marker_round_trip,
)

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - exercised only when dependency missing
    Anthropic = None  # type: ignore[assignment]

CHUNK_CHAR_LIMIT = 80_000
MAX_TOKENS = 8192
_SENTENCE_DOUBLE_SPACE_RE = re.compile(r"([.?])\s+(?=\S)")
_LEADING_ZERO_TIME_RE = re.compile(r"\b0([1-9]):(\d{2}\s*[ap]\.m\.)", re.IGNORECASE)
_DOCTOR_NAME_RE = re.compile(r"\bDoctor\s+(?=[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)")
_MISS_NAME_RE = re.compile(r"\bMiss Kuipers\b")
_EM_DASH_RE = re.compile(r"\s*[—–]\s*")
_SPACED_DOUBLE_HYPHEN_RE = re.compile(r"\s*--\s*")
_LABEL_LINE_RE = re.compile(r"^(?P<label>[A-Z][A-Z .'-]+):\t(?P<text>.*)$")
_RAW_SPEAKER_LINE_RE = re.compile(r"^Speaker\s+\d+:\s*(?P<text>.*)$", re.IGNORECASE)
_DUNNELL_RE = re.compile(
    r"^((THE\s+)?VIDEOGRAPHER):\t(?P<text>Billy Dunnell here on behalf of .*)$",
    re.IGNORECASE,
)


def _normalize_whitespace(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _speaker_blocks(raw_text: str) -> list[str]:
    blocks = [block.strip() for block in (raw_text or "").split("\n\n")]
    return [block for block in blocks if block]


def split_transcript(
    raw_text: str, max_chunk_chars: int = CHUNK_CHAR_LIMIT
) -> list[str]:
    """Split raw speaker blocks into chunks near the requested character limit."""
    blocks = _speaker_blocks(raw_text)
    if not blocks:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for block in blocks:
        block_size = len(block) + 2
        if current and current_size + block_size > max_chunk_chars:
            chunks.append("\n\n".join(current))
            current = [block]
            current_size = block_size
            continue

        if not current and block_size > max_chunk_chars:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            running: list[str] = []
            running_size = 0
            for line in lines:
                line_size = len(line) + 1
                if running and running_size + line_size > max_chunk_chars:
                    chunks.append("\n".join(running))
                    running = [line]
                    running_size = line_size
                else:
                    running.append(line)
                    running_size += line_size
            if running:
                chunks.append("\n".join(running))
            current = []
            current_size = 0
            continue

        current.append(block)
        current_size += block_size

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _case_meta_for_prompt(case_meta: dict[str, Any]) -> dict[str, Any]:
    ordered_keys = [
        "cause_number",
        "court",
        "county",
        "judicial_district",
        "deposition_date",
        "start_time",
        "end_time",
        "witness_name",
        "witness_credentials",
        "plaintiff_name",
        "defendant_names",
        "reporter_name",
        "reporter_csr",
        "attorneys",
        "videographer_name",
        # Phase 2: NOD-derived authoritative data. confirmed_spellings is
        # a wrong->right dict the model applies as proper-noun corrections.
        # deepgram_keyterms is the list of NOD entities given to Deepgram
        # as keyterms; surfacing it to the model lets it preserve those
        # spellings as canonical. Both fields are passed through from
        # job_config.json by ui/tab_transcribe.py::_run_clean_format_job.
        "confirmed_spellings",
        "deepgram_keyterms",
    ]
    return {
        key: case_meta.get(key)
        for key in ordered_keys
        if case_meta.get(key) not in (None, "", [], {})
    }


def build_user_message(
    chunk: str, case_meta: dict[str, Any], chunk_index: int, chunk_count: int
) -> str:
    meta_json = json.dumps(
        _case_meta_for_prompt(case_meta), indent=2, ensure_ascii=False
    )
    return (
        f"Case metadata:\n{meta_json}\n\n"
        f"Transcript chunk {chunk_index} of {chunk_count}:\n"
        f"{chunk}\n"
    )


def _response_text(response: Any) -> tuple[str, str | None]:
    parts = []
    for item in getattr(response, "content", []) or []:
        text = getattr(item, "text", "")
        if text:
            parts.append(text)
    output = "\n".join(parts).strip()
    stop_reason = getattr(response, "stop_reason", None)
    if not output:
        raise RuntimeError("Anthropic response did not include text content")
    return output, stop_reason


def _normalize_body_text(text: str) -> str:
    text = _DOCTOR_NAME_RE.sub("Dr. ", text)
    text = _MISS_NAME_RE.sub("Ms. Kuipers", text)
    text = _LEADING_ZERO_TIME_RE.sub(r"\1:\2", text)
    text = _EM_DASH_RE.sub(" -- ", text)
    text = _SPACED_DOUBLE_HYPHEN_RE.sub(" -- ", text)
    for short_title, token in {
        "Dr. ": "__TITLE_DR__",
        "Mr. ": "__TITLE_MR__",
        "Ms. ": "__TITLE_MS__",
        "Mrs. ": "__TITLE_MRS__",
    }.items():
        text = text.replace(short_title, token)
    text = _SENTENCE_DOUBLE_SPACE_RE.sub(r"\1  ", text)
    for token, short_title in {
        "__TITLE_DR__": "Dr. ",
        "__TITLE_MR__": "Mr. ",
        "__TITLE_MS__": "Ms. ",
        "__TITLE_MRS__": "Mrs. ",
    }.items():
        text = text.replace(token, short_title)
    return text


def _postprocess_formatted_text(formatted_text: str) -> str:
    lines: list[str] = []
    for raw_line in (formatted_text or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            lines.append("")
            continue

        dunnell_match = _DUNNELL_RE.match(line)
        if dunnell_match:
            lines.append(
                f"MR. DUNNELL:\t{_normalize_body_text(dunnell_match.group('text'))}"
            )
            continue

        if line.startswith("COURT REPORTER:\t") or line.startswith("THE COURT REPORTER:\t"):
            prefix = "COURT REPORTER:\t" if line.startswith("COURT REPORTER:\t") else "THE COURT REPORTER:\t"
            lines.append(
                "THE REPORTER:\t"
                + _normalize_body_text(line[len(prefix) :])
            )
            continue

        if line.startswith("VIDEOGRAPHER:\t") or line.startswith("THE VIDEOGRAPHER:\t"):
            prefix = "VIDEOGRAPHER:\t" if line.startswith("VIDEOGRAPHER:\t") else "THE VIDEOGRAPHER:\t"
            lines.append(
                "THE VIDEOGRAPHER:\t"
                + _normalize_body_text(line[len(prefix) :])
            )
            continue

        if line in {"COURT REPORTER:", "THE COURT REPORTER:"}:
            lines.append("THE REPORTER:")
            continue

        if line in {"VIDEOGRAPHER:", "THE VIDEOGRAPHER:"}:
            lines.append("THE VIDEOGRAPHER:")
            continue

        if line.startswith("Q.\t"):
            lines.append("Q.\t" + _normalize_body_text(line[3:]))
            continue

        if line.startswith("A.\t"):
            lines.append("A.\t" + _normalize_body_text(line[3:]))
            continue

        label_match = _LABEL_LINE_RE.match(line)
        if label_match:
            label = label_match.group("label").strip()
            text = _normalize_body_text(label_match.group("text"))
            lines.append(f"{label}:\t{text}")
            continue

        lines.append(_normalize_body_text(line))

    return "\n".join(lines).strip()


def _token_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def _verbatim_fallback_for_chunk(chunk: str) -> str:
    """Lossless fallback when model output drops too much content.

    Keeps all words from the raw chunk and only applies body-text normalization
    on each speaker line's body.
    """
    lines: list[str] = []
    for raw_line in (chunk or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            lines.append("")
            continue
        match = _RAW_SPEAKER_LINE_RE.match(line)
        if not match:
            lines.append(_normalize_body_text(line))
            continue
        body = match.group("text")
        lines.append(f"{line[:match.start('text')]}{_normalize_body_text(body)}")
    return "\n".join(lines).strip()


def _build_client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    if Anthropic is None:
        raise RuntimeError("anthropic package is not installed")
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=ANTHROPIC_API_KEY)


def format_transcript(
    raw_text: str,
    case_meta: dict[str, Any],
    *,
    client: Any | None = None,
    model: str | None = None,
    max_chunk_chars: int = CHUNK_CHAR_LIMIT,
    deepgram_words: list[dict[str, Any]] | None = None,
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> str:
    """Format a raw Deepgram transcript into clean-format text.

    Step C: when ``deepgram_words`` is provided, tokens with confidence
    below ``low_confidence_threshold`` are wrapped with ``‹LC:...›``
    markers prior to the Anthropic cleanup pass. The system prompt
    instructs the model to preserve those markers verbatim. Step D's
    DOCX writer reads the markers to render yellow highlights.

    When ``deepgram_words`` is None (default), behavior is unchanged.
    """
    marked_text = (
        inject_markers(
            raw_text, deepgram_words, threshold=low_confidence_threshold
        )
        if deepgram_words
        else raw_text
    )
    chunks = split_transcript(marked_text, max_chunk_chars=max_chunk_chars)
    if not chunks:
        return ""

    api_client = _build_client(client)
    rendered_chunks: list[str] = []
    selected_model = model or AI_MODEL

    for index, chunk in enumerate(chunks, start=1):
        response = api_client.messages.create(
            model=selected_model,
            max_tokens=MAX_TOKENS,
            system=CLEAN_FORMAT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_user_message(chunk, case_meta, index, len(chunks)),
                }
            ],
        )
        response_text, stop_reason = _response_text(response)
        if stop_reason == "max_tokens":
            rendered_chunks.append(_verbatim_fallback_for_chunk(chunk))
            continue
        if deepgram_words:
            validate_marker_round_trip(chunk, response_text)
        source_tokens = _token_count(chunk)
        response_tokens = _token_count(response_text)
        if source_tokens >= 80 and response_tokens < int(source_tokens * 0.7):
            rendered_chunks.append(_verbatim_fallback_for_chunk(chunk))
            continue
        rendered_chunks.append(_postprocess_formatted_text(response_text))

    return "\n\n".join(part for part in rendered_chunks if part.strip()).strip()


def _extract_city(attorney: dict[str, Any]) -> str:
    for key in ("city", "city_state_zip", "address"):
        value = _normalize_whitespace(str(attorney.get(key, "") or ""))
        if value:
            if "," in value:
                return value.split(",")[0].strip()
            return value
    return ""


def _attorneys_from_ufm(ufm_fields: dict[str, Any]) -> list[dict[str, str]]:
    attorneys: list[dict[str, str]] = []
    for role_key, role_name in (
        ("plaintiff_counsel", "plaintiff"),
        ("defense_counsel", "defendant"),
    ):
        for entry in ufm_fields.get(role_key, []) or []:
            name = _normalize_whitespace(str(entry.get("name", "") or ""))
            if not name:
                continue
            attorneys.append(
                {
                    "name": name,
                    "role": role_name,
                    "city": _extract_city(entry),
                }
            )
    return attorneys


def build_case_meta_from_ufm(ufm_fields: dict[str, Any]) -> dict[str, Any]:
    """Project existing job-config UFM data into the clean-format case metadata shape."""
    witness_name = _normalize_whitespace(str(ufm_fields.get("witness_name", "") or ""))
    witness_core, _, witness_credentials = witness_name.partition(",")
    defendant_name = _normalize_whitespace(
        str(ufm_fields.get("defendant_name", "") or "")
    )

    return {
        "cause_number": _normalize_whitespace(
            str(ufm_fields.get("cause_number", "") or "")
        ),
        "court": _normalize_whitespace(
            str(ufm_fields.get("court_caption") or ufm_fields.get("court_type") or "")
        ),
        "county": _normalize_whitespace(str(ufm_fields.get("county", "") or "")),
        "judicial_district": _normalize_whitespace(
            str(ufm_fields.get("judicial_district", "") or "")
        ),
        "deposition_date": _normalize_whitespace(
            str(ufm_fields.get("depo_date", "") or "")
        ),
        "start_time": _normalize_whitespace(
            str(ufm_fields.get("depo_time_start", "") or "")
        ),
        "end_time": _normalize_whitespace(
            str(ufm_fields.get("depo_time_end", "") or "")
        ),
        "witness_name": witness_core or witness_name,
        "witness_credentials": witness_credentials.strip(),
        "plaintiff_name": _normalize_whitespace(
            str(ufm_fields.get("plaintiff_name", "") or "")
        ),
        "defendant_names": [defendant_name] if defendant_name else [],
        "reporter_name": _normalize_whitespace(
            str(ufm_fields.get("reporter_name", "") or "")
        ),
        "reporter_csr": _normalize_whitespace(
            str(ufm_fields.get("reporter_csr") or ufm_fields.get("csr_number") or "")
        ),
        "attorneys": _attorneys_from_ufm(ufm_fields),
        "videographer_name": _normalize_whitespace(
            str(ufm_fields.get("videographer_name", "") or "")
        ),
        # Phase 2 placeholders. The Start-Transcription job populates
        # these from job_config.json (top-level keys, not nested in
        # ufm_fields) at the _run_clean_format_job call site. Default
        # empty so existing callers and tests still work.
        "confirmed_spellings": {},
        "deepgram_keyterms": [],
    }


def load_case_meta(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_deepgram_words_from_json(
    path: str | Path,
) -> list[dict[str, Any]] | None:
    """Load the Deepgram word array from a raw_deepgram.json file.

    Returns the ``words`` list when present and non-empty; ``None`` in
    every degraded case (file missing, JSON malformed, no ``words``
    key, empty list). Never raises — callers can pass the result
    directly to ``format_transcript(..., deepgram_words=...)`` and the
    yellow-highlight pipeline degrades to "no markers" gracefully.

    The schema expected matches what ``core/job_runner.py`` writes to
    ``{case_dir}/Deepgram/raw_deepgram.json``: a dict with a top-level
    ``"words"`` key holding a list of Deepgram word dicts.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    words = data.get("words")
    if not isinstance(words, list) or not words:
        return None
    return words
