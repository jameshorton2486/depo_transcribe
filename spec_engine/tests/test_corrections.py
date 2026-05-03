from unittest.mock import patch

from spec_engine.corrections import (
    _build_corrections_map,
    apply_corrections,
    apply_morsons_rules,
)
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


def test_legal_dictionary_applies_when_nod_is_silent():
    fake_dict = {"voir deer": "voir dire", "subpeona": "subpoena"}
    with patch("core.case_vocab.load_legal_dictionary", return_value=fake_dict):
        corrections = _build_corrections_map(confirmed_spellings={}, keyterms=None)
    assert corrections["voir deer"] == "voir dire"
    assert corrections["subpeona"] == "subpoena"


def test_nod_overrides_legal_dictionary_on_collision():
    fake_dict = {"bear county": "Bexar County"}
    nod = {"bear county": "BEXAR COUNTY"}
    with patch("core.case_vocab.load_legal_dictionary", return_value=fake_dict):
        corrections = _build_corrections_map(confirmed_spellings=nod)
    assert corrections["bear county"] == "BEXAR COUNTY"


def test_legal_terms_blocklist_rejects_dictionary_entries():
    bad_dict = {"form": "Foundation", "objection": "Wrong"}
    with patch("core.case_vocab.load_legal_dictionary", return_value=bad_dict):
        corrections = _build_corrections_map()
    assert "form" not in corrections
    assert "objection" not in corrections


def test_legal_terms_blocklist_rejects_nod_entries():
    nod = {"form": "Foundation", "objection": "Wrong"}
    corrections = _build_corrections_map(confirmed_spellings=nod)
    assert "form" not in corrections
    assert "objection" not in corrections
