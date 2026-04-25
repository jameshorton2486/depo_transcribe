"""
Persistence tests for the Transcript tab review-state intelligence.

The Run Corrections pipeline reloads the transcript and word data, which
triggers TranscriptTab._restore_review_state(). That method must preserve
"confirmed"/"corrected" state for words whose Deepgram (start, end)
timestamps are unchanged across the reload, and must drop state for words
that were removed.

These tests exercise _restore_review_state directly with a SimpleNamespace
stand-in for `self`, so the full UI does not need to be instantiated.
"""

from types import SimpleNamespace

from ui.tab_transcript import TranscriptTab


def _make_fake_tab(words, review_state):
    """Build a minimal stand-in for `self` that _restore_review_state needs."""
    fake = SimpleNamespace(_words=list(words), review_state=dict(review_state))
    # Bind the bound-method dependencies so _restore_review_state can call
    # self._is_confidence_stop_word, self._normalize_confidence_token, and
    # self._review_key without instantiating the full TranscriptTab class.
    fake._normalize_confidence_token = TranscriptTab._normalize_confidence_token  # static
    fake._is_confidence_stop_word = lambda tok: TranscriptTab._is_confidence_stop_word(fake, tok)
    fake._review_key = TranscriptTab._review_key  # static
    return fake


def _word(text, start, end, confidence):
    return {"word": text, "start": start, "end": end, "confidence": confidence}


def test_restore_review_state_preserves_confirmed_after_reload():
    """A word marked 'confirmed' before reload must stay 'confirmed' if its
    (start, end) timestamps come back unchanged - the Run Corrections case."""
    old_words = [
        _word("objection", 1.0, 1.5, 0.62),
        _word("hearsay", 2.0, 2.5, 0.71),
    ]
    fake = _make_fake_tab(old_words, {0: "confirmed", 1: "pending"})

    # New load returns the same Deepgram words (text rewritten by corrections,
    # but timestamps unchanged because they come from the original audio).
    new_words = [
        _word("Objection.", 1.0, 1.5, 0.62),  # text changed, timestamps same
        _word("hearsay", 2.0, 2.5, 0.71),
    ]

    TranscriptTab._restore_review_state(fake, new_words)

    assert fake.review_state[0] == "confirmed"
    assert fake.review_state[1] == "pending"


def test_restore_review_state_preserves_corrected_after_reload():
    old_words = [_word("widget", 5.0, 5.4, 0.40)]
    fake = _make_fake_tab(old_words, {0: "corrected"})

    new_words = [_word("widget", 5.0, 5.4, 0.40)]

    TranscriptTab._restore_review_state(fake, new_words)

    assert fake.review_state[0] == "corrected"


def test_restore_review_state_drops_state_for_removed_words():
    """If a flagged word disappears from the new word list (e.g., the
    correction collapsed an artifact duplicate), its prior state should not
    be carried forward to a different word."""
    old_words = [
        _word("the the", 1.0, 1.4, 0.50),  # confirmed before
        _word("courthouse", 2.0, 2.5, 0.60),
    ]
    fake = _make_fake_tab(old_words, {0: "confirmed", 1: "pending"})

    # Corrections removed the doubled word; only "courthouse" remains.
    new_words = [_word("courthouse", 2.0, 2.5, 0.60)]

    TranscriptTab._restore_review_state(fake, new_words)

    # Index 0 in the new list is the courthouse word; it should be pending.
    assert fake.review_state[0] == "pending"
    # The "the the" state at the old index 0 is gone.
    assert len(fake.review_state) == 1


def test_restore_review_state_does_not_flag_words_above_threshold():
    """Words with confidence >= CONFIDENCE_AMBER_THRESHOLD (0.75) must not
    appear in review_state at all - nothing to flag, nothing to track."""
    old_words = [_word("clear", 0.0, 0.3, 0.95)]
    fake = _make_fake_tab(old_words, {})

    new_words = [_word("clear", 0.0, 0.3, 0.95)]

    TranscriptTab._restore_review_state(fake, new_words)

    assert fake.review_state == {}


def test_restore_review_state_does_not_flag_stop_words():
    """Common stop words ('the', 'a', 'and', etc.) must never be flagged
    even if they have low confidence - they are not meaningful review
    targets."""
    old_words = [
        _word("the", 0.0, 0.2, 0.40),  # stop word, low confidence
        _word("evidence", 0.5, 1.0, 0.40),  # real word, low confidence
    ]
    fake = _make_fake_tab(old_words, {})

    new_words = list(old_words)
    TranscriptTab._restore_review_state(fake, new_words)

    # "the" must not be in review_state; "evidence" must be pending.
    assert 0 not in fake.review_state
    assert fake.review_state.get(1) == "pending"


def test_restore_review_state_handles_only_pending_words():
    """If no words were confirmed before, all flagged words come back as
    pending - which is the normal first-load case."""
    old_words = [
        _word("objection", 1.0, 1.5, 0.50),
        _word("foundation", 2.0, 2.5, 0.55),
    ]
    fake = _make_fake_tab(old_words, {0: "pending", 1: "pending"})

    new_words = list(old_words)
    TranscriptTab._restore_review_state(fake, new_words)

    assert fake.review_state == {0: "pending", 1: "pending"}


def test_restore_review_state_rolls_back_on_failure():
    """If anything in the alignment loop raises, the saved review_state
    must be restored - the reviewer's confirmed/corrected decisions are
    not allowed to silently disappear."""
    old_words = [_word("objection", 1.0, 1.5, 0.62)]
    fake = _make_fake_tab(old_words, {0: "confirmed"})

    # Pass a malformed words list that will blow up float() conversion
    # inside the loop. The saved {0: 'confirmed'} state must come back.
    new_words = [{"word": "objection", "start": 1.0, "end": 1.5, "confidence": "not-a-float"}]

    TranscriptTab._restore_review_state(fake, new_words)

    assert fake.review_state == {0: "confirmed"}
