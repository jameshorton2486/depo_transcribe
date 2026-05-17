from spec_engine.legal_dictionary import build_case_dictionary, is_legal_term


def test_is_legal_term():
    assert is_legal_term("objection")
    assert not is_legal_term("antique")


def test_build_case_dictionary():
    mapping = build_case_dictionary(["Bexar County", "", "Cause Number"])
    assert mapping["bexar county"] == "Bexar County"
    assert mapping["cause number"] == "Cause Number"
