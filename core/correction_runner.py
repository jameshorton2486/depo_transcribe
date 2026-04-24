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
import time as _time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app_logging import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE CONTROL
# ══════════════════════════════════════════════════════════════════════════════
# Per-stage switches for the deterministic correction pipeline.
# Set to False to skip a stage during debugging or to isolate a problem.
#
# In this codebase, the deterministic Layers 1-4 (deepgram patterns, NOD
# corrections, preamble rules, scopist flags) live INSIDE spec_engine/processor
# — they run as part of process_blocks() and cannot be toggled individually
# from here. The only top-level kill switch is LAYER_5_SPEC_ENGINE.
#
# The AI correction pass (ai_corrector.py) is NOT controlled here. It runs
# only when the user clicks "AI Correct" in the Corrections tab.
# ══════════════════════════════════════════════════════════════════════════════

PIPELINE_CONFIG: dict[str, bool] = {
    # Full spec_engine pipeline: corrections, classifier, qa_fixer,
    # objections, speaker_mapper, validator, etc. Disabling this produces
    # output without Q/A structure or speaker labels.
    "LAYER_5_SPEC_ENGINE": True,
}


def _elapsed_ms(start: float) -> int:
    """Return elapsed milliseconds since a perf_counter() start timestamp."""
    return int((_time.perf_counter() - start) * 1000)


def _print_pipeline_audit_header(
    transcript_path: str,
    job_config_data: dict,
    draft_mode: bool,
    log_fn: Callable[[str], None],
) -> None:
    """Print a header summarizing what will run before the pipeline starts."""
    ufm = (job_config_data or {}).get("ufm_fields", {}) or {}
    cause = ufm.get("cause_number") or "(not set)"
    witness = ufm.get("witness_name") or "(not set)"
    spellings = len((job_config_data or {}).get("confirmed_spellings", {}) or {})
    keyterms = len((job_config_data or {}).get("deepgram_keyterms", []) or [])

    sep = "-" * 60
    log_fn(sep)
    log_fn("DEPO-PRO CORRECTION PIPELINE")
    log_fn(sep)
    log_fn(f"  FILE     : {Path(transcript_path).name}")
    log_fn(f"  CAUSE    : {cause}")
    log_fn(f"  WITNESS  : {witness}")
    log_fn(f"  SPELLINGS: {spellings} confirmed  |  KEYTERMS: {keyterms}")
    log_fn(f"  MODE     : {'draft (speaker map unverified)' if draft_mode else 'final'}")
    log_fn(sep)
    log_fn("LAYERS:")
    for key, enabled in PIPELINE_CONFIG.items():
        status = "ON " if enabled else "OFF"
        label = key.replace("_", " ").title()
        log_fn(f"  [{status}] {label}")
    log_fn(sep)


def format_blocks_to_text(blocks: list) -> str:
    from spec_engine.emitter import emit_blocks

    paragraph_text = emit_blocks(blocks)
    if not paragraph_text:
        return ""

    return paragraph_text


def _build_ai_proper_nouns(job_config_data: dict, ufm: dict, cfg: Any) -> list[str]:
    """
    Build a stable proper-noun context list for the AI pass.

    Source of truth is the saved job_config.json. We prefer persisted
    Deepgram keyterms, then enrich with confirmed correct spellings and
    high-value participant names from the mapped JobConfig.
    """
    terms: set[str] = set()

    def _add(value: Any):
        if not isinstance(value, str):
            return
        normalized = " ".join(value.split()).strip()
        if len(normalized) >= 3:
            terms.add(normalized)

    for term in job_config_data.get("deepgram_keyterms", []) or []:
        _add(term)

    for correct in (job_config_data.get("confirmed_spellings", {}) or {}).values():
        _add(correct)

    _add(ufm.get("cause_number", ""))
    _add(cfg.witness_name)
    _add(cfg.reporter_name)
    _add(cfg.plaintiff_name)
    for name in getattr(cfg, "defendant_names", []) or []:
        _add(name)
    for counsel in getattr(cfg, "plaintiff_counsel", []) or []:
        _add(getattr(counsel, "name", ""))
        _add(getattr(counsel, "firm", ""))
    for counsel in getattr(cfg, "defense_counsel", []) or []:
        _add(getattr(counsel, "name", ""))
        _add(getattr(counsel, "firm", ""))

    return sorted(terms)


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
        safe_map = {}
        for raw_key, raw_name in speaker_map.items():
            try:
                safe_map[int(raw_key)] = raw_name
            except (TypeError, ValueError):
                logger.warning("[CorrectionRunner] Ignoring non-integer speaker_map key: %r", raw_key)
        cfg.speaker_map = safe_map

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

    # ── AI proper noun context — from saved keyterms + mapped case names ────
    cfg.all_proper_nouns = _build_ai_proper_nouns(job_config_data, ufm, cfg)

    logger.info(
        "[CorrectionRunner] JobConfig built: cause=%r  witness=%r  "
        "spellings=%d  speakers=%d  counsel=%d+%d  ai_terms=%d",
        cfg.cause_number,
        cfg.witness_name,
        len(cfg.confirmed_spellings),
        len(cfg.speaker_map),
        len(cfg.plaintiff_counsel),
        len(cfg.defense_counsel),
        len(cfg.all_proper_nouns),
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

    session_id = None
    pipeline_start = _time.perf_counter()

    try:
        from spec_engine.block_builder import build_blocks_from_deepgram
        from spec_engine.processor import process_blocks
        from spec_engine.run_logger import RunLogger
        from app_logging import start_pipeline_session, end_pipeline_session

        session_id = start_pipeline_session(
            "CORRECTIONS",
            transcript=Path(transcript_path).name,
        )

        _log(f"Using correction runner module: {Path(__file__).resolve()}")

        # ── Load job config first so we can print the audit header ──────────
        _log("Loading case configuration...")
        job_config_data = _load_job_config_for_transcript(transcript_path)
        if job_config_data:
            _log(
                f"  job_config.json: "
                f"ufm_fields={len(job_config_data.get('ufm_fields', {}))} keys  "
                f"spellings={len(job_config_data.get('confirmed_spellings', {}))}  "
                f"keyterms={len(job_config_data.get('deepgram_keyterms', []))}"
            )
            job_config = _build_job_config_from_ufm(job_config_data)
        else:
            _log("  No job_config.json — using default JobConfig (no name corrections)")
            from spec_engine.models import JobConfig
            job_config = JobConfig()
            job_config_data = {}

        draft_mode = not bool(job_config.speaker_map_verified)
        _print_pipeline_audit_header(
            transcript_path, job_config_data, draft_mode, _log
        )

        # ── Layer 0 — build raw blocks from Deepgram JSON ───────────────────
        t0 = _time.perf_counter()
        _log("Layer 0 | block_builder.py - Loading Deepgram JSON...")
        json_path = _find_deepgram_json(transcript_path)

        if not json_path:
            raise RuntimeError(
                "Deepgram JSON not found. Corrections require utterances-backed Deepgram JSON."
            )

        _log(f"  JSON file: {Path(json_path).name}")
        with open(json_path, "r", encoding="utf-8") as fh:
            deepgram_data = json.load(fh)
        if "utterances" not in deepgram_data:
            raise RuntimeError(
                "Deepgram JSON missing 'utterances'. Ensure 'utterances=True' is enabled."
            )
        blocks = build_blocks_from_deepgram(deepgram_data)
        if not blocks:
            raise RuntimeError("No transcript blocks could be generated.")
        _log(f"  Layer 0 complete - {len(blocks)} raw blocks  ({_elapsed_ms(t0)}ms)")

        # ── Layer 5 — spec_engine full pipeline ────────────────────────────
        if PIPELINE_CONFIG["LAYER_5_SPEC_ENGINE"]:
            t5 = _time.perf_counter()
            _log("Layer 5 | processor.py - spec_engine pipeline starting...")
            _log("  corrections / deepgram_patterns / nod_corrections / preamble_rules")
            _log("  flag_rules / speaker_mapper / speaker_intelligence / classifier")
            _log("  qa_fixer / paragraph_splitter / objections / validator")
            with RunLogger(cause_number=job_config.cause_number or Path(transcript_path).stem) as run_logger:
                corrected_blocks = process_blocks(blocks, job_config, run_logger=run_logger)
            _log(
                f"  Layer 5 complete - {len(corrected_blocks)} blocks  "
                f"({_elapsed_ms(t5)}ms)"
            )
        else:
            _log("Layer 5 | SKIPPED (LAYER_5_SPEC_ENGINE = False)")
            _log("  WARNING: output has no Q/A structure, speaker labels, or objection extraction")
            corrected_blocks = list(blocks)

        all_corrections = _serialize_corrections(corrected_blocks)
        correction_count = len(all_corrections)
        flag_count = sum(
            1 for b in corrected_blocks
            if getattr(b.block_type, "value", "") == "FLAG"
        )
        _log(f"Corrections applied: {correction_count}  |  Scopist flags: {flag_count}")

        # ── Layer 6 — format ──────────────────────────────────────────────
        t6 = _time.perf_counter()
        _log("Layer 6 | emitter.py - Formatting transcript...")
        corrected_text = format_blocks_to_text(corrected_blocks)
        _log(
            f"  Layer 6 complete - {len(corrected_text):,} chars  "
            f"({_elapsed_ms(t6)}ms)"
        )

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
            "draft_mode": draft_mode,
            "corrections": all_corrections,
        }
        with open(corrections_path, "w", encoding="utf-8") as fh:
            json.dump(corrections_data, fh, indent=2, ensure_ascii=False)

        total_ms = _elapsed_ms(pipeline_start)
        sep = "-" * 60
        _log(sep)
        _log("PIPELINE COMPLETE")
        _log(f"  Corrections : {correction_count}")
        _log(f"  Flags       : {flag_count}")
        _log(f"  Time        : {total_ms}ms")
        _log(sep)
        _log(f"Correction complete - {correction_count} corrections, {flag_count} flags")

        end_pipeline_session(
            session_id, "CORRECTIONS",
            success=True,
            blocks=len(corrected_blocks),
            corrections=correction_count,
            flags=flag_count,
            spellings=len(job_config.confirmed_spellings),
            draft_mode=draft_mode,
            output=Path(corrected_path).name,
        )

        _done({
            "success": True,
            "corrected_path": str(corrected_path),
            "corrections_path": str(corrections_path),
            "corrected_text": corrected_text,
            "correction_count": correction_count,
            "flag_count": flag_count,
            "draft_mode": draft_mode,
            "error": None,
        })

    except Exception as exc:
        logger.exception("[CorrectionRunner] Failed: %s", exc)
        _log(f"ERROR: {exc}")
        try:
            if session_id is not None:
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
