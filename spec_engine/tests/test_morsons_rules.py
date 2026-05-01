from spec_engine.corrections import apply_morsons_rules


def test_intro_comma():
    assert apply_morsons_rules("yes i went there") == "Yes, i went there."


def test_question_detection():
    assert apply_morsons_rules("did you go there") == "Did you go there?"


def test_stutter_fix():
    assert apply_morsons_rules("i i went there") == "I  I went there."


def test_number_start():
    assert apply_morsons_rules("2 people were there") == "Two people were there."


def test_spacing_cleanup():
    assert apply_morsons_rules("well   i went there") == "Well, i went there."


def test_ellipses_normalization():
    assert apply_morsons_rules("wait . . . what") == "Wait ... what."
    assert apply_morsons_rules("wait....") == "Wait..."


def test_em_dash_normalization():
    assert apply_morsons_rules("I went -- then left") == "I went  then left."
    assert apply_morsons_rules("I went - then left") == "I went  then left."


def test_interrogative_without_punctuation_gets_question_mark():
    assert apply_morsons_rules("who was there") == "Who was there?"
