from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.job_config_manager import load_job_config, merge_and_save


def test_merge_and_save_persists_utt_split(tmp_path):
    merge_and_save(str(tmp_path), utt_split=0.7)

    data = load_job_config(str(tmp_path))

    assert data["utt_split"] == 0.7


def test_merge_and_save_persists_transcription_settings(tmp_path):
    merge_and_save(
        str(tmp_path),
        model="nova-3-medical",
        audio_quality="Aggressive (noisy/poor audio)",
        utt_split=1.2,
    )

    data = load_job_config(str(tmp_path))

    assert data["model"] == "nova-3-medical"
    assert data["audio_quality"] == "Aggressive (noisy/poor audio)"
    assert data["utt_split"] == 1.2


def test_load_job_config_ignores_legacy_deepgram_keyterms(tmp_path):
    config_path = tmp_path / "source_docs" / "job_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "deepgram_keyterms": ["Matthew Coger"],
                "confirmed_spellings": {"Koger": "Coger"},
            }
        ),
        encoding="utf-8",
    )

    data = load_job_config(str(tmp_path))

    assert "deepgram_keyterms" not in data


def test_merge_and_save_ignores_deepgram_keyterms_section(tmp_path):
    merge_and_save(
        str(tmp_path),
        deepgram_keyterms=["Matthew Coger"],
        confirmed_spellings={"Koger": "Coger"},
    )

    data = load_job_config(str(tmp_path))

    assert "deepgram_keyterms" not in data
