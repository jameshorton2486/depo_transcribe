from spec_engine.corrections import apply_corrections, apply_morsons_rules
from spec_engine.models import TranscriptBlock


def test_apply_morsons_rules_handles_basic_legal_cleanup():
    assert apply_morsons_rules("yes i went there") == "Yes, i went there."
    assert apply_morsons_rules("did you go there") == "Did you go there?"
    assert apply_morsons_rules("i i went there") == "I  I went there."


def test_apply_corrections_runs_proper_nouns_before_morsons_rules():
    blocks = [
        TranscriptBlock(
            speaker="speaker 1",
            text="yes doctor karam testified",
            type="colloquy",
        )
    ]
    corrected = apply_corrections(blocks, confirmed_spellings={"karam": "Caram"})
    assert corrected[0].text == "Yes, doctor Caram testified."
