from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spec_engine.prompt_packs import get_prompt_pack_path, load_prompt_pack


def test_load_prompt_pack_reads_claude_like_v1():
    pack = load_prompt_pack("claude_like_v1")

    assert pack.id == "claude_like_v1"
    assert pack.model == "claude-sonnet-4-6"
    assert pack.max_tokens == 5500


def test_get_prompt_pack_path_points_to_json_file():
    path = get_prompt_pack_path("claude_like_v1")

    assert path.name == "claude_like_v1.json"
    assert path.exists() is True
