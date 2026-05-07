r"""Production bridge: saved Deepgram run JSON -> spec_engine -> corrected
TXT + corrected JSON, sitting next to the originals.

This is the first wired path from production output into spec_engine.
Read-only relative to all source files; never overwrites the original
transcript or original JSON. No UI, no Deepgram I/O, no DOCX, no AI
correction.

Public entry point:
    run_corrections_for_json(json_path) -> CorrectionResult

What it does:
    1. Load the saved per-run JSON produced by core/job_runner.py.
    2. Convert its `utterances` list (Deepgram-shape: 'transcript' /
       'speaker_label') into the {speaker, text, type} block-input shape
       expected by spec_engine.classify_blocks.
    3. Run the canonical spec_engine pipeline:
           classify_blocks
           apply_corrections (with confirmed_spellings + keyterms from
                              the case folder's job_config.json, if any)
           enforce_structure (Q/A invariants)
           normalize_speakers (label canonicalization)
           emit_blocks (UFM-strict text output)
    4. Write `<base>_corrected.txt` (the emitted text) and
       `<base>_corrected.json` (metadata + per-block dump) next to the
       source. The source files are untouched.

Manual invocation from PowerShell:
    .\.venv\Scripts\python.exe -c "
    from pathlib import Path
    from core.corrections_runner import run_corrections_for_json
    r = run_corrections_for_json(Path(r'<path-to-deepgram-run-json>'))
    print(r)
    "
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app_logging import get_logger
from spec_engine.classifier import classify_blocks
from spec_engine.corrections import apply_corrections
from spec_engine.emitter import emit_blocks
from spec_engine.qa_fixer import enforce_structure
from spec_engine.speaker_mapper import normalize_speakers

logger = get_logger(__name__)


@dataclass
class CorrectionResult:
    """Returned to the caller. Paths are absolute strings; warnings /
    errors capture any soft-failure from the spec_engine validation
    pass without raising — callers can decide what to surface in UI.
    """

    source_json_path: str
    corrected_txt_path: str
    corrected_json_path: str
    block_count: int
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _load_job_vocab(case_root: Path) -> tuple[dict, list[str]]:
    """Best-effort load of confirmed_spellings + deepgram_keyterms from
    `<case>/source_docs/job_config.json`. Missing or malformed file
    yields empty defaults — corrections still run, just with no
    per-case vocabulary layer (the global legal_dictionary still
    applies via spec_engine.corrections._build_corrections_map).
    """
    cfg_path = case_root / "source_docs" / "job_config.json"
    if not cfg_path.exists():
        return {}, []
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.warning("[corrections_runner] could not read %s: %s", cfg_path, exc)
        return {}, []
    confirmed = data.get("confirmed_spellings") or {}
    keyterms = list(data.get("deepgram_keyterms") or [])
    return (confirmed if isinstance(confirmed, dict) else {}, keyterms)


def _utterances_to_block_input(utterances: Any) -> list[dict[str, str]]:
    """Map saved Deepgram-shape utterances (with 'transcript' + 'speaker_label')
    onto the {speaker, text, type} input that classify_blocks expects.

    Mirrors what spec_engine/block_builder.build_blocks does, but reads
    the Deepgram-canonical 'transcript' / 'speaker_label' keys that the
    saved JSON actually uses (block_builder reads bare 'text' / numeric
    'speaker', so feeding it raw saved utterances yields empty blocks).
    """
    out: list[dict[str, str]] = []
    for utt in utterances or []:
        if not isinstance(utt, dict):
            continue
        text = (utt.get("transcript") or utt.get("text") or "").strip()
        if not text:
            continue
        # Prefer the string label ("Speaker 0") so downstream
        # normalize_speaker_label produces a clean "SPEAKER 0:" prefix
        # rather than the raw int.
        speaker = utt.get("speaker_label")
        if not speaker:
            raw = utt.get("speaker")
            speaker = f"Speaker {raw}" if raw is not None else "UNKNOWN"
        out.append({"speaker": str(speaker), "text": text, "type": "utterance"})
    return out


def _serialize_block(block) -> dict[str, Any]:
    """Convert a TranscriptBlock dataclass into a plain dict for JSON.
    Defensive against any future field additions via getattr fallbacks.
    """
    return {
        "speaker": getattr(block, "speaker", ""),
        "text": getattr(block, "text", ""),
        "type": getattr(block, "type", ""),
        "source_type": getattr(block, "source_type", ""),
        "examiner": getattr(block, "examiner", None),
    }


def run_corrections_for_json(json_path: Path | str) -> CorrectionResult:
    """Run the spec_engine pipeline against a saved per-run JSON.

    Writes <base>_corrected.txt and <base>_corrected.json into the same
    directory as the source. The source JSON, the source TXT, and the
    raw_deepgram.json sibling are NEVER modified. No DOCX is produced
    here; that is a separate downstream step.

    Returns a CorrectionResult dataclass with the absolute paths of the
    new files and any soft warnings / errors captured during the run.
    Hard failures (missing file, bad JSON) raise; this function should
    be called inside a try / except by the UI layer.
    """
    json_path = Path(json_path)
    if not json_path.is_file():
        raise FileNotFoundError(f"Input JSON not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as fh:
        source = json.load(fh)
    if not isinstance(source, dict):
        raise ValueError(
            f"Input JSON root must be an object, got {type(source).__name__}"
        )

    # Resolve the case-root vocab: the saved per-run JSON sits in
    # <case>/Deepgram/<file>.json, so the case folder is the parent's
    # parent. Walk-up failures gracefully degrade to empty vocab.
    case_root = json_path.parent.parent
    confirmed_spellings, keyterms = _load_job_vocab(case_root)

    block_input = _utterances_to_block_input(source.get("utterances"))

    warnings: list[str] = []
    errors: list[str] = []

    classified = classify_blocks(block_input)
    corrected_blocks = apply_corrections(
        classified,
        confirmed_spellings=confirmed_spellings,
        keyterms=keyterms,
    )
    try:
        fixed = enforce_structure(corrected_blocks)
    except ValueError as exc:
        # enforce_structure is strict — it raises on Q/A invariants
        # like orphan answers or consecutive questions. Capture the
        # error so the UI can surface it, but keep going with the
        # un-validated list so the proofreader still gets *something*
        # to look at.
        errors.append(f"enforce_structure: {exc}")
        fixed = corrected_blocks
    mapped = normalize_speakers(fixed)
    text = emit_blocks(mapped)

    base = json_path.stem
    txt_path = json_path.parent / f"{base}_corrected.txt"
    out_json_path = json_path.parent / f"{base}_corrected.json"

    txt_path.write_text(text, encoding="utf-8")

    serial_blocks = [_serialize_block(b) for b in mapped]
    out_payload = {
        "source_json_path": str(json_path),
        "corrected_txt_path": str(txt_path),
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "block_count": len(mapped),
        "blocks": serial_blocks,
        "original_transcript": source.get("transcript", ""),
        "warnings": warnings,
        "errors": errors,
    }
    with open(out_json_path, "w", encoding="utf-8") as fh:
        json.dump(out_payload, fh, indent=2, ensure_ascii=False)

    logger.info(
        "[corrections_runner] %s -> %s (%d blocks, %d errors)",
        json_path.name,
        txt_path.name,
        len(mapped),
        len(errors),
    )

    return CorrectionResult(
        source_json_path=str(json_path),
        corrected_txt_path=str(txt_path),
        corrected_json_path=str(out_json_path),
        block_count=len(mapped),
        warnings=warnings,
        errors=errors,
    )
