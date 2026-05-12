# GOLD_STANDARD_REGRESSION_PROPOSAL — Cavazos

**Case folder referenced:** `C:\Users\james\Depositions\2026\May\2026CV00803\cavazos_gilberto`

This is a *proposal* for a Cavazos-rooted regression test, not a built artifact. The intent is to lock in observable behavior of the live Start-Transcription pipeline against a known case so future changes to `clean_format/`, `core/job_runner.py`, or `pipeline/transcriber.py` produce a clear pass/fail signal instead of "looks roughly right." The test would protect against silent drift in the four properties that matter most: that the pipeline runs at all, that confirmed spellings (when they apply) survive the cleanup, that the highlight count stays in a plausible band, and that Q/A paragraph counts don't regress.

## 1. Inputs needed

### Source audio location
`C:\Users\james\Downloads\video1506949045 (2).mp4` — 95.3 MB, MP4 with embedded audio. **Risk:** the audio lives outside the case folder (per `raw_deepgram.json["audio_file"]`), which is fragile. Either copy the audio into `tests/regression/fixtures/cavazos/source_audio/` and update `audio_file` in the fixture's `raw_deepgram.json`, or accept that this is a "live-call gated" test and not a true regression test.

### `source_docs/job_config.json` snapshot
File at `<case>\source_docs\job_config.json` (65,297 bytes). Captures every input to the Start-Transcription pipeline that is not the audio itself:

- `ufm_fields` (41 keys, all the case-meta inputs).
- `confirmed_spellings` (33 entries) — including the variant pairs (Cavazas→Cavazos, Valley→Valle, Chester→Chesser, plus the 13 Objection-variant entries).
- `deepgram_keyterms` (84 entries) — the list sent to Deepgram for keyterm-hinting.
- `speaker_map_suggestion` (7 roles).
- `low_confidence_words` (517 entries — these are derived, not input; useful for the regression to assert "Deepgram still flagged the same low-conf words" after a model upgrade).
- `version`, `model`, `audio_quality`.

Copy verbatim to `tests/regression/fixtures/cavazos/source_docs/job_config.json`.

### Expected `raw_deepgram.json` (golden capture)
File at `<case>\Deepgram\raw_deepgram.json` (5,462,437 bytes — 5.2 MB). Contains the exact Deepgram response shape this test should assert against if the test is run in **replay mode** (mocked `transcribe_chunk` returning canned data). Captures: 3,858 word records with `(word, start, end, confidence, speaker, punctuated_word, type)`, `utterances`, `raw_utterances`, `chunks`, `chunk_summaries`, `transcript`, `audio_file`, `deepgram_keyterms_used`.

Copy verbatim to `tests/regression/fixtures/cavazos/Deepgram/raw_deepgram.json`.

### Expected final DOCX (golden capture, post any future fixes)
**Do not freeze yet.** Today's smoke DOCX (`Cavazos_Deposition_smoke_2026-05-12.docx`) has the issues catalogued in `CASE_MUTATION_REPORT.md`:
- 58 inline `[SCOPIST: FLAG ...]` annotations that the team likely does not want in body text.
- Q:A ratio 108:55 with 125 unclassified paragraphs — structurally implausible.
- Header conflating attorney role (`role="defendant"`) with the defendant label.

A regression test that asserts equality against today's DOCX would lock in those defects. **Recommendation:** capture today's DOCX as a *reference* artifact (committed under `tests/regression/fixtures/cavazos/reference_outputs/`), but write the assertions to allow drift bands rather than byte equality (see §2). After the issues catalogued in this audit are addressed, capture a new "expected" DOCX and tighten the assertions then.

## 2. Test layout

### Where it would live
`tests/regression/test_cavazos.py`. Sibling-level to existing test trees (`pipeline/tests/`, `clean_format/tests/`, `core/tests/`, `ui/tests/`, `tests/ufm_engine/`). `tests/regression/` is a new top-level package; would need a `__init__.py` and a `conftest.py` that resolves the fixture root.

### How it bootstraps the case
```python
# tests/regression/conftest.py
import json
from pathlib import Path
import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "cavazos"

@pytest.fixture(scope="module")
def cavazos_fixture():
    return {
        "case_root": FIXTURE_ROOT,
        "job_config": json.loads((FIXTURE_ROOT / "source_docs" / "job_config.json").read_text(encoding="utf-8")),
        "raw_deepgram_json": FIXTURE_ROOT / "Deepgram" / "raw_deepgram.json",
        "raw_deepgram_txt": FIXTURE_ROOT / "Deepgram" / "raw_deepgram.txt",
        "case_meta_path": FIXTURE_ROOT / "case_meta.json",
        "audio_path": FIXTURE_ROOT / "source_audio" / "video1506949045_2.mp4",
        "reference_docx": FIXTURE_ROOT / "reference_outputs" / "Cavazos_Deposition_reference.docx",
    }
```

### What it asserts

#### Section 1 — Pipeline ran end-to-end
Run mode: invoke `clean_format.formatter.format_transcript(raw_text, case_meta, deepgram_words=words)` directly. Skip the Deepgram leg; assume the captured `raw_deepgram.json` is the input.

```python
def test_section1_pipeline_completes(cavazos_fixture):
    raw_text = (cavazos_fixture["raw_deepgram_txt"]).read_text(encoding="utf-8")
    words = load_deepgram_words_from_json(cavazos_fixture["raw_deepgram_json"])
    case_meta = json.loads(cavazos_fixture["case_meta_path"].read_text(encoding="utf-8"))

    formatted = format_transcript(raw_text, case_meta, deepgram_words=words)

    assert formatted, "format_transcript returned empty"
    assert "Q." in formatted or "EXAMINATION" in formatted, "no exam structure"
    # Sanity: text length within ±25% of the captured reference
    reference_len = 23_334  # observed in smoke
    assert 0.75 * reference_len <= len(formatted) <= 1.25 * reference_len
```

#### Section 2 — Specific `confirmed_spellings` applied
**Important caveat per the Mutation Report:** on the live Cavazos case, none of the 33 wrong forms appeared in the raw transcript, so this test would assert a no-op today. The right assertion is to verify the spellings dict (a) was persisted to job_config (the wiring up to that point works) and (b) was *available* to the cleanup pass. The latter is currently false (see Active Path Audit Q2/Q3); this test would document the gap until it's closed.

```python
def test_section2_confirmed_spellings_persisted_and_visible_to_cleanup(cavazos_fixture):
    cs = cavazos_fixture["job_config"]["confirmed_spellings"]
    assert len(cs) == 33
    assert cs["Cavazas"] == "Cavazos"
    assert cs["Valley"] == "Valle"
    assert cs["Chester"] == "Chesser"

    # This part FAILS today and would document the wiring gap.
    # When the audit's wiring recommendation lands, this becomes the regression
    # that prevents it being lost again.
    case_meta_keys = list(_case_meta_for_prompt(json.loads(
        cavazos_fixture["case_meta_path"].read_text(encoding="utf-8")
    )).keys())
    # When the fix lands: "confirmed_spellings" should appear in the prompt
    # input. Today it does not.
    assert "confirmed_spellings" in case_meta_keys, (
        "confirmed_spellings is persisted but never reaches the cleanup prompt. "
        "See docs/audits/ACTIVE_PATH_AUDIT.md Q2."
    )
```

#### Section 3 — Highlight count within tolerance band
Per the smoke run, 154 markers were injected and 150 yellow `<w:highlight>` runs appeared in the DOCX. Future runs against the same fixture should land in a tolerance band around these.

```python
def test_section3_highlight_count_within_band(cavazos_fixture, tmp_path):
    formatted = run_format_transcript(cavazos_fixture)  # helper from Section 1
    docx_path = tmp_path / "cavazos_test.docx"
    case_meta = json.loads(cavazos_fixture["case_meta_path"].read_text(encoding="utf-8"))
    write_deposition_docx(formatted, case_meta, docx_path)

    yellow_count = count_yellow_highlights_in_docx(docx_path)

    # Captured: 150. Allow ±15% band to absorb cleanup-pass non-determinism.
    assert 128 <= yellow_count <= 173, f"yellow highlights drifted: {yellow_count}"

    # Stronger assertion: the drift from injected to rendered should stay
    # under the 5% systematic-drift threshold, matching the Step E policy.
    injected = count_injected_markers_for(formatted)  # from inject_markers
    if injected >= 5:
        drop_pct = 100 * (injected - yellow_count) / injected
        assert drop_pct <= 5.0, f"marker drift {drop_pct:.1f}% > 5%"
```

#### Section 4 — Q/A paragraph count within band
Per Mutation Report row M-13, today's smoke DOCX has Q.=108, A.=55, three-tab non-QA=125 — flagged as a regression vs. the pre-smoke DOCX which had Q.=106, A.=102, three-tab=0 from the same inputs. The right assertion here is "Q. and A. counts should be within ±10% of each other for a deposition" and "three-tab non-QA paragraphs should be near zero."

```python
def test_section4_qa_balance(cavazos_fixture, tmp_path):
    formatted = run_format_transcript(cavazos_fixture)
    docx_path = tmp_path / "cavazos_test.docx"
    case_meta = json.loads(cavazos_fixture["case_meta_path"].read_text(encoding="utf-8"))
    write_deposition_docx(formatted, case_meta, docx_path)

    counts = count_paragraph_structure(docx_path)
    q, a, tt = counts["q"], counts["a"], counts["three_tab_non_qa"]

    # Q/A should be roughly balanced (questions get answered).
    ratio = max(q, a) / max(min(q, a), 1)
    assert ratio < 2.0, (
        f"Q:A ratio {q}:{a} is structurally implausible for a deposition"
    )

    # Three-tab non-QA paragraphs should be near zero in a depo with a
    # cleanly mapped witness.
    assert tt < 10, f"too many unclassified paragraphs: {tt}"
```

### Pre-commit hooks vs. CI
This test should NOT run on `pre-commit` (its runtime is dominated by ≈160 s of Anthropic calls per Section-3+4 invocation). It should run nightly or on PRs that touch `clean_format/`, `pipeline/`, or `core/job_runner.py`.

## 3. Cost-of-running notes

### Does it require live Deepgram + Anthropic calls?
- **Deepgram:** No, if `raw_deepgram.json` is captured as a fixture and the Deepgram-leg of the pipeline is bypassed by feeding `format_transcript` the captured words directly. Yes, if the test is run end-to-end including audio→transcription.
- **Anthropic:** Yes, the Section 3 and Section 4 assertions depend on the live cleanup pass running. Each invocation costs roughly the same as the smoke run (Sonnet/Opus tokens for ~3,858 input words × N chunks). At today's rates, low single-digit cents per run. Acceptable for a nightly job; not acceptable for every push.

### Suggested gating
Add a custom pytest marker `@pytest.mark.regression` and an env-gated runner:

```python
# pytest.ini
[pytest]
markers =
    regression: opt-in regression suite hitting live Anthropic. Requires REGRESSION_LIVE=1.

# tests/regression/test_cavazos.py
@pytest.mark.regression
@pytest.mark.skipif(
    not os.environ.get("REGRESSION_LIVE"),
    reason="set REGRESSION_LIVE=1 to opt into live-API regression suite",
)
def test_section3_highlight_count_within_band(...):
    ...
```

The default `pytest -q` invocation stays at ~561 fast tests and does not hit any API. CI runs the regression suite once per night or on PRs touching the wired modules.

## 4. What it can't catch

A regression test rooted in a single case is bounded by what that case exercises. This test will **not** catch:

1. **Bugs in cases with confirmed_spellings that actually apply.** Cavazos's confirmed_spellings dict has 33 entries but none of the wrong forms appear in this specific audio. A wiring fix or regression in the `confirmed_spellings → prompt` path would be invisible to this test. Would need a *second* fixture case where Deepgram demonstrably mis-transcribed a name and the dict had to correct it.
2. **Cases with substantially different speaker counts or shapes.** Cavazos is a 5-speaker case with one primary witness and one primary questioning attorney. A solo-deponent case, a multi-witness deposition, or a case where the videographer/reporter speak at length would exercise the speaker-mapping code along different branches.
3. **Audio-quality regressions.** This test bypasses the audio→Deepgram leg (using the captured JSON). Changes to `pipeline/preprocessor.py`, `pipeline/vad_trimmer.py`, or `pipeline/audio_quality.py` would not be caught.
4. **Anthropic-model drift.** When the cleanup model is upgraded (Sonnet 4.6 → 4.7 → 5.x), the cleanup output will shift in ways the band-based assertions deliberately tolerate. The test will not flag "model is now subtly worse at preserving filler words" unless the drift is large enough to push counts outside the bands.
5. **DOCX visual-fidelity issues** that don't surface as XML-level counts: font choice, margin sizing, page-break positions, table-cell shading, header-image rendering. The audit found `0xfffd` replacement chars in extracted DOCX text (Mutation Report M-16) — a count-based assertion would not catch that.
