"""Tests for Phase 7D additional universal legal vocabulary corrections."""

from spec_engine.corrections import (
    _fix_eod_to_eld,
    fix_traffic_citation_mishearing,
    fix_universal_legal_phrases,
)


def test_fix_recs_plural():
    result = fix_universal_legal_phrases("How many other RECs have you been in?")
    assert "wrecks" in result and "RECs" not in result


def test_fix_recs_singular():
    assert "wreck" in fix_universal_legal_phrases("that REC happened in 2018")


def test_fix_recs_singular_the():
    assert "wreck" in fix_universal_legal_phrases("tell me about the REC")


def test_fix_recs_preserves_other_words():
    assert fix_universal_legal_phrases("the records will speak for themselves") == "the records will speak for themselves"


def test_fix_city_elevator_truck():
    assert "city utility truck" in fix_universal_legal_phrases("it was a city elevator truck")


def test_fix_city_levator_truck():
    assert "city utility truck" in fix_universal_legal_phrases("a city levator truck was involved")


def test_fix_reserve_for_trial_variants():
    assert "reserve for trial" in fix_universal_legal_phrases("we will reserve for Tometrol")


def test_fix_reserve_for_tomorrow():
    assert "reserve for trial" in fix_universal_legal_phrases("I will reserve for tomorrow")


def test_fix_deposition_from():
    result = fix_universal_legal_phrases("This is the beginning of the deposition from Mr. Taylor")
    assert "deposition of" in result and "deposition from" not in result


def test_fix_stipulations_for_any_witness():
    result = fix_universal_legal_phrases("Counsel, state the stipulations for any witness.")
    assert "stipulations for the witness" in result


def test_reporter_name_is_not_hardcoded_in_universal_phrase_rules():
    assert fix_universal_legal_phrases("I am Mia Bardell, Court Reporter.") == (
        "I am Mia Bardell, Court Reporter."
    )


def test_fix_eod_to_eld_with_trucking_context():
    result = _fix_eod_to_eld("I install EOD devices for truck drivers")
    assert "ELD" in result and "EOD" not in result


def test_fix_eod_no_replacement_without_context():
    assert "EOD" in _fix_eod_to_eld("we are done for the EOD")


def test_fix_eod_electronic_logs_context():
    assert "ELD" in _fix_eod_to_eld("electronic logs and EOD tracking")


def test_fix_traffic_citation_with_context():
    result = fix_traffic_citation_mishearing("I got a sanitation for speeding")
    assert "citation" in result and "sanitation" not in result


def test_fix_traffic_citation_no_context():
    assert "sanitation" in fix_traffic_citation_mishearing("the sanitation department picked up trash")


def test_fix_traffic_citation_ticket_context():
    assert "citation" in fix_traffic_citation_mishearing("the officer gave me a sanitation ticket")


def test_fix_traffic_citation_with_court_context():
    assert "citation" in fix_traffic_citation_mishearing("the sanitation required me to go to court")


def test_fix_traffic_citation_officer_context():
    assert "citation" in fix_traffic_citation_mishearing("the officer gave me a sanitation")
