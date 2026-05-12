from spec_engine.corrections import apply_morsons_rules


def test_intro_comma():
    assert apply_morsons_rules("yes i went there") == "Yes, i went there."


def test_question_detection():
    # Step A: terminal punctuation defaults to . only. Morson's gives
    # no rule for inferring ? from word order; the scopist flips it
    # after audio review. See docs/plans/verbatim_punctuation_plan_2026-05-12.md.
    assert apply_morsons_rules("did you go there") == "Did you go there."


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
    # Step A: -- is the canonical interruption marker per Morson's
    # Rule 85 Note. It is preserved and normalized, NEVER collapsed to
    # spaces. The earlier behavior (collapse) violated verbatim by
    # destroying the textual representation of an interruption.
    # See docs/plans/verbatim_punctuation_plan_2026-05-12.md Rule 3.
    assert apply_morsons_rules("I went -- then left") == "I went -- then left."
    # Single hyphen with spaces is no longer treated as an em-dash
    # representation. It stays as-is (or gets period-defaulted at end).
    assert apply_morsons_rules("I went - then left") == "I went - then left."


def test_interrogative_without_punctuation_gets_period():
    # Step A: terminal punctuation defaults to . only. The scopist
    # flips . to ? after audio review of inflection. See
    # docs/plans/verbatim_punctuation_plan_2026-05-12.md Rule 2.
    assert apply_morsons_rules("who was there") == "Who was there."
