from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic

from core.config import AI_MODEL

from .prompt import SYSTEM_PROMPT

MAX_CHARS = 80_000
MAX_TOKENS = 8192


def _split_blocks(raw_text: str, max_chars: int = MAX_CHARS) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw_text.strip()) if b.strip()]
    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block
    if current:
        chunks.append(current)
    return chunks or [raw_text]


def _build_user_message(raw_chunk: str, case_meta: dict[str, Any], chunk_index: int, total_chunks: int) -> str:
    return (
        f"Case metadata:\n{json.dumps(case_meta, indent=2, sort_keys=True)}\n\n"
        f"Transcript chunk {chunk_index}/{total_chunks}:\n{raw_chunk}\n"
    )


def format_transcript(raw_text: str, case_meta: dict[str, Any], client: Anthropic | None = None) -> str:
    api = client or Anthropic()
    chunks = _split_blocks(raw_text)
    outputs: list[str] = []
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        message = _build_user_message(chunk, case_meta, idx, total)
        response = api.messages.create(
            model=AI_MODEL or "claude-sonnet-4-5",
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
        )
        text = "".join(part.text for part in response.content if getattr(part, "type", "") == "text").strip()
        if text:
            outputs.append(text)
    return "\n\n".join(outputs).strip()
