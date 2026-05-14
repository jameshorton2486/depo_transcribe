"""
Thomas baseline regression test.

A high-level transcript sanity check. Asserts that pipeline output
for the Thomas case still has sane high-level properties. Catches
catastrophic damage (large word loss, transcript-assembly collapse,
witness name rewritten, all speakers merged, etc.) without trying
to validate every detail.

Reads two artifacts from a completed Thomas case folder:

- The Phase A immutable raw response (raw_dg_response_*.json)
- The main pipeline output JSON (case base name + timestamp .json,
  excluding _raw variants)

The case folder is supplied via the THOMAS_CASE_DIR environment
variable. If unset, the test skips with a clear message - it does
not fail. Skipping keeps the dev loop fast for anyone not working
on the Thomas case.

Tolerances are calibrated to the actual Thomas case. If a deliberate
pipeline change legitimately moves a constant, update the constant
in the same commit that makes the pipeline change.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Calibrated to the current Thomas case output (13,598 words,
# 1,016 utterances). Rounded baselines are deliberate: this is a
# smoke alarm, not a forensic pin.
EXPECTED_WORD_COUNT = 13500
WORD_COUNT_TOLERANCE = 0.05
EXPECTED_MIN_UTTERANCES = 500
EXPECTED_MIN_TRANSCRIPT_CHARS = 1000
EXPECTED_MIN_SPEAKERS = 2
REQUIRED_PHRASES = (
    "Heath Thomas",
    "25CV00598OLG",
    "Miah Bardot",
)


def _case_dir() -> Path | None:
    raw = os.environ.get("THOMAS_CASE_DIR", "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def _find_raw_response(case_dir: Path) -> Path | None:
    matches = sorted((case_dir / "Deepgram").glob("raw_dg_response_*.json"))
    return matches[-1] if matches else None


def _find_main_output(case_dir: Path) -> Path | None:
    candidates = [
        p for p in (case_dir / "Deepgram").glob("*.json")
        if "_raw" not in p.name
        and not p.name.startswith("raw_dg_response_")
        and p.name != "raw_deepgram.json"
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]


@pytest.fixture(scope="module")
def thomas_output() -> dict:
    case_dir = _case_dir()
    if case_dir is None:
        pytest.skip(
            "THOMAS_CASE_DIR not set or path missing. "
            "Set to a completed Thomas case folder to run this test."
        )
    main_path = _find_main_output(case_dir)
    if main_path is None:
        pytest.skip(f"No main output JSON found in {case_dir / 'Deepgram'}")
    return json.loads(main_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def thomas_raw() -> dict:
    case_dir = _case_dir()
    if case_dir is None:
        pytest.skip("THOMAS_CASE_DIR not set.")
    raw_path = _find_raw_response(case_dir)
    if raw_path is None:
        pytest.skip(
            f"No raw_dg_response_*.json found in {case_dir / 'Deepgram'}. "
            "Run a fresh pipeline pass to produce the Phase A artifact."
        )
    return json.loads(raw_path.read_text(encoding="utf-8"))


def test_word_count_within_tolerance(thomas_output: dict) -> None:
    """Catastrophic word loss check. +/-5% of expected - outside this
    band means something dropped or duplicated a meaningful chunk
    of the transcript."""
    words = thomas_output.get("words") or []
    actual = len(words)
    low = EXPECTED_WORD_COUNT * (1 - WORD_COUNT_TOLERANCE)
    high = EXPECTED_WORD_COUNT * (1 + WORD_COUNT_TOLERANCE)
    assert low <= actual <= high, (
        f"Word count {actual} outside tolerance band "
        f"[{low:.0f}, {high:.0f}] around expected "
        f"{EXPECTED_WORD_COUNT}. Catastrophic loss or unexpected "
        f"expansion."
    )


def test_utterance_count_nonzero(thomas_output: dict) -> None:
    """Atomization-drift smoke check. We don't pin an exact upper
    bound (atomization would push this number very high) but we
    require a sane minimum so total collapse is caught."""
    utterances = thomas_output.get("utterances") or []
    assert len(utterances) >= EXPECTED_MIN_UTTERANCES, (
        f"Only {len(utterances)} utterances; expected at least "
        f"{EXPECTED_MIN_UTTERANCES}. Possible total collapse."
    )


def test_transcript_assembled(thomas_output: dict) -> None:
    """Assembly-collapse check. Word objects can exist and the test
    above can pass while the joined transcript string is empty or
    near-empty - for example if a future change breaks the
    word-list-to-transcript join. This catches that failure mode."""
    transcript = (thomas_output.get("transcript") or "").strip()
    assert len(transcript) >= EXPECTED_MIN_TRANSCRIPT_CHARS, (
        f"Transcript text is only {len(transcript)} chars; expected "
        f"at least {EXPECTED_MIN_TRANSCRIPT_CHARS}. Word objects "
        f"may have survived but transcript assembly likely failed."
    )


def test_required_phrases_present(thomas_output: dict) -> None:
    """Transcript-corruption check. If the witness name, case
    number, or reporter identity is missing, something rewrote
    content that must not be rewritten."""
    transcript = thomas_output.get("transcript") or ""
    missing = [p for p in REQUIRED_PHRASES if p not in transcript]
    assert not missing, (
        f"Required phrases missing from transcript: {missing}. "
        f"Transcript-content corruption suspected."
    )


def test_timeline_sane(thomas_output: dict) -> None:
    """Timestamp-damage check. First word starts in the first
    few minutes, last word starts well after that, both are
    positive floats. The Thomas baseline does not start near zero,
    so this checks for non-collapsed monotonic timeline shape rather
    than zero-based normalization."""
    words = thomas_output.get("words") or []
    assert words, "No words in output - cannot check timeline."
    first = words[0]
    last = words[-1]
    first_start = float(first.get("start", -1))
    last_start = float(last.get("start", -1))
    assert 0.0 <= first_start < 300.0, (
        f"First word start {first_start} not in [0, 300). "
        f"Timeline likely damaged."
    )
    assert last_start > first_start + 60.0, (
        f"Last word start {last_start} not at least 60 seconds past "
        f"first word start {first_start}. "
        f"Transcript truncated or timeline collapsed."
    )


def test_speaker_diarization_sanity(thomas_raw: dict) -> None:
    """Diarization-collapse check. Uses Phase A raw response so this
    is independent of any downstream smoothing. Requires at least
    EXPECTED_MIN_SPEAKERS distinct speaker IDs across all chunks."""
    speakers: set[int] = set()
    for chunk in thomas_raw.get("chunks") or []:
        dg = chunk.get("deepgram_response") or {}
        channels = (dg.get("results") or {}).get("channels") or []
        if not channels:
            continue
        alts = (channels[0] or {}).get("alternatives") or []
        if not alts:
            continue
        for word in (alts[0] or {}).get("words") or []:
            speaker = word.get("speaker")
            if isinstance(speaker, int):
                speakers.add(speaker)
    assert len(speakers) >= EXPECTED_MIN_SPEAKERS, (
        f"Only {len(speakers)} distinct speakers in raw response "
        f"(expected at least {EXPECTED_MIN_SPEAKERS}). "
        f"Diarization collapsed."
    )
