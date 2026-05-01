from spec_engine.corrections import apply_proper_noun_corrections


def test_apply_proper_noun_corrections_caram():
    corrections = {"karam": "Caram"}
    assert apply_proper_noun_corrections("Doctor Karam testified", corrections) == "Doctor Caram testified"


def test_apply_proper_noun_corrections_chrestman():
    corrections = {"kressman": "Chrestman"}
    assert (
        apply_proper_noun_corrections("Hannah Kressman said yes", corrections)
        == "Hannah Chrestman said yes"
    )


def test_apply_proper_noun_corrections_respects_word_boundaries():
    corrections = {"karam": "Caram"}
    assert apply_proper_noun_corrections("Karamian remained present", corrections) == "Karamian remained present"


def test_apply_proper_noun_corrections_skips_legal_terms():
    corrections = {"form": "Forme"}
    assert apply_proper_noun_corrections("Objection form", corrections) == "Objection form"
