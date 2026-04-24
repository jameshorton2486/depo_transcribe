from ui.tab_transcript import (
    _apply_speaker_map_to_text,
    _build_speaker_dropdown_values,
    _build_speaker_options,
    _build_progressive_speaker_defaults,
    _choose_best_speaker_option,
    _compute_speaker_confidence,
    _confidence_label,
    _extract_speaker_ids,
    _format_attorney_dropdown_label,
    _format_speaker_option_with_confidence,
    _normalize_transcript_speaker_map,
    _strip_speaker_confidence_label,
)


def test_extract_speaker_ids_finds_unique_ids_in_order():
    text = "Speaker 2: Hello.\n\nSpeaker 0: Hi.\nSpeaker 2: Again."

    result = _extract_speaker_ids(text)

    assert result == ["0", "2"]


def test_normalize_transcript_speaker_map_handles_mixed_keys():
    result = _normalize_transcript_speaker_map({"0": "the reporter", 2: "Mr. Jones", "x": "ignored"})

    assert result == {0: "THE REPORTER", 2: "MR. JONES"}


def test_apply_speaker_map_to_text_relabels_matching_speakers_only():
    text = "Speaker 0: Opening.\n\nSpeaker 1: Yes."

    result = _apply_speaker_map_to_text(text, {0: "THE REPORTER", 1: "THE WITNESS"})

    assert result == "THE REPORTER: Opening.\n\nTHE WITNESS: Yes."


def test_build_progressive_speaker_defaults_prefers_saved_map():
    text = "Speaker 0: Opening.\nSpeaker 1: Yes."

    result = _build_progressive_speaker_defaults(
        text,
        {0: "THE REPORTER", 1: "THE WITNESS"},
        {"reporter": "Ignored Reporter"},
    )

    assert result == {
        "Speaker 0": "THE REPORTER",
        "Speaker 1": "THE WITNESS",
    }


def test_format_attorney_dropdown_label_uses_title_and_last_name():
    assert _format_attorney_dropdown_label("Ms. Jane Smith") == "MS. SMITH"


def test_build_speaker_options_uses_nod_defaults_and_counsel_names():
    config_data = {
        "ufm_fields": {
            "reporter_name": "Miah Bardot",
            "witness_name": "John Doe",
            "plaintiff_counsel": [{"name": "Hector Benavides"}],
            "defense_counsel": [{"name": "Ms. Carla Jones"}],
        }
    }

    result = _build_speaker_options(config_data)

    assert result == [
        "Select speaker...",
        "THE REPORTER",
        "THE WITNESS",
        "UNKNOWN SPEAKER",
        "MR. BENAVIDES",
        "MS. JONES",
    ]


def test_compute_speaker_confidence_marks_attorney_question_flow_high():
    config_data = {
        "ufm_fields": {
            "plaintiff_counsel": [{"name": "Hector Benavides"}],
        }
    }
    transcript_text = "Speaker 1: Did you see the accident?\n\nSpeaker 1: Where were you standing?"

    result = _compute_speaker_confidence("1", "MR. BENAVIDES", transcript_text, config_data)

    assert result == 0.8


def test_confidence_label_formats_score_bands():
    assert _confidence_label(0.8) == "High"
    assert _confidence_label(0.5) == "Medium"
    assert _confidence_label(0.1) == "Low"


def test_strip_speaker_confidence_label_returns_canonical_value():
    assert _strip_speaker_confidence_label("MR. BENAVIDES (High)") == "MR. BENAVIDES"


def test_build_speaker_dropdown_values_decorates_options_with_confidence():
    config_data = {
        "ufm_fields": {
            "witness_name": "John Doe",
        }
    }
    transcript_text = "Speaker 2: Yes.\n\nSpeaker 2: Correct."

    result = _build_speaker_dropdown_values("2", transcript_text, config_data)

    assert result == [
        "Select speaker...",
        "THE REPORTER (Low)",
        "THE WITNESS (High)",
        "UNKNOWN SPEAKER (Low)",
    ]


def test_choose_best_speaker_option_prefers_highest_scoring_label():
    config_data = {
        "ufm_fields": {
            "witness_name": "John Doe",
            "plaintiff_counsel": [{"name": "Hector Benavides"}],
        }
    }
    transcript_text = "Speaker 2: Yes.\n\nSpeaker 2: Correct."

    result = _choose_best_speaker_option("2", transcript_text, config_data)

    assert result == "THE WITNESS"


def test_format_speaker_option_with_confidence_appends_label():
    config_data = {
        "ufm_fields": {
            "plaintiff_counsel": [{"name": "Hector Benavides"}],
        }
    }
    transcript_text = "Speaker 1: Did you see the accident?"

    result = _format_speaker_option_with_confidence("1", "MR. BENAVIDES", transcript_text, config_data)

    assert result == "MR. BENAVIDES (High)"
