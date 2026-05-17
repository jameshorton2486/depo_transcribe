from spec_engine.punctuation_rules import normalize_punctuation_spacing


def test_normalize_punctuation_spacing():
    assert normalize_punctuation_spacing("Hello ,  world!!") == "Hello, world!"
