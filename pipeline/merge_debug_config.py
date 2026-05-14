"""Investigation-only override for the local utterance-merge gap values.

Production defaults live in ``pipeline.transcriber.MERGE_GAP_THRESHOLD_SECONDS``
(per-chunk merge) and ``pipeline.assembler.GAP_THRESHOLD_SECONDS``
(cross-chunk merge). This module lets a controlled experiment vary
those values **without** editing the production constants.

Default state: every helper returns ``None``, meaning "use the
existing production constant." Callers are written so a ``None``
return path keeps the original behavior. There is no way for this
module to make production behave differently unless one of the
two opt-in mechanisms below is exercised.

Two opt-in mechanisms:

1. **Environment variables** (intended for one-off command-line use):

   - ``DEPO_TRANSCRIBE_MERGE_IN_CHUNK_GAP``  — float, e.g. ``0.6``
   - ``DEPO_TRANSCRIBE_MERGE_CROSS_CHUNK_GAP`` — float, e.g. ``0.9``
   - ``DEPO_TRANSCRIBE_MERGE_DEBUG_LOG`` — truthy value enables
     extra debug log lines in the merge path

2. **Programmatic context** (intended for the experiment runner):

   ``set_overrides(in_chunk_gap=0.4, cross_chunk_gap=0.5)`` /
   ``clear_overrides()``. Programmatic overrides take precedence
   over environment variables. The experiment runner sets them
   before invoking merge logic and clears them at the end of each
   experiment.

This is a debugging utility. It is intentionally narrow:

- It does NOT define a configuration architecture.
- It does NOT validate values beyond a basic float-coercion.
- It does NOT persist anything.
- It is NOT imported by any UI / job-runner / CLI in production code.

CLAUDE.md note: this stays inside ``pipeline/`` because the merge
gaps it overrides live in ``pipeline/``. It does not import from
``clean_format/`` or ``spec_engine/``.
"""
from __future__ import annotations

import os
import threading
from typing import Optional

_ENV_IN_CHUNK = "DEPO_TRANSCRIBE_MERGE_IN_CHUNK_GAP"
_ENV_CROSS_CHUNK = "DEPO_TRANSCRIBE_MERGE_CROSS_CHUNK_GAP"
_ENV_DEBUG_LOG = "DEPO_TRANSCRIBE_MERGE_DEBUG_LOG"

# Programmatic overrides — wins over env-vars when set. ``None`` means
# "no programmatic override is in effect; fall through to env-var or
# production default."
_lock = threading.Lock()
_overrides: dict[str, Optional[float]] = {
    "in_chunk_gap": None,
    "cross_chunk_gap": None,
}


def _coerce_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def set_overrides(
    *,
    in_chunk_gap: Optional[float] = None,
    cross_chunk_gap: Optional[float] = None,
) -> None:
    """Install programmatic overrides for the merge gap values.

    Pass ``None`` to leave a particular field unchanged. To clear
    everything, call :func:`clear_overrides` instead.
    """
    with _lock:
        if in_chunk_gap is not None:
            _overrides["in_chunk_gap"] = float(in_chunk_gap)
        if cross_chunk_gap is not None:
            _overrides["cross_chunk_gap"] = float(cross_chunk_gap)


def clear_overrides() -> None:
    """Reset programmatic overrides back to default (no override)."""
    with _lock:
        _overrides["in_chunk_gap"] = None
        _overrides["cross_chunk_gap"] = None


def get_in_chunk_gap_override() -> Optional[float]:
    """Return the per-chunk merge gap override, or ``None`` if unset."""
    with _lock:
        value = _overrides["in_chunk_gap"]
    if value is not None:
        return value
    return _coerce_float(os.environ.get(_ENV_IN_CHUNK))


def get_cross_chunk_gap_override() -> Optional[float]:
    """Return the cross-chunk merge gap override, or ``None`` if unset."""
    with _lock:
        value = _overrides["cross_chunk_gap"]
    if value is not None:
        return value
    return _coerce_float(os.environ.get(_ENV_CROSS_CHUNK))


def debug_log_enabled() -> bool:
    """Return True when the optional `[MERGE_DEBUG]` log lines should fire."""
    raw = os.environ.get(_ENV_DEBUG_LOG, "")
    return bool(raw and raw.strip().lower() not in {"0", "false", "no", ""})
