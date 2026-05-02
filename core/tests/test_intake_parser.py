from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.config import MAX_KEYTERMS
from core.intake_parser import (
    STANDARD_LEGAL_SPELLINGS,
    _clean_extracted_text,
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


def test_filter_enforces_shared_term_cap():
    raw = [f"Firm Name {i}" for i in range(MAX_KEYTERMS + 20)]
    assert len(filter_keyterms(raw)) <= MAX_KEYTERMS


def test_filter_empty_input():
    assert filter_keyterms([]) == []


def test_filter_strips_whitespace():
    raw = ["  Matthew Coger  ", " Will Allan Law Firm "]
    assert filter_keyterms(raw) == ["Matthew Coger", "Will Allan Law Firm"]


def test_strip_markdown_fences_removes_json_fence():
    raw = '```json\n{"causeNumber": null}\n```'
    assert _strip_markdown_fences(raw) == '{"causeNumber": null}'


def test_strip_markdown_fences_leaves_plain_text():
    raw = '{"causeNumber": null}'
    assert _strip_markdown_fences(raw) == raw


def test_filter_removes_single_caps_words():
    assert "ORAL" not in hard_filter_keyterms(["ORAL", "CAUSE", "Matthew Coger"])


def test_filter_keeps_multi_word_all_caps():
    result = hard_filter_keyterms(["SUBPOENA DUCES TECUM"])
    assert "SUBPOENA DUCES TECUM" in result


def test_filter_caps_at_max_keyterms():
    raw = [f"Name Person {i}" for i in range(MAX_KEYTERMS + 20)]
    assert len(hard_filter_keyterms(raw)) <= MAX_KEYTERMS


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


def test_clean_extracted_text_normalizes_known_ocr_name_variant():
    raw = "JAYPEE ASCUNSION\nvs.\nSTONE"

    cleaned = _clean_extracted_text(raw)

    assert "ASCUNCION" in cleaned


def test_parse_intake_document_uses_preextracted_text_without_pdf_read(monkeypatch):
    def _fail_open(_path):
        raise AssertionError(
            "pdfplumber should not be used when extracted_text is supplied"
        )

    class _FakeMessages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text='{"cause_number":"2025-CI-19595","court":null,"case_style":null,"deposition_date":null,"deposition_method":null,"subpoena_duces_tecum":false,"amendment":null,"read_and_sign":false,"signature_waived":false,"video_recorded":false,"plaintiffs":[],"defendants":[],"deponents":[],"ordering_attorney":{},"filing_attorney":{},"copy_attorneys":[],"ordered_by":null,"reporter_name":null,"reporter_csr":null,"reporter_firm":null,"reporter_address":null,"vocabulary_terms":[],"all_proper_nouns":[],"confirmed_spellings":{}}'
                    )
                ]
            )

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=_fail_open))
    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic)
    )

    result = parse_intake_document(
        "ignored.pdf",
        extracted_text=(
            "Cause No. 2025-CI-19595\n"
            "Notice of Deposition of Matthew Coger.\n"
            "This packet contains enough text to avoid scanned-PDF fallback."
        ),
    )

    assert result and result.cause_number == "2025-CI-19595"


def test_parse_intake_document_uses_stripped_env_api_key(monkeypatch):
    captured = {}

    class _FakeMessages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text='{"cause_number":null,"court":null,"case_style":null,"deposition_date":null,"deposition_method":null,"subpoena_duces_tecum":false,"amendment":null,"read_and_sign":false,"signature_waived":false,"video_recorded":false,"plaintiffs":[],"defendants":[],"deponents":[],"ordering_attorney":{},"filing_attorney":{},"copy_attorneys":[],"ordered_by":null,"reporter_name":null,"reporter_csr":null,"reporter_firm":null,"reporter_address":null,"vocabulary_terms":[],"all_proper_nouns":[],"confirmed_spellings":{}}'
                    )
                ]
            )

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key
            self.messages = _FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", " test-key ")
    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic)
    )

    result = parse_intake_document(
        "ignored.pdf",
        extracted_text=(
            "Cause No. 2025-CI-19595\n"
            "Notice of Deposition of Matthew Coger.\n"
            "This packet contains enough text to avoid scanned-PDF fallback."
        ),
    )

    assert result is not None
    assert captured["api_key"] == "test-key"


def test_parse_intake_document_builds_speaker_map_and_entity_counts(monkeypatch):
    response_json = json_text = (
        '{"cause_number":"01-25-0000-4994","court":null,"case_style":null,'
        '"deposition_date":"04/08/2026","deposition_method":"Via Zoom",'
        '"subpoena_duces_tecum":false,"amendment":null,"read_and_sign":false,'
        '"signature_waived":false,"video_recorded":true,'
        '"plaintiffs":["Basilio Gonzales"],'
        '"defendants":["Rentokil North America Inc"],'
        '"deponents":[{"name":"Chris Epley","role":"deponent"}],'
        '"ordering_attorney":{"name":"Juan Munoz Zarate","firm":"Injury Law Guides"},'
        '"filing_attorney":{"name":"Juan M. Muñoz","firm":"Ford & Harrison LLP"},'
        '"copy_attorneys":[{"name":"Willard W. Clark III","firm":"Ford & Harrison LLP"}],'
        '"ordered_by":"SA Legal Solutions","reporter_name":"Miah Bardot",'
        '"reporter_csr":null,"reporter_firm":"SA Legal Solutions","reporter_address":null,'
        '"vocabulary_terms":['
        '{"term":"Chris Epley","term_type":"PERSON","field_name":"deponent","reason":"name"},'
        '{"term":"Ford & Harrison LLP","term_type":"COMPANY","field_name":"firm","reason":"firm"}'
        "],"
        '"all_proper_nouns":["Chris Epley","Ford & Harrison LLP","Texas Rule of Civil Procedure 199.2(b)(1)"],'
        '"confirmed_spellings":{"Munoz":"Muñoz"}}'
    )

    class _FakeMessages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text=json_text)])

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic)
    )

    result = parse_intake_document(
        "ignored.pdf",
        extracted_text=(
            "Claimant Basilio Gonzales.\n"
            "Respondent Rentokil North America Inc.\n"
            "Deponent Chris Epley.\n"
            "Pursuant to the Texas Rule of Civil Procedure 199.2(b)(1).\n"
            "Zoom Video Deposition on 04/08/2026 at 9:30 AM."
        ),
    )

    assert result is not None
    assert result.speaker_map_suggestion["deponent"] == "Chris Epley"
    assert result.speaker_map_suggestion["witness"] == "Chris Epley"
    assert result.speaker_map_suggestion["claimant"] == "Basilio Gonzales"
    assert result.speaker_map_suggestion["respondent"] == "Rentokil North America Inc"
    assert result.speaker_map_suggestion["ordering_attorney"] == "Juan Munoz Zarate"
    assert result.entity_counts["people"] >= 4
    assert result.entity_counts["orgs"] >= 2
    assert result.entity_counts["roles"] >= 2
    assert result.entity_counts["legal_phrases"] >= 2
    assert result.entity_counts["dates"] == 1
    assert result.entity_counts["times"] == 1
    assert result.entity_counts["keyterms"] == 3


def test_parse_intake_document_builds_structured_keyterm_map(monkeypatch):
    json_text = (
        '{"cause_number":"2024-CI-27841","court":"In the 131st Judicial District Court of Bexar County, Texas",'
        '"case_style":"Jaypee Ascuncion v. Gregory Ernest Stone",'
        '"deposition_date":"04/22/2026","deposition_method":"Via Zoom",'
        '"subpoena_duces_tecum":false,"amendment":null,"read_and_sign":false,'
        '"signature_waived":false,"video_recorded":false,'
        '"plaintiffs":["Jaypee Ascuncion","Joanna Ascuncion"],'
        '"defendants":["Gregory Ernest Stone"],'
        '"deponents":[{"name":"Gregory Ernest Stone","role":"deponent"}],'
        '"ordering_attorney":{"name":"Thomas D. Jones","firm":"Law Offices of Thomas D. Jones, P.C."},'
        '"filing_attorney":{"name":"Hector M. Benavides","firm":"Holly D Shull & Associates"},'
        '"copy_attorneys":[],"ordered_by":"SA Legal Solutions","reporter_name":"Miah Bardot",'
        '"reporter_csr":null,"reporter_firm":"SA Legal Solutions","reporter_address":null,'
        '"vocabulary_terms":[],'
        '"all_proper_nouns":["Gregory Ernest Stone","Thomas D. Jones","Hector M. Benavides","Bexar County"],'
        '"confirmed_spellings":{}}'
    )

    class _FakeMessages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text=json_text)])

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic)
    )

    result = parse_intake_document(
        "ignored.pdf",
        extracted_text="CAUSE NO. 2024-CI-27841\nBEXAR COUNTY, TEXAS\nGREGORY ERNEST STONE",
    )

    assert result is not None
    assert result.keyterm_map["names"]["stone"] == "Gregory Ernest Stone"
    assert result.keyterm_map["names"]["jones"] == "Thomas D. Jones"
    assert result.keyterm_map["names"]["benavides"] == "Hector M. Benavides"
    assert result.keyterm_map["locations"]["bear county"] == "Bexar County"
    assert result.keyterm_map["legal"]["cost number"] == "Cause Number"
