"""One-shot: re-run only the clean_format half on the freshly-transcribed
case folder, producing a DOCX. Used to push past MarkerDriftError when
the drift threshold has been temporarily relaxed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True)
    args = parser.parse_args()
    case_dir = Path(args.case_dir).resolve()

    from clean_format import format_transcript, write_deposition_docx
    from clean_format.formatter import load_deepgram_words_from_json

    raw_txt = case_dir / "Deepgram" / "raw_deepgram.txt"
    raw_json = case_dir / "Deepgram" / "raw_deepgram.json"
    case_meta_path = case_dir / "case_meta.json"

    raw_text = raw_txt.read_text(encoding="utf-8")
    case_meta = json.loads(case_meta_path.read_text(encoding="utf-8"))
    words = load_deepgram_words_from_json(raw_json)

    t0 = time.time()
    formatted_text = format_transcript(raw_text, case_meta, deepgram_words=words)
    elapsed = time.time() - t0
    print(f"[CLEAN_FORMAT] Anthropic done in {elapsed:.1f}s — formatted chars={len(formatted_text)}")

    witness_last = (case_meta.get("witness_name", "Witness").split() or ["Witness"])[-1]
    date_part = (
        str(case_meta.get("deposition_date", ""))
        .replace("/", "-")
        .replace(",", "")
    )

    # Persist the Anthropic-cleaned text BEFORE attempting DOCX write
    # so a DOCX permission error doesn't discard the $2 result.
    formatted_txt_path = case_dir / f"{witness_last}_Deposition_{date_part}_fresh.txt"
    formatted_txt_path.write_text(formatted_text, encoding="utf-8")
    print(f"[CLEAN_FORMAT] Formatted text saved: {formatted_txt_path}")

    # Write the DOCX to a fresh filename so a locked existing DOCX
    # (Word holding the file) doesn't kill the run.
    docx_path = case_dir / f"{witness_last}_Deposition_{date_part}_fresh.docx"
    saved = write_deposition_docx(formatted_text, case_meta, docx_path)
    print(f"[CLEAN_FORMAT] DOCX written: {saved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
