from spec_engine.corrections import (
    fix_cause_number_prefix,
    fix_depot_mishearing,
    fix_judicial_district_ordinal,
)


def test_fix_depot_mishearing_plural():
    assert fix_depot_mishearing("keep these depots") == "keep these depots"


def test_fix_depot_mishearing_singular():
    assert fix_depot_mishearing("doing two depot") == "doing two depot"


def test_fix_depot_mishearing_preserves_other_words():
    assert fix_depot_mishearing("the train station") == "the train station"


def test_fix_cause_number_prefix_cop():
    assert fix_cause_number_prefix("cop number 2025CI08060") == "cop number 2025CI08060"


def test_fix_cause_number_prefix_cost():
    assert fix_cause_number_prefix("cost number 2025") == "cost number 2025"


def test_fix_judicial_district_ordinal_three_digit():
    assert fix_judicial_district_ordinal("407 Judicial District") == "407th Judicial District"


def test_fix_judicial_district_ordinal_already_correct():
    assert fix_judicial_district_ordinal("407th Judicial District") == "407th Judicial District"


def test_fix_judicial_district_ordinal_285():
    assert fix_judicial_district_ordinal("285 Judicial District") == "285th Judicial District"


def test_fix_judicial_district_ordinal_spoken_digits():
    assert fix_judicial_district_ordinal("four zero seven Judicial District") == "407th Judicial District"
