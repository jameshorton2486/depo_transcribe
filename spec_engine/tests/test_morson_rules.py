from spec_engine.morson_rules import normalize_ellipsis, normalize_interruptions


def test_normalize_interruptions_to_spaced_double_hyphen():
    assert normalize_interruptions("wait—no") == "wait -- no"
    assert normalize_interruptions("wait --no") == "wait -- no"


def test_normalize_ellipsis_variants():
    assert normalize_ellipsis("Well . . . maybe") == "Well... maybe"
    assert normalize_ellipsis("Wait....") == "Wait..."
