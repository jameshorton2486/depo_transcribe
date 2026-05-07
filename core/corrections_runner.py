"""Run spec_engine corrections on a finished Deepgram run.

Reads ``{base}_raw.json`` (written by ``core/job_runner.py``), pulls
``confirmed_spellings`` and keyterms from ``source_docs/job_config.json``,
and writes ``{base}_corrected.txt`` next to the input.

This is the deterministic post-Deepgram correction stage. It does not
modify the original transcript files; it only adds a corrected ``.txt``
next to them. Re-runs overwrite.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from spec_engine.block_builder import build_blocks
from spec_engine.processor import process_blocks

logger = logging.getLogger(__name__)

_RAW_SUFFIX = "_raw.json"
_CORRECTED_SUFFIX = "_corrected.txt"


def _resolve_job_config(raw_json_path: Path) -> Path:
    """Locate ``source_docs/job_config.json`` from the raw JSON path.

    Expected case layout::

        case_folder/
          source_docs/
            job_config.json
          Deepgram/
            {base}_raw.json
    """
    deepgram_dir = raw_json_path.parent
    case_folder = deepgram_dir.parent
    return case_folder / "source_docs" / "job_config.json"


def _load_job_config(job_config_path: Path) -> tuple[dict, list[str]]:
    """Read ``confirmed_spellings`` and keyterms from the top level.

    Per project contract, ``confirmed_spellings`` lives at the top level
    of ``job_config.json`` and is a sibling of ``ufm_fields``, never
    nested inside it. Keyterms are read from ``deepgram_keyterms`` first,
    falling back to ``keyterms``.

    Missing file or malformed JSON → log a warning and return empties.
    """
    if not job_config_path.exists():
        logger.warning(
            "job_config.json not found at %s; running with empty corrections inputs",
            job_config_path,
        )
        return {}, []

    try:
        data = json.loads(job_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Could not parse %s (%s); running with empty corrections inputs",
            job_config_path,
            exc,
        )
        return {}, []

    confirmed_spellings = data.get("confirmed_spellings") or {}
    keyterms = data.get("deepgram_keyterms")
    if keyterms is None:
        keyterms = data.get("keyterms") or []

    if not isinstance(confirmed_spellings, dict):
        logger.warning(
            "confirmed_spellings is not a dict (got %s); ignoring",
            type(confirmed_spellings).__name__,
        )
        confirmed_spellings = {}

    if not isinstance(keyterms, list):
        logger.warning(
            "keyterms is not a list (got %s); ignoring",
            type(keyterms).__name__,
        )
        keyterms = []

    if not confirmed_spellings:
        logger.warning(
            "confirmed_spellings is empty — name corrections will be skipped"
        )
    if not keyterms:
        logger.info("keyterms list is empty")

    return confirmed_spellings, keyterms


def _build_corrected_text(
    raw_data: dict,
    confirmed_spellings: dict,
    keyterms: list[str],
) -> str:
    """Run the ``spec_engine`` pipeline on assembled utterances.

    Uses the top-level ``utterances`` field from the wrapped raw JSON,
    feeding it to ``build_blocks`` as a synthetic Deepgram alternative.
    """
    utterances = raw_data.get("utterances") or []
    if not utterances:
        raise RuntimeError(
            "Raw JSON has no utterances; cannot run corrections"
        )

    alt = {"utterances": utterances}
    blocks = build_blocks(alt)
    if not blocks:
        raise RuntimeError(
            f"build_blocks returned no blocks from {len(utterances)} utterances"
        )

    return process_blocks(
        blocks,
        confirmed_spellings=confirmed_spellings,
        keyterms=keyterms,
    )


def run_corrections(raw_json_path: str | Path) -> Path:
    """Apply ``spec_engine`` corrections to a finished raw run.

    Args:
        raw_json_path: Path to ``{base}_raw.json`` written by
            ``core/job_runner.py``.

    Returns:
        Path to the written ``{base}_corrected.txt`` file.

    Raises:
        FileNotFoundError: ``raw_json_path`` does not exist.
        ValueError: ``raw_json_path`` does not end with ``_raw.json``.
        RuntimeError: raw JSON has no utterances or ``spec_engine``
            could not produce a transcript from them.
    """
    raw_json_path = Path(raw_json_path).resolve()

    if not raw_json_path.exists():
        raise FileNotFoundError(f"Raw JSON not found: {raw_json_path}")
    if not raw_json_path.name.endswith(_RAW_SUFFIX):
        raise ValueError(
            f"Expected a *{_RAW_SUFFIX} file, got: {raw_json_path.name}"
        )

    raw_data = json.loads(raw_json_path.read_text(encoding="utf-8"))

    job_config_path = _resolve_job_config(raw_json_path)
    confirmed_spellings, keyterms = _load_job_config(job_config_path)

    logger.info(
        "Running corrections: utterances=%d  spellings=%d  keyterms=%d",
        len(raw_data.get("utterances") or []),
        len(confirmed_spellings),
        len(keyterms),
    )

    corrected_text = _build_corrected_text(
        raw_data, confirmed_spellings, keyterms
    )

    base_name = raw_json_path.name[: -len(_RAW_SUFFIX)]
    output_path = raw_json_path.parent / f"{base_name}{_CORRECTED_SUFFIX}"
    timestamp = datetime.now().isoformat(timespec="seconds")
    header = f"# Corrected from {raw_json_path.name} on {timestamp}\n"
    output_path.write_text(header + corrected_text, encoding="utf-8")

    logger.info("Wrote corrected transcript: %s", output_path)
    return output_path


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Run spec_engine corrections on a finished raw transcript JSON."
        )
    )
    parser.add_argument("raw_json", help="Path to {base}_raw.json")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        out = run_corrections(args.raw_json)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
