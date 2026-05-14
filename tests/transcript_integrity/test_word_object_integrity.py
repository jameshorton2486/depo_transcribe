"""Phase A regression baseline — word-object integrity contract.

Asserts properties of the canonical fixture captured at
``tests/fixtures/canonical_raw_fixture_phase_a/``. The fixture was
produced by a real end-to-end Etminan run on 2026-05-13 13:47:06 and
is the forensic-architecture baseline for Phase A. See
``docs/validation/IMMUTABILITY_RESULTS.md`` for the run provenance.

The Phase B baseline (Thomas 5-minute fixture, captured at
``tests/fixtures/canonical_raw_fixture/``) is a separate regression
target and is asserted by a different test module.

This module intentionally stays on the historical schema-v1 live-run
fixture. Current schema-v2 shape is asserted separately in
``tests/transcript_integrity/test_raw_store_schema_v2.py`` so the
historical forensic baseline does not get rewritten just to track an
additive storage-schema bump.

Required assertions (per the plan's word-object contract):

- No word loss at the source (immutable raw chunk-sum matches
  fixture metadata).
- No timestamp corruption (start < end for every word).
- No confidence loss (every word carries a numeric ``confidence`` in
  [0.0, 1.0]).
- No speaker corruption at the source (every word has an integer
  ``speaker``).
- Raw layer immutability — schema_version + provenance fields
  present.
- Structured-layer downstream values consistent with metadata.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "canonical_raw_fixture_phase_a"
)
RAW_RESPONSE_PATH = FIXTURE_DIR / "raw_dg_response.json"
RAW_TXT_PATH = FIXTURE_DIR / "raw_deepgram.txt"
METADATA_PATH = FIXTURE_DIR / "metadata.json"


@pytest.fixture(scope="module")
def raw_response():
    if not RAW_RESPONSE_PATH.exists():
        pytest.skip(
            f"Phase-A canonical fixture missing: {RAW_RESPONSE_PATH}. "
            "Run the Phase-A validation pass to regenerate."
        )
    return json.loads(RAW_RESPONSE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metadata():
    if not METADATA_PATH.exists():
        pytest.skip(f"Fixture metadata missing: {METADATA_PATH}")
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def _iter_native_words(raw_response):
    """Yield every word object from every chunk in the immutable raw store."""
    for chunk in raw_response.get("chunks", []):
        resp = chunk.get("deepgram_response") or {}
        results = resp.get("results", {}) or {}
        channels = results.get("channels", []) or []
        if not channels:
            continue
        alts = channels[0].get("alternatives", []) or []
        if not alts:
            continue
        for word in alts[0].get("words", []) or []:
            yield word


def _iter_native_utterances(raw_response):
    for chunk in raw_response.get("chunks", []):
        resp = chunk.get("deepgram_response") or {}
        for utt in (resp.get("results", {}) or {}).get("utterances", []) or []:
            yield utt


# ---------------------------------------------------------------------------
# Raw layer immutability — schema integrity
# ---------------------------------------------------------------------------


class TestRawLayerImmutability:
    def test_schema_version_present(self, raw_response):
        assert raw_response["schema_version"] == 1

    def test_required_provenance_fields_present(self, raw_response):
        for key in (
            "saved_at_utc",
            "saved_at_local",
            "audio_file",
            "model",
            "chunk_count",
            "chunks",
        ):
            assert key in raw_response, f"missing top-level key: {key}"

    def test_chunk_count_matches_chunks_array(self, raw_response):
        assert raw_response["chunk_count"] == len(raw_response["chunks"])

    def test_every_chunk_has_index_and_offset(self, raw_response):
        for i, chunk in enumerate(raw_response["chunks"]):
            assert chunk["index"] == i
            assert isinstance(chunk["start_seconds"], (int, float))
            assert chunk["start_seconds"] >= 0


# ---------------------------------------------------------------------------
# No word loss / timing corruption / confidence loss / speaker corruption
# at the SOURCE (i.e. inside the immutable raw)
# ---------------------------------------------------------------------------


class TestSourceWordObjectIntegrity:
    def test_total_native_word_count_matches_metadata(
        self, raw_response, metadata
    ):
        total = sum(1 for _ in _iter_native_words(raw_response))
        assert total == metadata["native_word_total"], (
            f"Word count drift in fixture: counted {total}, "
            f"metadata says {metadata['native_word_total']}"
        )

    def test_total_native_utterance_count_matches_metadata(
        self, raw_response, metadata
    ):
        total = sum(1 for _ in _iter_native_utterances(raw_response))
        assert total == metadata["native_utterance_total"]

    def test_every_word_has_required_fields(self, raw_response):
        for word in _iter_native_words(raw_response):
            for field in ("word", "start", "end", "confidence", "speaker"):
                assert field in word, f"word missing field {field}: {word}"

    def test_every_word_start_before_end(self, raw_response):
        for word in _iter_native_words(raw_response):
            start = float(word["start"])
            end = float(word["end"])
            assert start <= end, (
                f"timing corruption: start={start} > end={end} "
                f"for word={word.get('word')!r}"
            )

    def test_every_word_confidence_in_range(self, raw_response):
        for word in _iter_native_words(raw_response):
            conf = float(word["confidence"])
            assert 0.0 <= conf <= 1.0, (
                f"confidence out of range: {conf} for word={word.get('word')!r}"
            )

    def test_every_word_speaker_is_nonnegative_integer(self, raw_response):
        for word in _iter_native_words(raw_response):
            speaker = word["speaker"]
            assert isinstance(speaker, int) and speaker >= 0, (
                f"speaker corruption: speaker={speaker!r} "
                f"for word={word.get('word')!r}"
            )

    def test_no_word_has_empty_text(self, raw_response):
        for word in _iter_native_words(raw_response):
            assert word["word"].strip() != "", (
                f"empty word: {word}"
            )


# ---------------------------------------------------------------------------
# Utterance-level integrity (still at the source)
# ---------------------------------------------------------------------------


class TestSourceUtteranceIntegrity:
    def test_every_utterance_has_required_fields(self, raw_response):
        for utt in _iter_native_utterances(raw_response):
            for field in ("transcript", "start", "end", "speaker"):
                assert field in utt, f"utterance missing {field}: {utt}"

    def test_every_utterance_start_before_end(self, raw_response):
        for utt in _iter_native_utterances(raw_response):
            assert float(utt["start"]) <= float(utt["end"])

    def test_every_utterance_has_transcript(self, raw_response):
        for utt in _iter_native_utterances(raw_response):
            assert isinstance(utt["transcript"], str) and utt["transcript"]


# ---------------------------------------------------------------------------
# Cross-layer continuity — the structured (post-mutation) layer must
# preserve a clear reference back to the raw source counts.
# ---------------------------------------------------------------------------


class TestStructuredLayerPreservesRawReferences:
    def test_metadata_records_native_vs_canonical_counts(self, metadata):
        # The fixture metadata captures both the native (immutable raw)
        # and the canonical (post-mutation) counts. Both must be
        # present and the canonical must be <= native (mutation only
        # removes; it never adds).
        assert metadata["native_word_total"] >= metadata["canonical_assembled_words"]
        assert (
            metadata["native_utterance_total"]
            >= metadata["canonical_assembled_utterances"]
        )

    def test_word_loss_within_documented_overlap_dedup_bound(self, metadata):
        # The 9-chunk Etminan run had ~20 s overlap × 8 boundaries ≈
        # 160 s overlap audio. At ~2.5 words/s the expected drop is
        # 400 ± 100. The actual drop here is 12212 - 11795 = 417.
        loss = metadata["native_word_total"] - metadata["canonical_assembled_words"]
        assert 100 < loss < 700, (
            f"word loss {loss} outside documented overlap-dedup bound. "
            f"Investigate before allowing further refactor phases."
        )

    def test_request_params_recorded(self, metadata):
        params = metadata.get("request_params_snapshot", {})
        # The audit doc lists 9 baseline Deepgram flags. All must be
        # present in the snapshot.
        for key in (
            "model", "language", "smart_format", "diarize", "punctuate",
            "paragraphs", "utterances", "utt_split", "filler_words",
            "numerals",
        ):
            assert key in params, f"params snapshot missing {key}"

    def test_utt_split_pinned_to_0_8(self, metadata):
        assert metadata["request_params_snapshot"]["utt_split"] == "0.8"


# ---------------------------------------------------------------------------
# Fixture sanity (catches the case where the fixture itself was corrupted)
# ---------------------------------------------------------------------------


class TestFixtureSanity:
    def test_raw_response_file_size_reasonable(self):
        size = RAW_RESPONSE_PATH.stat().st_size
        # The Etminan fixture is ~9.3 MB. We allow 5–20 MB to catch
        # both empty-file regressions and accidental enlargement.
        assert 5_000_000 < size < 20_000_000, (
            f"raw_dg_response.json size {size} outside expected band"
        )

    def test_raw_deepgram_txt_present_and_nonempty(self):
        assert RAW_TXT_PATH.exists()
        assert RAW_TXT_PATH.stat().st_size > 1000
