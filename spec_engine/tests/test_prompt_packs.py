from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spec_engine.prompt_packs import get_prompt_pack_path, load_prompt_pack


def test_load_prompt_pack_reads_legal_transcript_v1():
    pack = load_prompt_pack("legal_transcript_v1")

    assert pack.id == "legal_transcript_v1"
    assert pack.model == "claude-sonnet-4-6"
    assert pack.max_tokens == 5500


def test_get_prompt_pack_path_points_to_json_file():
    path = get_prompt_pack_path("legal_transcript_v1")

    assert path.name == "legal_transcript_v1.json"
    assert path.exists() is True


def test_load_prompt_pack_defaults_to_legal_transcript_v1(monkeypatch):
    monkeypatch.delenv("AI_CORRECTION_PROMPT_PACK", raising=False)

    pack = load_prompt_pack()

    assert pack.id == "legal_transcript_v1"


def test_load_prompt_pack_reads_legal_verbatim_v2():
    pack = load_prompt_pack("legal_verbatim_v2")

    assert pack.id == "legal_verbatim_v2"
    assert pack.model == "claude-sonnet-4-6"
    assert pack.temperature == 0.0
    assert pack.invariants["strict_verbatim_mode"] is True


def test_legal_verbatim_v2_prompt_preserves_single_output_contract():
    pack = load_prompt_pack("legal_verbatim_v2")

    assert "Return only the corrected transcript text." in pack.system_prompt
    assert "Do not return a clean transcript section" in pack.system_prompt


def test_legacy_claude_like_v1_pack_still_loads_for_compatibility():
    pack = load_prompt_pack("claude_like_v1")

    assert pack.id == "claude_like_v1"
