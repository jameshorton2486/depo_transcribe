from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.intake_parser import _strip_markdown_fences, filter_keyterms


def test_filter_removes_noise_words():
    raw = ["court", "texas", "plaintiff", "Matthew Coger"]
    assert filter_keyterms(raw) == ["Matthew Coger"]


def test_filter_removes_short_terms():
    raw = ["to", "or", "LLC", "El Chino Trucking LLC"]
    assert filter_keyterms(raw) == ["El Chino Trucking LLC"]


def test_filter_removes_pure_numbers():
    raw = ["12345", "2025CI19595", "Matthew Coger"]
    result = filter_keyterms(raw)
    assert "12345" not in result


def test_filter_keeps_alphanumeric_case_numbers():
    raw = ["12345", "2025CI19595", "Matthew Coger"]
    result = filter_keyterms(raw)
    assert "2025CI19595" in result


def test_filter_deduplicates_case_insensitive():
    raw = ["Matthew Coger", "matthew coger", "MATTHEW COGER"]
    assert len(filter_keyterms(raw)) == 1


def test_filter_keeps_valid_proper_nouns():
    raw = ["Will Allan Law Firm", "Boyce Wright Legal", "SUBPOENA DUCES TECUM"]
    result = filter_keyterms(raw)
    assert len(result) == 3


def test_filter_removes_single_lowercase_words():
    raw = ["oral", "cause", "bexar", "pursuant", "Murphy Oil USA"]
    assert filter_keyterms(raw) == ["Murphy Oil USA"]


def test_filter_enforces_60_term_cap():
    raw = [f"Firm Name {i}" for i in range(80)]
    assert len(filter_keyterms(raw)) <= 60


def test_filter_empty_input():
    assert filter_keyterms([]) == []


def test_filter_strips_whitespace():
    raw = ["  Matthew Coger  ", " Will Allan Law Firm "]
    assert filter_keyterms(raw) == ["Matthew Coger", "Will Allan Law Firm"]


def test_strip_markdown_fences_removes_json_fence():
    raw = "```json\n{\"causeNumber\": null}\n```"
    assert _strip_markdown_fences(raw) == "{\"causeNumber\": null}"


def test_strip_markdown_fences_leaves_plain_text():
    raw = "{\"causeNumber\": null}"
    assert _strip_markdown_fences(raw) == raw
