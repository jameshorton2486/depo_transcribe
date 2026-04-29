from __future__ import annotations

import argparse
import json
from pathlib import Path

from .docx_writer import write_deposition_docx
from .formatter import format_transcript


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    raw_text = (case_dir / "raw_deepgram.txt").read_text(encoding="utf-8")
    case_meta = json.loads((case_dir / "case_meta.json").read_text(encoding="utf-8"))

    formatted = format_transcript(raw_text, case_meta)
    witness_last = case_meta["witness_name"].split()[-1]
    out_name = f"{witness_last}_Deposition_{case_meta['deposition_date']}.docx"
    output = Path(args.output) if args.output else case_dir / out_name

    path = write_deposition_docx(case_meta, formatted, output)
    print(path)


if __name__ == "__main__":
    main()
