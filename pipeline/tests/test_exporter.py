from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import exporter


def test_export_results_writes_raw_deepgram_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "OUTPUT_DIR", str(tmp_path))

    assembled_result = {
        "words": [],
        "utterances": [
            {
                "speaker": 0,
                "transcript": "Merged text.",
                "start": 0.0,
                "end": 1.0,
                "speaker_label": "Speaker 0",
            },
        ],
        "raw_utterances": [
            {"speaker": 0, "transcript": "Good afternoon,", "start": 0.0, "end": 0.5},
            {"speaker": 0, "transcript": "Doctor Leifer.", "start": 0.5, "end": 1.0},
        ],
        "transcript": "Speaker 0: Merged text.",
        "raw_chunks": [],
    }

    result = exporter.export_results(assembled_result, source_filename="sample.wav")

    raw_path = Path(result["raw_deepgram"])
    assert raw_path.name == "raw_deepgram.txt"
    assert raw_path.exists()
    assert raw_path.read_text(encoding="utf-8") == (
        "Speaker 0: Good afternoon,\n\n" "Speaker 0: Doctor Leifer.\n\n"
    )
