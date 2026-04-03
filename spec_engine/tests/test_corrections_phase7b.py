"""Tests for Phase 7B universal legal phrase and Texas seed corrections."""

from spec_engine.corrections import (
    TEXAS_DEPOSITION_SEEDS,
    apply_texas_deposition_seeds,
    fix_universal_legal_phrases,
)


def test_fix_oath_phrase():
    assert fix_universal_legal_phrases("so help you guide") == "so help you God"


def test_fix_mope_deposition():
    assert fix_universal_legal_phrases("this mope deposition") == "this remote deposition"


def test_fix_remotes_or_any_witness():
    assert "remote swearing of the witness" in fix_universal_legal_phrases(
        "remotes or any witness by saying your name"
    )


def test_fix_notice_and_attorney():
    assert "noticing attorney" in fix_universal_legal_phrases(
        "beginning with the notice and attorney"
    )


def test_fix_fly_down_sheriff():
    assert "flag down a sheriff" in fix_universal_legal_phrases(
        "we had to fly down a sheriff"
    )


def test_fix_rs22_insurance():
    assert "SR-22" in fix_universal_legal_phrases("RS22 insurance policy")


def test_fix_electronic_books():
    assert fix_universal_legal_phrases("electronic books") == "electronic logs"


def test_texas_deposition_seeds_constant_present():
    assert TEXAS_DEPOSITION_SEEDS["Bear County"] == "Bexar County"


def test_seeds_bear_county():
    assert "Bexar County" in apply_texas_deposition_seeds("Bear County, Texas", {})


def test_seeds_royces_county():
    assert "Nueces County" in apply_texas_deposition_seeds("Royces County", {})


def test_seeds_case_specific_wins():
    assert apply_texas_deposition_seeds(
        "Bear County", {"Bear County": "Bear County (intentional)"}
    ) == "Bear County"


def test_seeds_does_not_modify_clean_text():
    assert apply_texas_deposition_seeds("San Antonio, Texas", {}) == "San Antonio, Texas"
