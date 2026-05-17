from spec_engine.punctuation_rules import (
    enforce_deterministic_formatting,
    normalize_dashes,
    normalize_ellipsis,
    normalize_punctuation_spacing,
    normalize_quote_spacing,
    normalize_whitespace,
)


def test_normalize_punctuation_spacing():
    assert normalize_punctuation_spacing("Hello ,  world!!") == "Hello, world!"


def test_normalize_dashes():
    assert normalize_dashes("wait—what") == "wait -- what"


def test_normalize_ellipsis():
    assert normalize_ellipsis("well . . . maybe") == "well... maybe"


def test_normalize_quote_spacing():
    assert normalize_quote_spacing('He said " hello "') == 'He said "hello"'


def test_normalize_whitespace():
    assert normalize_whitespace("A  \n\n\nB\t\t") == "A\n\nB\t"


def test_enforce_deterministic_formatting_pipeline():
    raw = 'He said  " hello " ,  then paused . . .\n\n\nwait—what'
    assert enforce_deterministic_formatting(raw) == 'He said "hello", then paused...\n\nwait -- what'
