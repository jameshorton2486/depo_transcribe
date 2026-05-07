"""Runner for the AI utterance splitter.

Loads a ``{base}_raw.json`` produced by ``core/job_runner.py``, runs
``spec_engine.utterance_splitter.split_utterances``, and writes
``{base}_split_raw.json`` next to the input. The split file is a
strict superset — preserves the original ``utterances`` array verbatim,
adds ``split_utterances`` and ``split_metadata`` top-level keys.

This is a manual-trigger path. ``core/corrections_runner.py`` does NOT
automatically pick up split files; that is Step 2D's territory.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import datetime
from pathlib import Path

from spec_engine.utterance_splitter import split_utterances

logger = logging.getLogger(__name__)

_RAW_SUFFIX = "_raw.json"
_SPLIT_SUFFIX = "_split_raw.json"


def run_splitter(
    raw_json_path: str | Path,
    *,
    max_ai_calls: int = 200,
) -> Path:
    """Run the AI splitter on a finished raw transcript.

    Args:
        raw_json_path: path to ``{base}_raw.json``.

    Returns:
        Path to the written ``{base}_split_raw.json``.

    Raises:
        FileNotFoundError, ValueError, RuntimeError: see corresponding
            error messages.
    """
    raw_json_path = Path(raw_json_path).resolve()
    if not raw_json_path.exists():
        raise FileNotFoundError(f"Raw JSON not found: {raw_json_path}")
    if not raw_json_path.name.endswith(_RAW_SUFFIX):
        raise ValueError(
            f"Expected a *{_RAW_SUFFIX} file, got: {raw_json_path.name}"
        )

    raw_data = json.loads(raw_json_path.read_text(encoding="utf-8"))
    utterances = raw_data.get("utterances") or []
    if not utterances:
        raise RuntimeError(
            "Raw JSON has no utterances; cannot run splitter"
        )

    logger.info(
        "Running utterance splitter on %d utterances", len(utterances)
    )

    split_utts, meta = split_utterances(utterances, max_ai_calls=max_ai_calls)

    logger.info(
        "Splitter complete: original=%d split=%d flagged=%d "
        "ai_calls=%d cache_hits=%d validation_failures=%d "
        "skipped_over_cap=%d",
        meta.original_count, meta.split_count, meta.flagged_count,
        meta.ai_calls, meta.cache_hits, meta.validation_failures,
        meta.skipped_over_cap,
    )

    output = dict(raw_data)
    output["split_utterances"] = split_utts
    meta_dict = dataclasses.asdict(meta)
    meta_dict["timestamp"] = datetime.now().isoformat(timespec="seconds")
    meta_dict["source_raw"] = raw_json_path.name
    output["split_metadata"] = meta_dict

    base = raw_json_path.name[: -len(_RAW_SUFFIX)]
    output_path = raw_json_path.parent / f"{base}{_SPLIT_SUFFIX}"
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Wrote split file: %s", output_path)
    return output_path


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the AI utterance splitter on a raw transcript JSON."
    )
    parser.add_argument("raw_json", help="Path to {base}_raw.json")
    parser.add_argument(
        "--max-ai-calls",
        type=int,
        default=200,
        help=(
            "Hard cap on AI splitter calls per invocation (default: 200). "
            "Utterances flagged after this cap pass through unchanged."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        out = run_splitter(args.raw_json, max_ai_calls=args.max_ai_calls)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
