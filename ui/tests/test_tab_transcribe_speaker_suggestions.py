from ui.tab_transcribe import (
    _build_ui_speaker_defaults,
    _build_ui_speaker_reference_text,
    _build_ui_quickfill_labels,
    _normalize_ui_speaker_map,
    _normalize_ui_speaker_suggestion,
)


def test_normalize_ui_speaker_map_handles_string_keys_and_uppercases_values():
    result = _normalize_ui_speaker_map({"0": "the reporter", 2: "Mr. Jones", "x": "ignored"})

    assert result == {0: "THE REPORTER", 2: "MR. JONES"}


def test_normalize_ui_speaker_suggestion_keeps_supported_fields_only():
    result = _normalize_ui_speaker_suggestion(
        {
            "reporter": "Miah Bardot",
            "witness": "Gregory Ernest Stone",
            "ordering_attorney": "Thomas D. Jones",
            "copy_attorneys": ["Hector M. Benavides", ""],
            "claimant": "ignored",
        }
    )

    assert result == {
        "reporter": "Miah Bardot",
        "witness": "Gregory Ernest Stone",
        "ordering_attorney": "Thomas D. Jones",
        "copy_attorneys": ["Hector M. Benavides"],
    }


def test_build_ui_speaker_defaults_prefers_exact_saved_map():
    result = _build_ui_speaker_defaults(
        ["0", "1", "2"],
        {0: "THE REPORTER", 1: "MR. BENAVIDES", 2: "THE WITNESS"},
        {"reporter": "Ignored Reporter"},
    )

    assert result == {
        "Speaker 0": "THE REPORTER",
        "Speaker 1": "MR. BENAVIDES",
        "Speaker 2": "THE WITNESS",
    }


def test_build_ui_speaker_defaults_uses_ordered_suggestions_when_no_saved_map():
    result = _build_ui_speaker_defaults(
        ["0", "1", "2"],
        {},
        {
            "reporter": "Miah Bardot",
            "ordering_attorney": "Thomas D. Jones",
            "witness": "Gregory Ernest Stone",
        },
    )

    assert result == {
        "Speaker 0": "THE REPORTER",
        "Speaker 1": "THOMAS D. JONES",
        "Speaker 2": "THE WITNESS",
    }


def test_build_ui_speaker_reference_text_includes_witness_and_attorneys():
    result = _build_ui_speaker_reference_text(
        {
            "reporter": "Miah Bardot",
            "witness": "Gregory Ernest Stone",
            "ordering_attorney": "Thomas D. Jones",
            "filing_attorney": "Hector M. Benavides",
        }
    )

    assert "Reporter: MIAH BARDOT" in result
    assert "Witness: GREGORY ERNEST STONE" in result
    assert "THOMAS D. JONES" in result
    assert "HECTOR M. BENAVIDES" in result


def test_build_ui_quickfill_labels_only_returns_canonical_safe_roles():
    result = _build_ui_quickfill_labels(
        {
            "reporter": "Miah Bardot",
            "witness": "Gregory Ernest Stone",
            "ordering_attorney": "Thomas D. Jones",
        }
    )

    assert result == ["THE REPORTER", "THE WITNESS"]
