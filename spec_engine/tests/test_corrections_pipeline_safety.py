from spec_engine.corrections import apply_corrections, clean_block
from spec_engine.models import Block, JobConfig


def _cfg() -> JobConfig:
    return JobConfig()


def test_fix_spaced_dashes_normalizes_partial_spacing_cases():
    assert clean_block("word-- word", _cfg())[0] == "Word -- word."
    assert clean_block("word --word", _cfg())[0] == "Word -- word."


def test_fix_spaced_dashes_preserves_short_stutter_tokens():
    result = clean_block("I--I do not know.", _cfg())[0]
    assert "I--I" in result


def test_apply_corrections_only_skips_near_duplicate_blocks():
    blocks = [
        Block(
            speaker_id=1,
            text="I don't recall.",
            raw_text="I don't recall.",
            meta={"start": 10.0},
        ),
        Block(
            speaker_id=1,
            text="I don't recall.",
            raw_text="I don't recall.",
            meta={"start": 25.0},
        ),
    ]

    corrected = apply_corrections(blocks, _cfg())

    assert len(corrected) == 2


def test_apply_corrections_skips_only_tightly_overlapping_duplicate_blocks():
    blocks = [
        Block(
            speaker_id=1,
            text="I don't recall.",
            raw_text="I don't recall.",
            meta={"start": 10.0},
        ),
        Block(
            speaker_id=1,
            text="I don't recall.",
            raw_text="I don't recall.",
            meta={"start": 10.4},
        ),
    ]

    corrected = apply_corrections(blocks, _cfg())

    assert len(corrected) == 1
