"""
Headless tests for the Remaining ↔ Done pill toggle in
TranscriptTab._update_review_counts.

When every flagged word has been reviewed, the amber Remaining pill is
swapped for the emerald Done pill — that restores the explicit
"you're done" signal that the prior single-label scheme conveyed via
text_color cycling.

Tests use SimpleNamespace stubs that record pack / pack_forget /
.configure(text=...) calls so the full UI is not required.
"""

from types import SimpleNamespace

from ui.tab_transcript import TranscriptTab


class _StubLabel:
    def __init__(self):
        self.text = None

    def configure(self, *, text):
        self.text = text


class _StubPill:
    def __init__(self):
        self.text_label = _StubLabel()
        self.packed = False
        self.pack_calls = 0
        self.forget_calls = 0

    def pack(self, **_kwargs):
        self.packed = True
        self.pack_calls += 1

    def pack_forget(self):
        self.packed = False
        self.forget_calls += 1


def _make_fake_tab():
    return SimpleNamespace(
        _pill_flagged=_StubPill(),
        _pill_reviewed=_StubPill(),
        _pill_remaining=_StubPill(),
        _pill_done=_StubPill(),
    )


def test_idle_state_shows_remaining_not_done():
    fake = _make_fake_tab()
    TranscriptTab._update_review_counts(fake, flagged=0, reviewed=0, remaining=0)
    assert fake._pill_remaining.packed is True
    assert fake._pill_done.packed is False


def test_active_review_shows_remaining_not_done():
    fake = _make_fake_tab()
    TranscriptTab._update_review_counts(fake, flagged=10, reviewed=3, remaining=7)
    assert fake._pill_remaining.packed is True
    assert fake._pill_done.packed is False


def test_completion_swaps_remaining_for_done():
    fake = _make_fake_tab()
    TranscriptTab._update_review_counts(fake, flagged=10, reviewed=10, remaining=0)
    assert fake._pill_remaining.packed is False
    assert fake._pill_done.packed is True


def test_zero_flagged_keeps_remaining_visible_no_done():
    # No flags ever raised — not a "completion" event, just an empty doc.
    # Remaining stays so the pill row keeps a consistent shape.
    fake = _make_fake_tab()
    TranscriptTab._update_review_counts(fake, flagged=0, reviewed=0, remaining=0)
    assert fake._pill_done.packed is False


def test_remaining_text_updates_when_visible():
    fake = _make_fake_tab()
    TranscriptTab._update_review_counts(fake, flagged=10, reviewed=3, remaining=7)
    assert fake._pill_remaining.text_label.text == "Remaining: 7"


def test_remaining_text_not_updated_after_completion():
    # Once swapped to Done, the Remaining text isn't refreshed because
    # the pill is hidden. The next non-completion update will re-pack
    # remaining and refresh its text.
    fake = _make_fake_tab()
    fake._pill_remaining.text_label.text = "Remaining: 5"  # prior state
    TranscriptTab._update_review_counts(fake, flagged=10, reviewed=10, remaining=0)
    assert fake._pill_remaining.text_label.text == "Remaining: 5"


def test_completion_then_new_flag_re_packs_remaining():
    fake = _make_fake_tab()
    TranscriptTab._update_review_counts(fake, flagged=10, reviewed=10, remaining=0)
    assert fake._pill_done.packed is True
    TranscriptTab._update_review_counts(fake, flagged=12, reviewed=10, remaining=2)
    assert fake._pill_remaining.packed is True
    assert fake._pill_done.packed is False
    assert fake._pill_remaining.text_label.text == "Remaining: 2"


def test_flagged_and_reviewed_pills_always_get_text_updates():
    fake = _make_fake_tab()
    TranscriptTab._update_review_counts(fake, flagged=10, reviewed=10, remaining=0)
    assert fake._pill_flagged.text_label.text == "Flagged: 10"
    assert fake._pill_reviewed.text_label.text == "Reviewed: 10"


def test_no_pill_flagged_attribute_is_safe():
    # Mirrors the early-init guard. If _build_ui hasn't run, the call
    # must not raise.
    fake = SimpleNamespace()
    TranscriptTab._update_review_counts(fake, flagged=0, reviewed=0, remaining=0)
