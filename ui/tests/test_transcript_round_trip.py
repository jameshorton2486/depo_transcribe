"""
Round-trip invariant tests for TranscriptTab.

These tests guard the two contracts that CLAUDE.md §16 and §17 protect:

  §16  _render_with_confidence applies color tags ONLY. It must never
       replace textbox content. Doing so corrupts the file on save.

  §17  _save_transcript saves _canonical_text, not textbox content.
       The two differ during confidence highlighting and edit mode.

A future repack of the Transcript tab (e.g. wrapping the textbox in a
side-rail container) must keep these invariants. This file is the
safety net: if a layout change breaks either contract, one of these
tests fails immediately.

Tests are split between method-level (using SimpleNamespace stubs, no
Tk root needed) and textbox-level (using a real CTkTextbox to verify
tag application doesn't mutate text). The real-textbox fixture is
module-scoped because creating/destroying multiple CTk roots in one
pytest session intermittently fails to find tk.tcl on Windows.
"""

import customtkinter as ctk
import pytest

from types import SimpleNamespace
from pathlib import Path

from ui.tab_transcript import TranscriptTab


# ── Sample content ───────────────────────────────────────────────────────────

SAMPLE_TRANSCRIPT = (
    "\t\t\tTHE REPORTER:  This is Cause Number 2025-CI-19595.\n"
    "\n"
    "\tQ.  Did you go there?\n"
    "\tA.  Yes, sir.\n"
)


# ── Stub-only tests (no Tk root) ─────────────────────────────────────────────

class _StubBtn:
    def __init__(self):
        self.calls = []

    def configure(self, **kwargs):
        self.calls.append(kwargs)


class _StubLabel:
    def __init__(self):
        self.calls = []

    def configure(self, **kwargs):
        self.calls.append(kwargs)


class _StubTextbox:
    """A textbox whose .get() returns garbage — proves the save path
    reads from _canonical_text, not from this widget."""

    def __init__(self, fake_content="GARBAGE FROM TEXTBOX"):
        self._content = fake_content

    def get(self, _start, _end):
        return self._content


def _make_save_fake(canonical_text, tmp_path: Path, *, textbox_content="GARBAGE FROM TEXTBOX"):
    save_path = tmp_path / "out.txt"
    fake = SimpleNamespace(
        _canonical_text=canonical_text,
        _textbox=_StubTextbox(textbox_content),
        _save_btn=_StubBtn(),
        _path_label=_StubLabel(),
        _save_target_path=lambda: str(save_path),
        after=lambda _delay, _fn: None,
    )
    return fake, save_path


def test_save_writes_canonical_text_not_textbox(tmp_path):
    fake, save_path = _make_save_fake(SAMPLE_TRANSCRIPT, tmp_path)
    TranscriptTab._save_transcript(fake)
    assert save_path.read_text(encoding="utf-8") == SAMPLE_TRANSCRIPT


def test_save_ignores_textbox_garbage_when_canonical_set(tmp_path):
    # The whole point of the canonical-text contract: even if a future
    # bug causes _textbox.get to return wrong content (e.g. confidence
    # rendering accidentally replaced text), the saved file must still
    # match _canonical_text.
    fake, save_path = _make_save_fake(SAMPLE_TRANSCRIPT, tmp_path,
                                      textbox_content="CORRUPTED BY A REGRESSION")
    TranscriptTab._save_transcript(fake)
    assert "CORRUPTED" not in save_path.read_text(encoding="utf-8")


def test_save_falls_back_to_textbox_only_when_canonical_empty(tmp_path):
    # Documents the existing fallback. _canonical_text == "" or None
    # => textbox content is the source of truth (last-ditch).
    fake, save_path = _make_save_fake("", tmp_path,
                                      textbox_content="from textbox")
    TranscriptTab._save_transcript(fake)
    # textbox content gets saved.
    assert "from textbox" in save_path.read_text(encoding="utf-8")


def test_save_no_target_path_is_a_no_op(tmp_path):
    fake = SimpleNamespace(
        _canonical_text=SAMPLE_TRANSCRIPT,
        _textbox=_StubTextbox(),
        _save_btn=_StubBtn(),
        _path_label=_StubLabel(),
        _save_target_path=lambda: None,
        after=lambda _delay, _fn: None,
    )
    # Must not raise, must not write anywhere.
    TranscriptTab._save_transcript(fake)
    assert fake._save_btn.calls == []


def test_save_round_trip_byte_identical(tmp_path):
    # Write known content to disk, "load" it (read it as canonical),
    # then save back to a different file. The two files must be
    # byte-identical — no quoting, normalization, or BOM mutation.
    src = tmp_path / "src.txt"
    src.write_text(SAMPLE_TRANSCRIPT, encoding="utf-8")
    canonical = src.read_text(encoding="utf-8")
    fake, save_path = _make_save_fake(canonical, tmp_path)
    TranscriptTab._save_transcript(fake)
    assert save_path.read_bytes() == src.read_bytes()


# ── Real-textbox tests ───────────────────────────────────────────────────────

# `root` fixture is supplied by ui/tests/conftest.py at session scope.


def _make_render_fake(textbox, canonical):
    """Build a stub TranscriptTab that exposes just enough surface for
    _apply_confidence_tags to run end-to-end against a real textbox."""
    highlight_var = SimpleNamespace(get=lambda: True)
    fake = SimpleNamespace(
        _textbox=textbox,
        _canonical_text=canonical,
        _word_map=[],
        review_state={},
        _highlight_var=highlight_var,
    )
    # Bind the methods that _apply_confidence_tags reaches through self
    # so they operate on `fake`. These are the same methods the real
    # tab uses — we are exercising the production code paths, not
    # reimplementing them in the test.
    fake._apply_confidence_tags = lambda words: TranscriptTab._apply_confidence_tags(fake, words)
    fake._apply_confidence_highlights = lambda: TranscriptTab._apply_confidence_highlights(fake)
    fake._apply_speaker_label_colors = lambda: TranscriptTab._apply_speaker_label_colors(fake)
    fake._iter_pending_confidence_items = lambda: TranscriptTab._iter_pending_confidence_items(fake)
    fake._is_confidence_stop_word = lambda tok: TranscriptTab._is_confidence_stop_word(fake, tok)
    fake._normalize_confidence_token = TranscriptTab._normalize_confidence_token
    return fake


def _build_textbox(root, content):
    tb = ctk.CTkTextbox(root)
    tb.insert("1.0", content)
    return tb


def test_render_with_confidence_does_not_mutate_textbox(root):
    tb = _build_textbox(root, SAMPLE_TRANSCRIPT)
    fake = _make_render_fake(tb, SAMPLE_TRANSCRIPT)
    # Snapshot the textbox content before tag application.
    before = tb.get("1.0", "end-1c")
    TranscriptTab._render_with_confidence(fake, [])
    after = tb.get("1.0", "end-1c")
    assert after == before


def test_render_with_confidence_preserves_canonical_text(root):
    tb = _build_textbox(root, SAMPLE_TRANSCRIPT)
    fake = _make_render_fake(tb, SAMPLE_TRANSCRIPT)
    TranscriptTab._render_with_confidence(fake, [])
    # _canonical_text is the source of truth for save; render must not
    # touch it under any code path.
    assert fake._canonical_text == SAMPLE_TRANSCRIPT


def test_confidence_tags_cover_expected_char_ranges(root):
    tb = _build_textbox(root, SAMPLE_TRANSCRIPT)
    fake = _make_render_fake(tb, SAMPLE_TRANSCRIPT)
    # Place a low-confidence span over the word "Cause" (chars 21..26).
    cause_start = SAMPLE_TRANSCRIPT.index("Cause")
    cause_end = cause_start + len("Cause")
    fake._word_map = [
        {
            "word": "Cause",
            "char_start": cause_start,
            "char_end": cause_end,
            "confidence": 0.40,  # below CONFIDENCE_RED_THRESHOLD
        }
    ]
    TranscriptTab._render_with_confidence(fake, [])
    # The tag must wrap exactly the "Cause" range. Tk reports tag ranges
    # as a flat tuple of (start, end, start, end, ...) Tcl indices.
    inner = tb._textbox
    ranges = inner.tag_ranges("conf_low")
    assert len(ranges) == 2  # one (start, end) pair
    tagged = inner.get(ranges[0], ranges[1])
    assert tagged == "Cause"


def test_full_round_trip_load_render_save(tmp_path, root):
    # Full round-trip: write to disk → load into textbox + canonical →
    # apply confidence tags → save → reload from disk. The reloaded
    # bytes must equal the originally-written bytes, and the textbox
    # content must still equal canonical at every step.
    src = tmp_path / "src.txt"
    src.write_text(SAMPLE_TRANSCRIPT, encoding="utf-8")
    loaded = src.read_text(encoding="utf-8")

    tb = _build_textbox(root, loaded)
    render_fake = _make_render_fake(tb, loaded)
    TranscriptTab._render_with_confidence(render_fake, [])
    # tb.get("1.0", "end-1c") strips only Tk's auto-appended trailing
    # newline, leaving the original SAMPLE_TRANSCRIPT (which itself ends
    # with "\n").
    assert tb.get("1.0", "end-1c") == SAMPLE_TRANSCRIPT

    save_fake, save_path = _make_save_fake(render_fake._canonical_text, tmp_path)
    TranscriptTab._save_transcript(save_fake)
    assert save_path.read_bytes() == src.read_bytes()
