from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.keyterm_extractor import split_compound_terms, _is_full_name


def test_full_name_two_words():
    assert _is_full_name("David Boyce") is True


def test_full_name_with_middle_initial():
    assert _is_full_name("David P. Boyce") is True


def test_full_name_three_words():
    assert _is_full_name("Matthew Allen Coger") is True


def test_full_name_rejects_address():
    assert _is_full_name("13526 George Road Suite 200") is False


def test_full_name_rejects_single_word():
    assert _is_full_name("Coger") is False


def test_split_keeps_full_name_intact():
    result = split_compound_terms(["David P. Boyce"])
    assert result == ["David P. Boyce"]


def test_split_strips_street_number():
    result = split_compound_terms(["13526 George Road, San Antonio, TX 78230"])
    assert "George Road" in result


def test_split_removes_prefixed_street_number():
    result = split_compound_terms(["13526 George Road, San Antonio, TX 78230"])
    assert not any(t.startswith("13526") for t in result)


def test_split_removes_zip_code():
    result = split_compound_terms(["George Road, San Antonio, TX 78230"])
    assert not any("78230" in t for t in result)


def test_split_removes_state_abbreviation():
    result = split_compound_terms(["San Antonio, TX 78230"])
    assert not any(t.strip() == "TX" for t in result)


def test_split_removes_suite_number():
    result = split_compound_terms(["4700 Mueller Blvd. Suite 200, Austin"])
    assert not any("Suite" in t for t in result)


def test_split_removes_standalone_suite_number():
    result = split_compound_terms(["4700 Mueller Blvd. Suite 200, Austin"])
    assert not any("200" in t for t in result)


def test_split_keeps_company_with_ampersand():
    result = split_compound_terms(["Wright & Greenhill, P.C."])
    assert any("Wright & Greenhill" in t for t in result)


def test_split_keeps_judicial_district():
    result = split_compound_terms(["408th Judicial District"])
    assert "408th Judicial District" in result


def test_split_empty_input():
    assert split_compound_terms([]) == []


def test_split_drops_skip_words_after_split():
    result = split_compound_terms(["Suite 200, TX 78230"])
    assert result == []
