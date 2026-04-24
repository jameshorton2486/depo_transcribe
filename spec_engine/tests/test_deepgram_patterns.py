from types import SimpleNamespace

from spec_engine.deepgram_patterns import apply_deepgram_patterns
from spec_engine.models import Block, BlockType, JobConfig
from spec_engine import processor as processor_module


def test_apply_deepgram_patterns_rewrites_known_garble_and_tracks_audit():
    block = Block(
        text="mouth swearing of the witness",
        raw_text="mouth swearing of the witness",
        speaker_id=1,
        meta={},
    )

    result = apply_deepgram_patterns([block])

    assert result[0].text == "remote swearing of the witness"
    assert result[0].raw_text == "mouth swearing of the witness"
    assert result[0].meta["corrections"][0].pattern.startswith("deepgram_pattern:")


def test_process_blocks_applies_deepgram_patterns_before_speaker_mapping(monkeypatch):
    blocks = [
        Block(
            text="court for a license",
            raw_text="court for a license",
            speaker_id=4,
            meta={},
        )
    ]

    monkeypatch.setattr(processor_module, "apply_corrections", lambda blocks, job_config: blocks)

    def _map_speakers(blocks, job_config):
        assert blocks[0].text == "court reporter, licensed"
        blocks[0].speaker_name = "THE REPORTER"
        blocks[0].speaker_role = "THE REPORTER"
        return blocks

    monkeypatch.setattr(processor_module, "map_speakers", _map_speakers)

    def _classify_blocks(blocks, job_config):
        for block in blocks:
            block.block_type = BlockType.SPEAKER
        return blocks

    monkeypatch.setattr(processor_module, "classify_blocks", _classify_blocks)
    monkeypatch.setattr(processor_module, "fix_qa_structure", lambda blocks, job_config=None: blocks)
    monkeypatch.setattr(processor_module, "split_blocks_into_paragraphs", lambda blocks: blocks)
    monkeypatch.setattr(processor_module, "extract_objections", lambda blocks, job_config: blocks)
    monkeypatch.setattr(
        processor_module,
        "validate_blocks",
        lambda blocks, speaker_map_verified=False: SimpleNamespace(errors=[], warnings=[]),
    )

    result = processor_module.process_blocks(blocks, JobConfig(speaker_map_verified=True))

    assert result[0].text == "court reporter, licensed"
