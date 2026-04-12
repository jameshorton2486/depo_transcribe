from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.case_vocab import build_case_vocab_from_text, f1, precision, recall


SAMPLE_TEXT = """
FIRST AMENDED NOTICE OF INTENT TO TAKE ZOOM VIDEO DEPOSITION
BASILIO GONZALES, Claimant
v. CASE NO. 01-25-0000-4994
RENTOKIL NORTH AMERICA INC, Respondent
Pursuant to the Texas Rule of Civil Procedure 199.2(b)(1) ...
Respectfully submitted,
JUAN M. MUÑOZ
WILLARD W. CLARK III
San Antonio, TX
"""


def test_build_case_vocab_extracts_keyterms_and_counts():
    result = build_case_vocab_from_text(SAMPLE_TEXT)

    assert "Basilio Gonzales" in result["deepgram_keyterms"]
    assert "Rentokil North America Inc" in result["deepgram_keyterms"]
    assert result["counts"]["People"] >= 3
    assert result["counts"]["Legal Phrases"] >= 3


def test_build_case_vocab_preserves_diacritic_spellings_via_alias_map():
    result = build_case_vocab_from_text("JUAN M. MUÑOZ")

    assert result["confirmed_spellings"]["Juan M. Munoz"] == "Juan M. Muñoz"


def test_metrics_compute_expected_values():
    extracted = ["A", "B", "C"]
    gold = ["A", "B", "D"]

    p = precision(extracted, gold)
    r = recall(extracted, gold)

    assert p == 2 / 3
    assert r == 2 / 3
    assert f1(p, r) == 2 / 3
