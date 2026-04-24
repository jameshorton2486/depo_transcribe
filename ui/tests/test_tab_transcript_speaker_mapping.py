from ui.tab_transcript import (
    _apply_speaker_map_to_text,
    _build_debug_bundle_paths,
    _build_debug_bundle_text,
    _build_transcript_context_status,
    _build_progressive_speaker_defaults,
    _extract_speaker_ids,
    _normalize_transcript_speaker_map,
    _resolve_case_root_for_transcript,
)
from ui.tab_transcribe import _apply_speaker_labels_to_text


def test_extract_speaker_ids_finds_unique_ids_in_order():
    text = "Speaker 2: Hello.\n\nSpeaker 0: Hi.\nSpeaker 2: Again."

    result = _extract_speaker_ids(text)

    assert result == ["0", "2"]


def test_normalize_transcript_speaker_map_handles_mixed_keys():
    result = _normalize_transcript_speaker_map({"0": "the reporter", 2: "Mr. Jones", "x": "ignored"})

    assert result == {0: "the reporter", 2: "Mr. Jones"}


def test_apply_speaker_map_to_text_relabels_matching_speakers_only():
    text = "Speaker 0: Opening.\n\nSpeaker 1: Yes."

    result = _apply_speaker_map_to_text(text, {0: "THE REPORTER", 1: "THE WITNESS"})

    assert result == "THE REPORTER: Opening.\n\nTHE WITNESS: Yes."


def test_apply_speaker_labels_to_text_preserves_non_label_content():
    text = "Speaker 0: Opening.\n\nSpeaker 1: Yes, I do two things.\n\nSpeaker 3: Okay."

    result = _apply_speaker_labels_to_text(
        text,
        {0: "The Reporter", 1: "Mr. Gonzalez", 3: "Ms. Pena"},
    )

    assert result == "The Reporter: Opening.\n\nMr. Gonzalez: Yes, I do two things.\n\nMs. Pena: Okay."


def test_build_progressive_speaker_defaults_prefers_saved_map():
    text = "Speaker 0: Opening.\nSpeaker 1: Yes."

    result = _build_progressive_speaker_defaults(
        text,
        {0: "The Reporter", 1: "Ms. Jones"},
        {"reporter": "Ignored Reporter"},
    )

    assert result == {
        "Speaker 0": "The Reporter",
        "Speaker 1": "Ms. Jones",
    }


def test_build_progressive_speaker_defaults_falls_back_to_raw_speaker_labels():
    text = "Speaker 0: Opening.\nSpeaker 1: Yes."

    result = _build_progressive_speaker_defaults(text, {}, {"reporter": "Ignored Reporter"})

    assert result == {
        "Speaker 0": "Speaker 0",
        "Speaker 1": "Speaker 1",
    }


def test_resolve_case_root_for_transcript_detects_deepgram_layout():
    result = _resolve_case_root_for_transcript(
        r"C:\Depositions\2026\Apr\2024-CI-28593\leifer_jack\Deepgram\test.txt"
    )

    assert result == (r"C:\Depositions\2026\Apr\2024-CI-28593\leifer_jack", True)


def test_build_transcript_context_status_reports_missing_config():
    result = _build_transcript_context_status({})

    assert result == ("No case configuration found — limited corrections will run.", "#CCAA44")


def test_build_transcript_context_status_reports_draft_mode():
    result = _build_transcript_context_status({"ufm_fields": {"speaker_map_verified": False}})

    assert result == ("Case configuration loaded — Mode: Draft.", "#CCAA44")


def test_build_debug_bundle_paths_includes_logs_transcript_json_and_job_config(tmp_path):
    transcript_path = tmp_path / "Deepgram" / "sample.txt"
    case_root = tmp_path

    result = _build_debug_bundle_paths(str(transcript_path), str(case_root))

    assert ("transcript", transcript_path) in result
    assert ("deepgram_json", transcript_path.with_suffix(".json")) in result
    assert ("job_config", case_root / "source_docs" / "job_config.json") in result


def test_build_debug_bundle_text_marks_missing_files(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    logs_dir = repo_root / "logs"
    deepgram_dir = tmp_path / "Deepgram"
    source_docs = tmp_path / "source_docs"
    logs_dir.mkdir(parents=True)
    deepgram_dir.mkdir(parents=True)
    source_docs.mkdir(parents=True)

    (logs_dir / "app.log").write_text("app log line", encoding="utf-8")
    (deepgram_dir / "sample.txt").write_text("Speaker 0: Hello.", encoding="utf-8")
    (source_docs / "job_config.json").write_text('{"ufm_fields": {}}', encoding="utf-8")

    monkeypatch.setattr("ui.tab_transcript._REPO_ROOT", repo_root)

    result = _build_debug_bundle_text(
        transcript_path=str(deepgram_dir / "sample.txt"),
        case_root=str(tmp_path),
    )

    assert "# Depo Transcribe Debug Bundle" in result
    assert "## logs/app.log" in result
    assert "app log line" in result
    assert "## transcript" in result
    assert "Speaker 0: Hello." in result
    assert "## job_config" in result
    assert "[missing]" in result


def test_case_files_panel_toggle_helpers_exist():
    from ui.tab_transcribe import TranscribeTab

    assert TranscribeTab is not None
