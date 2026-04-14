from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.pdf_extractor import extract_from_filename, extract_case_info_from_pdf


def test_extract_from_filename_supports_legacy_date_prefix():
    result = extract_from_filename("03-24-26 Matthew Coger 01_1.wav")

    assert result["witness_first"] == ("Matthew", "filename")
    assert result["witness_last"] == ("Coger", "filename")


def test_extract_from_filename_supports_modern_iso_date_prefix_with_suffix():
    result = extract_from_filename("2026-04-09- Bianca Caram md.mp4")

    assert result["witness_first"] == ("Bianca", "filename")
    assert result["witness_last"] == ("Caram", "filename")


def test_extract_from_filename_does_not_set_date_from_audio_filename():
    result = extract_from_filename("2026-04-09- Bianca Caram md.mp4")

    assert result["date"] == (None, "failed")


def test_extract_case_info_from_pdf_uses_regex_case_vocab_fallback(monkeypatch):
    sample_text = """
    CASE NO. 01-25-0000-4994
    BASILIO GONZALES, Claimant
    RENTOKIL NORTH AMERICA INC, Respondent
    JUAN M. MUÑOZ
    """

    monkeypatch.setattr("core.pdf_extractor.extract_pdf_text", lambda _path: sample_text)
    monkeypatch.setattr("core.intake_parser.parse_intake_document", lambda *args, **kwargs: None)

    result = extract_case_info_from_pdf("ignored.pdf")

    assert "Basilio Gonzales" in result["keyterms"]
    assert result["confirmed_spellings"]["Juan M. Munoz"] == "Juan M. Muñoz"
    assert result["intake_entity_counts"]["People"] >= 2


def test_extract_case_info_from_pdf_uses_intake_deponent_for_first_and_last_name(monkeypatch):
    sample_text = (
        "Notice of deposition for Chris Epley in Cause Number 2025-CI-19595 "
        "scheduled for April 8, 2026 before the court reporter."
    )
    intake_result = SimpleNamespace(
        cause_number="2025-CI-19595",
        deponents=[{"name": "Chris Epley"}],
        deposition_date="04/08/2026",
        all_proper_nouns=["Chris Epley"],
        confirmed_spellings={},
        speaker_map_suggestion={"witness": "Chris Epley"},
        entity_counts={"people": 1},
    )

    monkeypatch.setattr("core.pdf_extractor.extract_pdf_text", lambda _path: sample_text)
    monkeypatch.setattr("core.intake_parser.parse_intake_document", lambda *args, **kwargs: intake_result)

    result = extract_case_info_from_pdf("ignored.pdf")

    assert result["witness_first"] == ("Chris", "ai")
    assert result["witness_last"] == ("Epley", "ai")
