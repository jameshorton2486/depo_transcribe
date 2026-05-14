"""Immutable raw-Deepgram-response store.

Phase A of the architectural stabilization plan
(``docs/plans/RAW_IMMUTABILITY_AND_PLAYGROUND_MODE_PLAN.md``). Writes
the **unmutated** per-chunk Deepgram response bodies plus full
provenance metadata into a timestamped, read-only JSON file
colocated with the case data::

    <case_dir>/Deepgram/raw_dg_response_<stamp>.json

Design contract
---------------
- **Write-once.** The file path embeds a second-resolution timestamp.
  ``save_raw_response`` refuses to overwrite if the target path
  already exists (defense-in-depth on top of the unique timestamp).
- **Read-only on disk.** After the write succeeds, the file's mode
  is set to ``0o444`` so a process inside the same Python runtime
  cannot accidentally re-open the file for writing without an
  explicit ``os.chmod`` first.
- **No transformation.** What gets saved is exactly the dict
  ``transcribe_chunk`` returned in ``result["raw"]`` (the parsed
  HTTP response body), plus a small wrapping with audio-source +
  chunk-offset metadata, the Deepgram request parameters actually
  sent, and the post-sanitization keyterm list actually transmitted.
- **No downstream consumer yet.** This file exists to be the
  forensic source-of-truth that later phases regression-compare
  against. The existing ``Deepgram/raw_deepgram.{txt,json}`` writes
  in ``core/job_runner.py`` are NOT removed.
- **Errors propagate, callers decide.** This module's functions
  raise ``ValueError``/``FileExistsError``/``OSError`` on data or
  filesystem problems. The caller (``core/job_runner.py``) decides
  whether the run aborts or continues. Silent failure at the
  *module* level is unacceptable; a policy choice at the
  *orchestration* level is appropriate.

The plan calls out that today's ``raw_deepgram.json["chunks"]``
field already contains the same per-chunk bodies — but that file is
overwritten on every re-run of the same case. This module's output
is never overwritten, so a forensic comparison against any prior
run remains possible.

Schema versions
---------------
- ``1`` — initial layout (audio_file, model, request_params, chunks).
- ``2`` — added top-level ``keyterms_sent`` field carrying the
  post-sanitization keyterm list actually transmitted to Deepgram.
  Readers should branch on ``schema_version`` rather than assuming
  a fixed shape.
"""
from __future__ import annotations

import json
import logging
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# File-name prefix used by ``save_raw_response``. Tools that look up
# saved raw responses key off this prefix.
RAW_RESPONSE_FILENAME_PREFIX = "raw_dg_response_"

# Subdirectory of the case folder where saved raw responses live.
# Same parent as ``raw_deepgram.json`` so a future tool that walks
# the Deepgram/ folder will find both.
RAW_STORE_SUBDIR = "Deepgram"

# Bump whenever the on-disk JSON layout changes. Readers should
# branch on this value rather than assuming a fixed shape.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class RawResponseSaveResult:
    """Returned by ``save_raw_response``."""

    path: Path
    chunk_count: int
    timestamp: str


def _build_timestamp() -> str:
    """Second-resolution local-time timestamp for the filename.

    Local time (not UTC) is used deliberately to match the existing
    ``Deepgram/<base>_<stamp>.json`` convention in
    ``core/job_runner.py``. Files created at the same point in time
    therefore share the same stamp, which makes co-located forensic
    artifacts easy to correlate by filename.
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _set_read_only(path: Path) -> None:
    """Set the file to read-only.

    On Windows ``os.chmod`` flips the read-only attribute. On POSIX
    systems it sets the permission bits. Both behaviors are sufficient
    to prevent the same Python process from silently overwriting the
    file without an explicit ``chmod`` first.
    """
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError as exc:
        # Some filesystems (e.g. SMB shares on Windows) refuse the
        # permission change. We log the failure but do not propagate —
        # the legal-record value here is *the saved JSON content*, not
        # the OS-level read-only attribute. Without the attribute, the
        # file is still a write-once timestamped artifact; the worst
        # case is that a later run could overwrite it, which our
        # collision check above already prevents.
        logger.warning(
            "[RAW_STORE] could not set read-only on %s: %s", path, exc
        )


def save_raw_response(
        case_dir: str | Path,
        chunk_results: list[dict[str, Any]],
        chunk_offsets: list[float],
        *,
        audio_file: str | None = None,
        model: str | None = None,
        request_params: dict[str, Any] | None = None,
        keyterms: list[str] | None = None,
        timestamp: str | None = None,
) -> RawResponseSaveResult:
    """Write the unmutated per-chunk Deepgram responses to a read-only JSON.

    Parameters
    ----------
    case_dir:
        The case folder. ``<case_dir>/Deepgram/`` is the destination
        directory; it is created if missing.
    chunk_results:
        The list of ``transcribe_chunk`` return dicts. Only the
        ``"raw"`` key of each is persisted — that field carries the
        full unmodified Deepgram HTTP response body.
    chunk_offsets:
        The list of per-chunk start-second offsets (parallel to
        ``chunk_results``). Must be the same length as
        ``chunk_results`` or this function raises ``ValueError``;
        silent truncation by ``zip`` would defeat the forensic
        purpose of the immutable store.
    audio_file:
        Optional source-audio path for provenance.
    model:
        Optional Deepgram model name (``nova-3``, ``nova-3-medical``).
    request_params:
        Optional copy of the Deepgram request parameters dict (after
        ``enforce_required_deepgram_flags``). Saved for forensic
        reconstruction. Without this, a saved response cannot be
        regression-compared against a re-run because the caller has
        no way to verify the parameters matched.
    keyterms:
        Optional list of keyterms actually sent to Deepgram (i.e.
        post-sanitization). Saved alongside ``request_params`` to
        complete the forensic provenance — a keyterm change explains
        most output diffs between runs, so the saved list must be
        the post-sanitization one, not the upstream input.
    timestamp:
        Override the timestamp string used in the filename. Defaults
        to ``datetime.now().strftime("%Y%m%d_%H%M%S")``.

    Returns
    -------
    RawResponseSaveResult
        Carries the destination path, chunk count, and timestamp used.

    Raises
    ------
    ValueError
        If ``chunk_results`` and ``chunk_offsets`` are different
        lengths. Refusing to save partial data is deliberate.
    FileExistsError
        If the target path already exists. Defense-in-depth on top of
        the timestamped filename; the user gets a loud error rather
        than silent corruption.
    OSError
        For any filesystem error during directory creation or file
        write. The caller decides whether to abort the run or
        continue with a degraded forensic record.
    """
    # Length mismatch is a programming error in the caller. Failing
    # loud here is safer than silently truncating to ``min(len(a),
    # len(b))`` via ``zip``, which would produce a forensically
    # incomplete record with no warning.
    chunk_results = list(chunk_results or [])
    chunk_offsets = list(chunk_offsets or [])
    if len(chunk_results) != len(chunk_offsets):
        raise ValueError(
            "raw_store: chunk_results length "
            f"({len(chunk_results)}) does not match chunk_offsets "
            f"length ({len(chunk_offsets)}). "
            "Refusing to save a forensically incomplete record."
        )

    case_dir = Path(case_dir)
    out_dir = case_dir / RAW_STORE_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = timestamp or _build_timestamp()
    target = out_dir / f"{RAW_RESPONSE_FILENAME_PREFIX}{stamp}.json"

    if target.exists():
        # The timestamped filename is meant to make this impossible
        # in practice; if a caller passes a ``timestamp`` override or
        # somehow trips a same-second collision, we refuse loudly.
        raise FileExistsError(
            f"raw_store target already exists, refusing to overwrite: {target}"
        )

    chunks_payload: list[dict[str, Any]] = []
    for index, (result, offset) in enumerate(
            zip(chunk_results, chunk_offsets)
    ):
        # ``result["raw"]`` is the parsed-but-unmodified Deepgram
        # HTTP response body. We persist it as-is. If a caller passed
        # a chunk dict without ``"raw"``, we record None so the file
        # still parses but the gap is visible.
        raw_body = (
            result.get("raw")
            if isinstance(result, dict)
            else None
        )
        chunks_payload.append(
            {
                "index": index,
                "start_seconds": float(offset),
                "deepgram_response": raw_body,
            }
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "saved_at_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "saved_at_local": datetime.now().isoformat(timespec="seconds"),
        "audio_file": audio_file,
        "model": model,
        "request_params": request_params or {},
        "keyterms_sent": list(keyterms) if keyterms else [],
        "chunk_count": len(chunks_payload),
        "chunks": chunks_payload,
    }

    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _set_read_only(target)

    logger.info(
        "[RAW_STORE] saved %s (chunks=%d, keyterms=%d, model=%s, audio=%s)",
        target,
        payload["chunk_count"],
        len(payload["keyterms_sent"]),
        model or "<unknown>",
        audio_file or "<unknown>",
    )

    return RawResponseSaveResult(
        path=target,
        chunk_count=payload["chunk_count"],
        timestamp=stamp,
    )
