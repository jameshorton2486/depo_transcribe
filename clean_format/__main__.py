"""CLI entry point for clean-format transcript generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from clean_format.docx_writer import write_deposition_docx
from clean_format.formatter import (
    format_transcript,
    load_case_meta,
    load_deepgram_words_from_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir")
    parser.add_argument("--output")
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    raw_path = case_dir / "raw_deepgram.txt"
    raw_json_path = case_dir / "raw_deepgram.json"
    meta_path = case_dir / "case_meta.json"

    raw_text = raw_path.read_text(encoding="utf-8")
    case_meta = load_case_meta(meta_path)
    # Step E: pass Deepgram word-level data so the cleanup pass can
    # wrap low-confidence tokens with markers that the DOCX writer
    # renders as yellow highlights. Missing/malformed json yields None
    # and the pipeline degrades to plain rendering.
    deepgram_words = load_deepgram_words_from_json(raw_json_path)
    formatted_text = format_transcript(
        raw_text, case_meta, deepgram_words=deepgram_words
    )

    output_path = args.output
    if output_path is None:
        date_part = (
            str(case_meta.get("deposition_date", "")).replace("/", "-").replace(",", "")
        )
        output_path = case_dir / (
            f"{case_meta.get('witness_name', 'Witness').split()[-1]}_"
            f"Deposition_{date_part}.docx"
        )

    saved_path = write_deposition_docx(formatted_text, case_meta, output_path)
    print(saved_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
