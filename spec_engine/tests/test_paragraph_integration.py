from spec_engine.models import Block, BlockType
from spec_engine.processor import process_blocks, split_blocks_into_paragraphs


class _ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = True


def test_paragraph_split_in_pipeline(monkeypatch):
    long_text = (
        "You understand this is under oath and that your answers carry the same force and effect as testimony in court. "
        "Correct? Correct."
    )
    blocks = [Block(text=long_text, speaker_id=1, speaker_name="THE WITNESS", speaker_role="THE WITNESS", block_type=BlockType.ANSWER)]

    monkeypatch.setattr("spec_engine.processor.apply_corrections", lambda blocks, job_config: blocks)
    monkeypatch.setattr("spec_engine.processor.map_speakers", lambda blocks, job_config: blocks)
    monkeypatch.setattr("spec_engine.processor.classify_blocks", lambda blocks, job_config: blocks)
    monkeypatch.setattr("spec_engine.processor.fix_qa_structure", lambda blocks, job_config=None: blocks)
    monkeypatch.setattr("spec_engine.processor.extract_objections", lambda blocks, job_config: blocks)
    monkeypatch.setattr("spec_engine.processor.validate_blocks", lambda blocks, speaker_map_verified=False: _ValidationResult())

    result = process_blocks(
        blocks,
        job_config={"speaker_map_verified": True},
    )

    assert [block.text for block in result][-2:] == ["Correct?", "Correct."]


def test_no_split_non_speech_block():
    blocks = [Block(text="Some metadata", speaker_id=1, block_type=BlockType.FLAG)]

    result = split_blocks_into_paragraphs(blocks)

    assert len(result) == 1
    assert result[0].text == "Some metadata"
