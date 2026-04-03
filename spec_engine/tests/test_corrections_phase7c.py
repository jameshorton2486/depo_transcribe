"""Tests for Phase 7C spoken digit collapse corrections."""

from spec_engine.corrections import (
    _collapse_spoken_digits,
    fix_address_digits,
    fix_cause_number_digits,
    fix_csr_number_digits,
)


def test_collapse_spoken_digits_basic():
    assert _collapse_spoken_digits("two zero two five") == "2025"


def test_collapse_spoken_digits_with_letter():
    assert _collapse_spoken_digits("two zero two five c one zero eight zero six zero") == "2025C108060"


def test_collapse_spoken_digits_all_digits():
    assert _collapse_spoken_digits("one two one two nine") == "12129"


def test_fix_cause_number_digits_basic():
    result = fix_cause_number_digits("Cause No. two zero two five c one zero eight zero six zero")
    assert "2025" in result and "Cause No." in result


def test_fix_cause_number_digits_preserves_prefix():
    assert fix_cause_number_digits("Cause No. two zero two five").startswith("Cause No.")


def test_fix_cause_number_digits_no_false_positive():
    assert fix_cause_number_digits("The witness said one thing.") == "The witness said one thing."


def test_fix_csr_number_licensed_in_texas():
    result = fix_csr_number_digits("licensed in Texas number one two one two nine")
    assert "CSR No." in result and "12129" in result


def test_fix_csr_number_texas_number():
    result = fix_csr_number_digits("Texas number one two one two nine")
    assert "CSR No." in result and "12129" in result


def test_fix_address_digits_four_digit():
    result = fix_address_digits("eight five zero one Southwest Capital Highway")
    assert "8501" in result and "Southwest Capital Highway" in result


def test_fix_address_digits_three_digit():
    result = fix_address_digits("two three seven Westgate Drive")
    assert "237" in result and "Westgate Drive" in result


def test_fix_address_digits_no_false_positive():
    assert fix_address_digits("one thing led to another") == "one thing led to another"


def test_fix_address_zip_code():
    assert "78408" in fix_address_digits("Corpus Christi, Texas seven eight four zero eight")
