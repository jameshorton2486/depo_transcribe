"""
Tests for Phase 7F small universal fixes.
"""

from spec_engine.corrections import (
    apply_texas_deposition_seeds,
    fix_spoken_dates,
    fix_universal_legal_phrases,
)


def test_remotes_for_any_witness():
    result = fix_universal_legal_phrases("remotes for any witness")
    assert "remote swearing of the witness" in result


def test_remote_swearing_of_any_witness():
    result = fix_universal_legal_phrases("remote swearing of any witness")
    assert "remote swearing of the witness" in result


def test_standalone_year_twenty_nineteen():
    result = fix_spoken_dates("that was twenty nineteen")
    assert "2019" in result


def test_standalone_year_twenty_eighteen():
    result = fix_spoken_dates("graduated in twenty eighteen")
    assert "2018" in result


def test_standalone_year_two_thousand_five():
    result = fix_spoken_dates("since two thousand and five")
    assert "2005" in result


def test_standalone_year_two_thousand_thirteen():
    result = fix_spoken_dates("back in two thousand thirteen")
    assert "2013" in result


def test_heb_agb():
    result = apply_texas_deposition_seeds("going to AGB", {})
    assert "H-E-B" in result


def test_heb_hep():
    result = apply_texas_deposition_seeds("the HEP parking lot", {})
    assert "H-E-B" in result


def test_heb_h_e_b_unchanged():
    result = apply_texas_deposition_seeds("going to H-E-B", {})
    assert "H-E-B" in result
