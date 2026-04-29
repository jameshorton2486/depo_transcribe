"""Anthropic-backed transcript cleanup for clean-format output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import AI_MODEL
from config import ANTHROPIC_API_KEY
from clean_format.prompt import CLEAN_FORMAT_SYSTEM_PROMPT

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - exercised only when dependency missing
    Anthropic = None  # type: ignore[assignment]

CHUNK_CHAR_LIMIT = 80_000
MAX_TOKENS = 8192


def _normalize_whitespace(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _speaker_blocks(raw_text: str) -> list[str]:
    blocks = [block.strip() for block in (raw_text or "").split("\n\n")]
    return [block for block in blocks if block]


def split_transcript(raw_text: str, max_chunk_chars: int = CHUNK_CHAR_LIMIT) -> list[str]:
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
    ]
    return {key: case_meta.get(key) for key in ordered_keys if case_meta.get(key) not in (None, "", [], {})}


def build_user_message(chunk: str, case_meta: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
    meta_json = json.dumps(_case_meta_for_prompt(case_meta), indent=2, ensure_ascii=False)
    return (
        f"Case metadata:\n{meta_json}\n\n"
        f"Transcript chunk {chunk_index} of {chunk_count}:\n"
        f"{chunk}\n"
    )


def _response_text(response: Any) -> str:
    parts = []
    for item in getattr(response, "content", []) or []:
        text = getattr(item, "text", "")
        if text:
            parts.append(text)
    output = "\n".join(parts).strip()
    if not output:
        raise RuntimeError("Anthropic response did not include text content")
    return output


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
) -> str:
    """Format a raw Deepgram transcript into clean-format text."""
    chunks = split_transcript(raw_text, max_chunk_chars=max_chunk_chars)
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
        rendered_chunks.append(_response_text(response))

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
    for role_key, role_name in (("plaintiff_counsel", "plaintiff"), ("defense_counsel", "defendant")):
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
    defendant_name = _normalize_whitespace(str(ufm_fields.get("defendant_name", "") or ""))

    return {
        "cause_number": _normalize_whitespace(str(ufm_fields.get("cause_number", "") or "")),
        "court": _normalize_whitespace(
            str(ufm_fields.get("court_caption") or ufm_fields.get("court_type") or "")
        ),
        "county": _normalize_whitespace(str(ufm_fields.get("county", "") or "")),
        "judicial_district": _normalize_whitespace(str(ufm_fields.get("judicial_district", "") or "")),
        "deposition_date": _normalize_whitespace(str(ufm_fields.get("depo_date", "") or "")),
        "start_time": _normalize_whitespace(str(ufm_fields.get("depo_time_start", "") or "")),
        "end_time": _normalize_whitespace(str(ufm_fields.get("depo_time_end", "") or "")),
        "witness_name": witness_core or witness_name,
        "witness_credentials": witness_credentials.strip(),
        "plaintiff_name": _normalize_whitespace(str(ufm_fields.get("plaintiff_name", "") or "")),
        "defendant_names": [defendant_name] if defendant_name else [],
        "reporter_name": _normalize_whitespace(str(ufm_fields.get("reporter_name", "") or "")),
        "reporter_csr": _normalize_whitespace(
            str(ufm_fields.get("reporter_csr") or ufm_fields.get("csr_number") or "")
        ),
        "attorneys": _attorneys_from_ufm(ufm_fields),
        "videographer_name": _normalize_whitespace(str(ufm_fields.get("videographer_name", "") or "")),
    }


def load_case_meta(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
