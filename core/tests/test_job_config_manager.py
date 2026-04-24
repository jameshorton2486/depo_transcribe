from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.job_config_manager import load_job_config, merge_and_save


def test_merge_and_save_persists_transcription_settings(tmp_path):
    merge_and_save(
        str(tmp_path),
        model="nova-3-medical",
        audio_quality="Aggressive (noisy/poor audio)",
    )

    data = load_job_config(str(tmp_path))

    assert data["model"] == "nova-3-medical"
    assert data["audio_quality"] == "Aggressive (noisy/poor audio)"


def test_load_job_config_preserves_deepgram_keyterms(tmp_path):
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

    assert data["deepgram_keyterms"] == ["Matthew Coger"]


def test_merge_and_save_persists_deepgram_keyterms_section(tmp_path):
    merge_and_save(
        str(tmp_path),
        deepgram_keyterms=["Matthew Coger"],
        confirmed_spellings={"Koger": "Coger"},
    )

    data = load_job_config(str(tmp_path))

    assert data["deepgram_keyterms"] == ["Matthew Coger"]


def test_merge_and_save_persists_intake_metadata_sections(tmp_path):
    merge_and_save(
        str(tmp_path),
        speaker_map_suggestion={"deponent": "Chris Epley"},
        intake_entity_counts={"people": 4, "orgs": 2, "keyterms": 7},
    )

    data = load_job_config(str(tmp_path))

    assert data["speaker_map_suggestion"] == {"deponent": "Chris Epley"}
    assert data["intake_entity_counts"] == {"people": 4, "orgs": 2, "keyterms": 7}
