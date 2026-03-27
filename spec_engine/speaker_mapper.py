"""
Speaker identity mapping and persistence for block-based processing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import Block
from .speaker_resolver import resolve_speaker


def _job_key(job_config: Any) -> str:
    if hasattr(job_config, "cause_number"):
        cause = (getattr(job_config, "cause_number", "") or "").strip()
        style = (getattr(job_config, "case_style", "") or "").strip()
    elif isinstance(job_config, dict):
        cause = (job_config.get("cause_number", "") or "").strip()
        style = (job_config.get("case_style", "") or "").strip()
    else:
        cause = ""
        style = ""
    return cause or style


def _speaker_map_from_job(job_config: Any) -> Dict[str, str]:
    if hasattr(job_config, "speaker_map"):
        return {str(k): v for k, v in getattr(job_config, "speaker_map", {}).items()}
    if isinstance(job_config, dict):
        return {str(k): v for k, v in (job_config.get("speaker_map", {}) or {}).items()}
    return {}


def _persisted_map_path() -> Path:
    path = Path("work_files") / "speaker_map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_persisted_maps() -> Dict[str, Dict[str, str]]:
    path = _persisted_map_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_persisted_maps(data: Dict[str, Dict[str, str]]) -> None:
    _persisted_map_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def map_speakers(blocks: List[Block], job_config: Any) -> List[Block]:
    """
    Apply speaker names from the current job config and persist them by job key.
    """
    persisted = _load_persisted_maps()
    key = _job_key(job_config)
    speaker_map = _speaker_map_from_job(job_config)

    merged = dict(persisted.get(key, {})) if key else {}
    merged.update(speaker_map)
    if key and merged:
        persisted[key] = merged
        _save_persisted_maps(persisted)

    for block in blocks:
        if block.speaker_id is None:
            continue
        _, speaker_role, speaker_name = resolve_speaker(block.speaker_id, {"speaker_map": merged})
        block.speaker_role = speaker_role
        block.speaker_name = speaker_name

    return blocks
