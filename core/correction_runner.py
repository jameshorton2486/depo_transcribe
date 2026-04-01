"""
core/correction_runner.py

Orchestrates the full deterministic correction pass on a completed transcript.

Workflow:
  1. Locate the Deepgram JSON file saved alongside the .txt transcript
  2. Load job_config.json from source_docs/ (single source of truth)
  3. Build a full JobConfig — all UFM fields + confirmed_spellings + speaker_map
  4. Run: build_blocks_from_deepgram → process_blocks (corrections + QA + validation)
  5. Format the corrected blocks into plain text
  6. Write {stem}_corrected.txt and {stem}_corrections.json to the same folder
  7. Return a result dict the UI can consume

Called from ui/tab_transcript.py via a background thread.
"""

from __future__ import annotations

import json
import os
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app_logging import get_logger

logger = get_logger(__name__)


# ── Output text formatter ─────────────────────────────────────────────────────

_QA_WRAP = 56   # matches spec_engine/emitter.py QA_WRAP_WIDTH
_SP_WRAP = 65   # matches spec_engine/emitter.py WRAP_WIDTH

def format_blocks_to_text(blocks: list) -> str:
    """
    Convert a processed Block list to plain corrected transcript text.

    Q/A lines:   \tQ.  {text} / \tA.  {text}  — two spaces after period
    SP lines:    \t\t\t{LABEL}:  {text}         — three tabs before label
    PAREN lines: ({text})
    FLAG lines:  {text}

    Long lines are wrapped. Continuation lines start at the left margin
    with no indent, matching UFM plain-text output format.
    """
    from spec_engine.models import BlockType

    lines: list[str] = []

    for block in blocks:
        bt   = getattr(block, "block_type", None)
        bv   = getattr(bt, "value", str(bt)) if bt else "UNKNOWN"
        text = (block.text or "").strip()
        role = (getattr(block, "speaker_role", "") or "").strip()
        name = (getattr(block, "speaker_name", "") or "").strip()

        if not text:
            continue

        if bv == "Q":
            wrapped = textwrap.fill(text, width=_QA_WRAP)
            lines.append(f"\tQ.  {wrapped}")
        elif bv == "A":
            wrapped = textwrap.fill(text, width=_QA_WRAP)
            lines.append(f"\tA.  {wrapped}")
        elif bv in ("COLLOQUY", "SPEAKER", "SP"):
            label   = (name or role or "SPEAKER").upper()
            wrapped = textwrap.fill(text, width=_SP_WRAP)
            lines.append(f"\t\t\t{label}:  {wrapped}")
        elif bv in ("PAREN", "PARENTHETICAL", "PN"):
            lines.append(f"({text})")
        elif bv == "FLAG":
            lines.append(text)
        else:
            if name or role:
                label   = (name or role).upper()
                wrapped = textwrap.fill(text, width=_SP_WRAP)
                lines.append(f"\t\t\t{label}:  {wrapped}")
            else:
                lines.append(text)

    return "\n\n".join(lines)


# ── job_config loader ────────────────────────────────────────────────────────

def _load_job_config_for_transcript(transcript_path: str) -> dict:
    """
    Load job_config.json from source_docs/ for the given transcript.

    Directory layout assumed:
        .../CaseFolder/Deepgram/filename.txt   ← transcript_path
        .../CaseFolder/source_docs/job_config.json

    Returns an empty dict if the file does not exist — caller must handle this.
    """
    from core.job_config_manager import load_job_config
    case_root = str(Path(transcript_path).parent.parent)
    return load_job_config(case_root)


# ── JobConfig builder ─────────────────────────────────────────────────────────

def _build_job_config_from_ufm(job_config_data: dict) -> Any:
    """
    Build a complete JobConfig from a loaded job_config.json dict.

    Reads UFM page fields from job_config_data["ufm_fields"] and
    confirmed_spellings from job_config_data["confirmed_spellings"]
    (top-level key — NOT inside ufm_fields).

    No silent fallbacks — missing ufm_fields is logged as an error
    and results in an empty JobConfig with default values only.
    """
    from core.field_mapping import UFM_TO_CFG_SCALAR
    from spec_engine.models import JobConfig, CounselInfo

    # ── Validate structure — no silent fallback ───────────────────────────────
    ufm = job_config_data.get("ufm_fields", {})
    if not ufm:
        logger.error(
            "[CorrectionRunner] ufm_fields missing or empty in job_config — "
            "JobConfig will use defaults only"
        )

    cfg = JobConfig()

    # ── Scalar fields via mapping dict ────────────────────────────────────────
    for ufm_key, cfg_attr in UFM_TO_CFG_SCALAR.items():
        value = ufm.get(ufm_key, "")
        if value and hasattr(cfg, cfg_attr):
            setattr(cfg, cfg_attr, value)

    # ── Complex fields — explicit type coercions ──────────────────────────────

    # defendant_name (str) → defendant_names (list[str])
    defendant = ufm.get("defendant_name", "")
    if defendant:
        cfg.defendant_names = [defendant]

    # video_required (str) → is_videotaped (bool)
    video = ufm.get("video_required", "")
    cfg.is_videotaped = bool(
        video and str(video).lower() not in ("", "no", "false")
    )

    # plaintiff_counsel / defense_counsel → list[CounselInfo]
    for atty in ufm.get("plaintiff_counsel", []):
        cfg.plaintiff_counsel.append(CounselInfo(
            name=atty.get("name", ""),    firm=atty.get("firm", ""),
            sbot=atty.get("sbot", ""),    address=atty.get("address", ""),
            phone=atty.get("phone", ""),  party=atty.get("party", ""),
        ))
    for atty in ufm.get("defense_counsel", []):
        cfg.defense_counsel.append(CounselInfo(
            name=atty.get("name", ""),    firm=atty.get("firm", ""),
            sbot=atty.get("sbot", ""),    address=atty.get("address", ""),
            phone=atty.get("phone", ""),  party=atty.get("party", ""),
        ))

    # speaker_map — JSON stores string keys, JobConfig needs int keys
    speaker_map = ufm.get("speaker_map", {})
    if isinstance(speaker_map, dict):
        cfg.speaker_map = {int(k): v for k, v in speaker_map.items()}

    # speaker_map_verified — must be True for Q/A classification to use map
    verified = ufm.get("speaker_map_verified", False)
    cfg.speaker_map_verified = bool(verified)

    # ── confirmed_spellings — TOP LEVEL of job_config, NOT inside ufm_fields ─
    spellings = job_config_data.get("confirmed_spellings", {})
    if isinstance(spellings, dict) and spellings:
        cfg.confirmed_spellings = spellings
        logger.info(
            "[CorrectionRunner] confirmed_spellings: %d entries loaded",
            len(spellings),
        )
    else:
        logger.warning(
            "[CorrectionRunner] confirmed_spellings empty — "
            "name corrections will not run for this transcript"
        )

    logger.info(
        "[CorrectionRunner] JobConfig built: cause=%r  witness=%r  "
        "spellings=%d  speakers=%d  counsel=%d+%d",
        cfg.cause_number,
        cfg.witness_name,
        len(cfg.confirmed_spellings),
        len(cfg.speaker_map),
        len(cfg.plaintiff_counsel),
        len(cfg.defense_counsel),
    )
    return cfg


# ── Deepgram JSON locator ─────────────────────────────────────────────────────

def _find_deepgram_json(transcript_path: str) -> str | None:
    """
    Given a .txt transcript path in a Deepgram/ folder, find the matching
    Deepgram structured JSON file (the one without _raw or _corrections suffix).

    Matching strategy (in order):
      1. Same stem, .json extension (exact stem match)
      2. Most recently modified .json in the same folder that doesn't end
         in _raw.json or _corrections.json
    """
    folder = Path(transcript_path).parent
    stem = Path(transcript_path).stem

    exact = folder / f"{stem}.json"
    if exact.exists():
        return str(exact)

    base_stem = stem
    for suffix in ("_corrected", "_renamed"):
        if base_stem.endswith(suffix):
            base_stem = base_stem[: -len(suffix)]

    exact_base = folder / f"{base_stem}.json"
    if exact_base.exists():
        return str(exact_base)

    excluded_endings = ("_raw.json", "_corrections.json")
    candidates = [
        f for f in folder.glob("*.json")
        if not any(str(f).endswith(e) for e in excluded_endings)
    ]
    if not candidates:
        return None

    return str(max(candidates, key=lambda f: f.stat().st_mtime))


# ── Correction records serializer ────────────────────────────────────────────

def _serialize_corrections(blocks: list) -> list[dict]:
    """Extract all CorrectionRecord objects from processed blocks."""
    from spec_engine.models import CorrectionRecord

    result = []
    for i, block in enumerate(blocks):
        for record in (block.meta.get("corrections") or []):
            if isinstance(record, CorrectionRecord):
                result.append({
                    "block_index": record.block_index,
                    "pattern": record.pattern,
                    "original": record.original,
                    "corrected": record.corrected,
                })
            elif isinstance(record, dict):
                result.append(record)
    return result


# ── Main entry point ──────────────────────────────────────────────────────────

def run_correction_job(
    transcript_path: str,
    progress_callback: Callable[[str], None] | None = None,
    done_callback: Callable[[dict], None] | None = None,
) -> None:
    """
    Run the full deterministic correction pass on a transcript file.

    Must be called in a background thread — calls done_callback when complete.

    Args:
        transcript_path:    Absolute path to the .txt transcript file.
        progress_callback:  Called with status strings during processing.
        done_callback:      Called with result dict when complete.

    Result dict keys:
        success (bool)
        corrected_path (str | None)    — path to _corrected.txt
        corrections_path (str | None)  — path to _corrections.json
        correction_count (int)
        flag_count (int)
        error (str | None)
    """

    def _log(msg: str):
        logger.info("[CorrectionRunner] %s", msg)
        if progress_callback:
            progress_callback(msg)

    def _done(result: dict):
        if done_callback:
            done_callback(result)

    try:
        from spec_engine.block_builder import build_blocks_from_deepgram, build_blocks_from_text
        from spec_engine.processor import process_blocks
        from app_logging import start_pipeline_session, end_pipeline_session

        session_id = start_pipeline_session(
            "CORRECTIONS",
            transcript=Path(transcript_path).name,
        )

        _log("Locating Deepgram JSON...")
        json_path = _find_deepgram_json(transcript_path)

        if json_path:
            _log(f"Loading Deepgram JSON: {Path(json_path).name}")
            with open(json_path, "r", encoding="utf-8") as fh:
                deepgram_data = json.load(fh)
            if "utterances" in deepgram_data:
                blocks = build_blocks_from_deepgram(deepgram_data)
            else:
                _log("JSON has no utterances key — falling back to text parsing")
                raw_text = Path(transcript_path).read_text(encoding="utf-8")
                blocks = build_blocks_from_text(raw_text)
        else:
            _log("No Deepgram JSON found — parsing transcript text directly")
            raw_text = Path(transcript_path).read_text(encoding="utf-8")
            blocks = build_blocks_from_text(raw_text)

        _log(f"Loaded {len(blocks)} blocks")

        _log("Loading case configuration...")
        job_config_data = _load_job_config_for_transcript(transcript_path)
        if job_config_data:
            _log(
                f"job_config.json loaded: "
                f"ufm_fields={len(job_config_data.get('ufm_fields', {}))} keys  "
                f"spellings={len(job_config_data.get('confirmed_spellings', {}))}  "
                f"keyterms={len(job_config_data.get('deepgram_keyterms', []))}"
            )
            job_config = _build_job_config_from_ufm(job_config_data)
        else:
            _log("No job_config.json found — using default JobConfig (no name corrections)")
            from spec_engine.models import JobConfig
            job_config = JobConfig()

        _log("Running corrections pipeline...")
        corrected_blocks = process_blocks(blocks, job_config)
        _log(f"Pipeline complete: {len(corrected_blocks)} blocks processed")

        all_corrections = _serialize_corrections(corrected_blocks)
        correction_count = len(all_corrections)
        flag_count = sum(
            1 for b in corrected_blocks
            if getattr(b.block_type, "value", "") == "FLAG"
        )
        _log(f"Corrections applied: {correction_count}  |  Scopist flags: {flag_count}")

        _log("Formatting corrected transcript...")
        corrected_text = format_blocks_to_text(corrected_blocks)

        folder = Path(transcript_path).parent
        stem = Path(transcript_path).stem
        if stem.endswith("_corrected"):
            stem = stem[: -len("_corrected")]

        corrected_path = folder / f"{stem}_corrected.txt"
        corrections_path = folder / f"{stem}_corrections.json"

        _log(f"Writing: {corrected_path.name}")
        corrected_path.write_text(corrected_text, encoding="utf-8")

        _log(f"Writing: {corrections_path.name}")
        corrections_data = {
            "source_transcript": transcript_path,
            "corrected_at": datetime.now().isoformat(),
            "correction_count": correction_count,
            "flag_count": flag_count,
            "corrections": all_corrections,
        }
        with open(corrections_path, "w", encoding="utf-8") as fh:
            json.dump(corrections_data, fh, indent=2, ensure_ascii=False)

        _log(f"✓ Correction complete — {correction_count} corrections, {flag_count} flags")

        end_pipeline_session(
            session_id, "CORRECTIONS",
            success=True,
            blocks=len(corrected_blocks),
            corrections=correction_count,
            flags=flag_count,
            spellings=len(job_config.confirmed_spellings),
            output=Path(corrected_path).name,
        )

        _done({
            "success": True,
            "corrected_path": str(corrected_path),
            "corrections_path": str(corrections_path),
            "corrected_text": corrected_text,
            "correction_count": correction_count,
            "flag_count": flag_count,
            "error": None,
        })

    except Exception as exc:
        logger.exception("[CorrectionRunner] Failed: %s", exc)
        _log(f"ERROR: {exc}")
        try:
            end_pipeline_session(session_id, "CORRECTIONS", success=False, error=str(exc)[:120])
        except Exception:
            pass
        _done({
            "success": False,
            "corrected_path": None,
            "corrections_path": None,
            "corrected_text": "",
            "correction_count": 0,
            "flag_count": 0,
            "error": str(exc),
        })
