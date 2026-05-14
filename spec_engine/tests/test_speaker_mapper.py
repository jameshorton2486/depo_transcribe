def test_normalize_directive_text_preserves_parentheticals():
    """Standalone parenthetical directives must pass through
    unchanged, since they share the directive type tag with
    BY-lines but are not BY-lines."""
    from spec_engine.speaker_mapper import normalize_directive_text

    assert normalize_directive_text("(Exhibit 1 marked)") == "(Exhibit 1 marked)"
    assert normalize_directive_text("(Recess from 1:34 p.m. to 1:35 p.m.)") == (
        "(Recess from 1:34 p.m. to 1:35 p.m.)"
    )
    # Surrounding whitespace preserved on the parenthetical path.
    assert normalize_directive_text("  (Exhibit 5 marked)  ") == "  (Exhibit 5 marked)  "
