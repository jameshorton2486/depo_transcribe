from spec_engine.corrections import clean_block
from spec_engine.models import JobConfig


def _cfg() -> JobConfig:
    return JobConfig()


def test_medical_injection_not_objection():
    text, _, _ = clean_block("The doctor gave a cortisone injection.", _cfg())
    assert "Objection" not in text
    assert "injection" in text.lower()


def test_curtory_to_cursory():
    text, _, _ = clean_block("Penalty of curtory.", _cfg())
    assert "cursory" in text.lower()


def test_leaving_not_global():
    text, _, _ = clean_block("Everybody was leaving work.", _cfg())
    assert "Leading" not in text
    assert "leaving work" in text.lower()


def test_mhmm_normalized():
    text, _, _ = clean_block("Mhmm.", _cfg())
    assert text == "Mm-hmm."


def test_trailer_trailer_preserved_verbatim():
    text, _, _ = clean_block("He was driving a trailer trailer.", _cfg())
    assert "tractor trailer" not in text.lower()
    assert "trailer." in text.lower()


def test_semi_trailer_trailer_is_not_rewritten():
    text, _, _ = clean_block("He was driving a semi-trailer trailer.", _cfg())
    assert "semi-trailer" in text.lower()
    assert "tractor trailer" not in text.lower()
