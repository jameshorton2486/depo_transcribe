from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.job_config_manager import load_job_config, merge_and_save


def test_merge_and_save_persists_utt_split(tmp_path):
    merge_and_save(str(tmp_path), utt_split=0.7)

    data = load_job_config(str(tmp_path))

    assert data["utt_split"] == 0.7
