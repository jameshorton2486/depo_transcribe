"""
Versioned prompt pack loading for AI correction.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptPack:
    id: str
    model: str
    temperature: float
    max_tokens: int
    system_prompt: str
    user_prompt_template: str
    invariants: dict[str, Any]


def _prompt_pack_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts" / "transcript_correction"


def get_prompt_pack_path(pack_id: str) -> Path:
    return _prompt_pack_dir() / f"{pack_id}.json"


def load_prompt_pack(pack_id: str | None = None) -> PromptPack:
    resolved_id = (
        (pack_id or "").strip()
        or os.environ.get("AI_CORRECTION_PROMPT_PACK", "").strip()
        or "legal_transcript_v1"
    )
    path = get_prompt_pack_path(resolved_id)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    return PromptPack(
        id=str(data["id"]).strip(),
        model=str(data["model"]).strip(),
        temperature=float(data.get("temperature", 0.1)),
        max_tokens=int(data.get("max_tokens", 5500)),
        system_prompt=str(data["system_prompt"]).strip(),
        user_prompt_template=str(data["user_prompt_template"]),
        invariants=dict(data.get("invariants", {})),
    )
