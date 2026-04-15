"""Tests for Phase 7B universal legal phrase and Texas seed corrections."""

from spec_engine.corrections import (
    TEXAS_DEPOSITION_SEEDS,
    apply_texas_deposition_seeds,
    clean_block,
    fix_universal_legal_phrases,
)
from spec_engine.models import JobConfig


def test_fix_oath_phrase():
    assert fix_universal_legal_phrases("so help you guide") == "so help you God"


def test_fix_oath_phrase_not_applied_outside_oath_context():
    result = fix_universal_legal_phrases("He texted the phrase so help you guide to mock the oath.")
    assert "so help you guide" in result


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


def test_fix_remit_for_remote_deposition():
    result = fix_universal_legal_phrases("state your remit for this remote deposition")
    assert "agreement for this remote deposition" in result


def test_fix_same_force_and_effect_phrase():
    result = fix_universal_legal_phrases("same effect as a weapon in the courthouse")
    assert "same force and effect as if given in open court" in result


def test_fix_oath_response_they_do():
    result = fix_universal_legal_phrases("They do. Thank you.")
    assert result.startswith("I do.")


def test_fix_stay_ahead_to_stand():
    result = fix_universal_legal_phrases("do you have to stay ahead")
    assert "do you have to stand" in result


def test_fix_court_reporter_licensed_in_texas():
    result = fix_universal_legal_phrases("I am court reporter license in Texas")
    assert "court reporter, licensed in Texas" in result


def test_fix_who_you_representing():
    result = fix_universal_legal_phrases("who you representing")
    assert "who you're representing" in result


def test_fix_braswell_to_brownsville_incident():
    result = fix_universal_legal_phrases("the Braswell incident")
    assert "Brownsville incident" in result


def test_fix_re_ranger_phrase():
    result = fix_universal_legal_phrases("Is this the first re ranger")
    assert "where you were injured" in result


def test_fix_psychiatrist_question_garble():
    result = fix_universal_legal_phrases("who was with living with you a psychiatrist")
    assert "who was living with you at that address" in result


def test_fix_job_stown_to_jobstown():
    result = fix_universal_legal_phrases("I work at Job stown Pizza and Grill")
    assert "Jobstown Pizza and Grill" in result


def test_fix_court_portal_license():
    result = clean_block(
        "I'm Mia Bardot Court Portal License in Texas, CSR No. 12129.",
        JobConfig(),
    )[0]
    assert "court reporter, licensed in texas" in result.lower()


def test_fix_attend_high_school_admission():
    result = fix_universal_legal_phrases("Did you attend high school admission?")
    assert "Did you attend high school in Mission" in result


def test_fix_by_airport():
    result = fix_universal_legal_phrases("I was gonna be by airport.")
    assert "by the airport" in result


def test_fix_food_safety_certification():
    result = clean_block("I have my food safe certification.", JobConfig())[0]
    assert "food safety certification" in result.lower()


def test_fix_a_a_mixture():
    result = clean_block("It was a a mixture of flavors.", JobConfig())[0]
    assert "a mixture" in result.lower()


def test_fix_two_day_drive():
    result = clean_block("It was a two day drive.", JobConfig())[0]
    assert "two-day drive" in result.lower()


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


def test_seeds_fix_miah_bardo():
    assert "Miah Bardot" in apply_texas_deposition_seeds("I am Mia Bardo.", {})


def test_seeds_fix_nadia_ivonne():
    assert "Nadia Yvonne" in apply_texas_deposition_seeds("Nadia Ivonne Trevino", {})
