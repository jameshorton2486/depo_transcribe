from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.intake_parser import (
    STANDARD_LEGAL_SPELLINGS,
    _normalize_confirmed_spellings,
    _strip_markdown_fences,
    filter_keyterms,
    hard_filter_keyterms,
    parse_intake_document,
)


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


def test_filter_removes_single_caps_words():
    assert "ORAL" not in hard_filter_keyterms(["ORAL", "CAUSE", "Matthew Coger"])


def test_filter_keeps_multi_word_all_caps():
    result = hard_filter_keyterms(["SUBPOENA DUCES TECUM"])
    assert "SUBPOENA DUCES TECUM" in result


def test_filter_caps_at_60():
    raw = [f"Name Person {i}" for i in range(80)]
    assert len(hard_filter_keyterms(raw)) <= 60


def test_hard_filter_removes_noise_words():
    noisy = ["court", "texas", "plaintiff", "defendant", "March"]
    assert hard_filter_keyterms(noisy) == []


def test_hard_filter_deduplicates():
    raw = ["Matthew Coger", "matthew coger", "MATTHEW COGER"]
    assert len(hard_filter_keyterms(raw)) == 1


def test_hard_filter_removes_pure_numbers():
    assert hard_filter_keyterms(["12345", "78230"]) == []


def test_hard_filter_min_length_4():
    assert hard_filter_keyterms(["SA", "LLC", "TX"]) == []


def test_standard_spellings_contains_objection():
    assert STANDARD_LEGAL_SPELLINGS["Infection"] == "Objection."


def test_standard_spellings_contains_pass_witness():
    assert "Past witness" in STANDARD_LEGAL_SPELLINGS


def test_standard_spellings_contains_leading():
    assert STANDARD_LEGAL_SPELLINGS["Bleeding"] == "Leading."


def test_normalize_confirmed_spellings_canonicalizes_value_case():
    result = _normalize_confirmed_spellings(
        {"Caso": "picasso"},
        ["Picasso", "Techy Inc"],
    )
    assert result["Caso"] == "Picasso"


def test_normalize_confirmed_spellings_canonicalizes_multiword_value():
    result = _normalize_confirmed_spellings(
        {"Techy": "techy inc", "Aboca": "aboca llc"},
        ["Picasso", "Techy Inc", "Aboca LLC"],
    )
    assert result["Techy"] == "Techy Inc"
    assert result["Aboca"] == "Aboca LLC"


def test_normalize_confirmed_spellings_strips_whitespace():
    result = _normalize_confirmed_spellings(
        {"  Caso  ": "  Picasso  "},
        ["Picasso"],
    )
    assert result["Caso"] == "Picasso"


def test_normalize_confirmed_spellings_keeps_unknown_target_when_needed():
    result = _normalize_confirmed_spellings(
        {"Macao": "Macao"},
        ["Picasso"],
    )
    assert result["Macao"] == "Macao"


def test_parse_intake_document_uses_preextracted_text_without_pdf_read(monkeypatch):
    def _fail_open(_path):
        raise AssertionError("pdfplumber should not be used when extracted_text is supplied")

    class _FakeMessages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text='{"cause_number":"2025-CI-19595","court":null,"case_style":null,"deposition_date":null,"deposition_method":null,"subpoena_duces_tecum":false,"amendment":null,"read_and_sign":false,"signature_waived":false,"video_recorded":false,"plaintiffs":[],"defendants":[],"deponents":[],"ordering_attorney":{},"filing_attorney":{},"copy_attorneys":[],"ordered_by":null,"reporter_name":null,"reporter_csr":null,"reporter_firm":null,"reporter_address":null,"vocabulary_terms":[],"all_proper_nouns":[],"confirmed_spellings":{}}')])

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=_fail_open))
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic))

    result = parse_intake_document(
        "ignored.pdf",
        extracted_text=(
            "Cause No. 2025-CI-19595\n"
            "Notice of Deposition of Matthew Coger.\n"
            "This packet contains enough text to avoid scanned-PDF fallback."
        ),
    )

    assert result and result.cause_number == "2025-CI-19595"
