"""Step E — production-wiring integration test.

Exercises the full path from a Deepgram-shaped JSON fixture through
``format_transcript`` (with ``deepgram_words`` populated) to the
``docx_writer`` rendering yellow-highlighted runs. This is the test
that catches a field-name mismatch between what ``inject_markers``
expects and what the JSON actually carries — the class of bug a
pure-synthetic Step C/D test can't see.

Coverage:
  1. ``load_deepgram_words_from_json`` happy path / degraded cases.
  2. End-to-end: fixture JSON -> marker injection -> mocked Anthropic
     round-trip with markers preserved -> docx_writer renders yellow
     highlights on the corresponding tokens.
  3. End-to-end with the canonical case-dir layout (
     ``{case_dir}/Deepgram/raw_deepgram.json`` per job_runner.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from docx.enum.text import WD_COLOR_INDEX

from clean_format.docx_writer import build_deposition_document
from clean_format.formatter import (
    format_transcript,
    load_deepgram_words_from_json,
)
from clean_format.low_confidence_markers import (
    LOW_CONF_CLOSE,
    LOW_CONF_OPEN,
)


FIXTURE_JSON = Path(__file__).parent / "fixtures" / "sample_raw_deepgram.json"


# ----------------------------------------------------------------------------
# load_deepgram_words_from_json
# ----------------------------------------------------------------------------


class TestLoadDeepgramWords:
    def test_happy_path_returns_words_list(self):
        words = load_deepgram_words_from_json(FIXTURE_JSON)
        assert words is not None
        assert len(words) > 0
        assert all(isinstance(w, dict) for w in words)
        # Spot-check the shape inject_markers expects.
        first = words[0]
        assert "word" in first
        assert "confidence" in first
        assert "start" in first
        assert "end" in first

    def test_fixture_includes_low_confidence_words(self):
        # The integration test relies on the fixture having tokens
        # below the default 0.85 threshold.
        words = load_deepgram_words_from_json(FIXTURE_JSON)
        assert words is not None
        low = [w for w in words if float(w["confidence"]) < 0.85]
        assert len(low) >= 2

    def test_missing_file_returns_none(self, tmp_path):
        path = tmp_path / "does_not_exist.json"
        assert load_deepgram_words_from_json(path) is None

    def test_malformed_json_returns_none(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{this is not json", encoding="utf-8")
        assert load_deepgram_words_from_json(path) is None

    def test_missing_words_key_returns_none(self, tmp_path):
        path = tmp_path / "no_words.json"
        path.write_text(json.dumps({"transcript": "hi"}), encoding="utf-8")
        assert load_deepgram_words_from_json(path) is None

    def test_empty_words_list_returns_none(self, tmp_path):
        path = tmp_path / "empty_words.json"
        path.write_text(json.dumps({"words": []}), encoding="utf-8")
        assert load_deepgram_words_from_json(path) is None

    def test_top_level_list_returns_none(self, tmp_path):
        # If someone passes the raw words array directly as a top-level
        # list, we still want None — the helper requires the dict
        # wrapping job_runner writes.
        path = tmp_path / "top_list.json"
        path.write_text(json.dumps([{"word": "hi"}]), encoding="utf-8")
        assert load_deepgram_words_from_json(path) is None


# ----------------------------------------------------------------------------
# End-to-end integration
# ----------------------------------------------------------------------------


def _build_raw_text(words: list[dict]) -> str:
    """Build the kind of raw transcript text the pipeline writes —
    speaker label + concatenated punctuated words, blank line between
    speakers."""
    blocks: dict[int, list[str]] = {}
    order: list[int] = []
    for w in words:
        speaker = int(w.get("speaker", 0))
        if speaker not in blocks:
            blocks[speaker] = []
            order.append(speaker)
        blocks[speaker].append(w.get("punctuated_word", w["word"]))
    return "\n\n".join(
        f"Speaker {sp}: {' '.join(blocks[sp])}" for sp in order
    )


class _FakeMessages:
    """Echo back the chunk content as the model response — simulates a
    well-behaved Anthropic that preserves markers exactly."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = kwargs["messages"][0]["content"]
        # Extract the transcript chunk portion from the user message.
        marker = "Transcript chunk "
        body_start = content.find(marker)
        if body_start == -1:
            text = content
        else:
            newline = content.find("\n", body_start)
            text = content[newline + 1 :].rstrip()
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def _case_meta() -> dict:
    return {
        "cause_number": "DC-25-13430",
        "court": "191st District Court",
        "county": "Dallas",
        "judicial_district": "191ST",
        "deposition_date": "2026-05-12",
        "witness_name": "Bianca Caram",
        "plaintiff_name": "Maria Lopez",
        "defendant_names": ["Acme Medical Group"],
        "reporter_name": "Miah Bardot",
        "attorneys": [
            {"name": "Emily Johnson", "role": "defendant", "city": "Houston"},
        ],
    }


class TestEndToEndWiring:
    def test_format_transcript_injects_markers_from_fixture(self):
        words = load_deepgram_words_from_json(FIXTURE_JSON)
        assert words is not None
        raw_text = _build_raw_text(words)
        client = _FakeClient()

        format_transcript(raw_text, _case_meta(), client=client, deepgram_words=words)

        sent = client.messages.calls[0]["messages"][0]["content"]
        # Marker characters present in the sent message.
        assert LOW_CONF_OPEN in sent
        # The low-confidence tokens from the fixture get wrapped.
        assert f"{LOW_CONF_OPEN}Acebo{LOW_CONF_CLOSE}" in sent
        assert f"{LOW_CONF_OPEN}Cesar{LOW_CONF_CLOSE}" in sent

    def test_format_transcript_returns_marker_bearing_text(self):
        words = load_deepgram_words_from_json(FIXTURE_JSON)
        assert words is not None
        raw_text = _build_raw_text(words)

        result = format_transcript(
            raw_text, _case_meta(), client=_FakeClient(), deepgram_words=words
        )
        # Markers survive the echo round-trip through _postprocess.
        assert f"{LOW_CONF_OPEN}Acebo{LOW_CONF_CLOSE}" in result
        assert f"{LOW_CONF_OPEN}Cesar{LOW_CONF_CLOSE}" in result

    def test_full_pipeline_renders_yellow_highlights_in_docx(self):
        """Load fixture -> format_transcript with deepgram_words ->
        write_deposition_docx -> the rendered DOCX has yellow runs on
        the low-confidence tokens."""
        words = load_deepgram_words_from_json(FIXTURE_JSON)
        assert words is not None
        raw_text = _build_raw_text(words)

        # Format with the mocked echo client so markers survive.
        formatted = format_transcript(
            raw_text, _case_meta(), client=_FakeClient(), deepgram_words=words
        )

        document = build_deposition_document(formatted, _case_meta())

        # Collect every yellow run text across all paragraphs.
        yellow_run_texts = []
        for paragraph in document.paragraphs:
            for run in paragraph.runs:
                if run.font.highlight_color == WD_COLOR_INDEX.YELLOW:
                    yellow_run_texts.append(run.text)

        assert "Acebo" in yellow_run_texts
        assert "Cesar" in yellow_run_texts

    def test_canonical_case_dir_layout_loads_words(self, tmp_path):
        # Mirror the layout core/job_runner.py writes: the canonical
        # raw_deepgram.json sits in {case_dir}/Deepgram/.
        case_dir = tmp_path / "case"
        deepgram_dir = case_dir / "Deepgram"
        deepgram_dir.mkdir(parents=True)
        target = deepgram_dir / "raw_deepgram.json"
        target.write_bytes(FIXTURE_JSON.read_bytes())

        words = load_deepgram_words_from_json(target)
        assert words is not None
        assert len(words) >= 10

    def test_no_words_param_unchanged_when_json_missing(self, tmp_path):
        # When the CLI / UI calls load_deepgram_words_from_json on a
        # missing file, the result is None and format_transcript falls
        # back to no-marker mode without any change in behavior.
        absent = tmp_path / "missing.json"
        words = load_deepgram_words_from_json(absent)
        assert words is None

        # Sanity-check the fallthrough.
        client = _FakeClient()
        format_transcript(
            "Speaker 0: hello.", _case_meta(), client=client, deepgram_words=words
        )
        sent = client.messages.calls[0]["messages"][0]["content"]
        assert LOW_CONF_OPEN not in sent
