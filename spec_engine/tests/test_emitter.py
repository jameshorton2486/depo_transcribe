from spec_engine.classifier import classify_blocks
from spec_engine.emitter import emit_blocks
from spec_engine.qa_fixer import enforce_structure
from spec_engine.speaker_mapper import normalize_speakers


def test_emitter_enforces_tabbed_qa_and_double_spacing():
    classified = classify_blocks(
        [
            {"speaker": "speaker 1", "text": "BY MS. MALONEY:", "type": "paragraph"},
            {"speaker": "speaker 1", "text": "\tQ.\tDid you go there? yes.", "type": "paragraph"},
            {"speaker": "speaker 2", "text": "\tA.\tYes. I did.", "type": "paragraph"},
        ]
    )
    rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
    assert "BY MS. MALONEY:" in rendered
    assert "\tQ.\tDid you go there?  yes." in rendered
    assert "\tA.\tYes.  I did." in rendered
    assert "\n\n\tA.\t" in rendered


def test_emitter_groups_consecutive_colloquy_under_one_label():
    classified = classify_blocks(
        [
            {"speaker": "videographer", "text": "Today's date is April 9, 2026.", "type": "paragraph"},
            {"speaker": "videographer", "text": "The time is 8:12 a.m.", "type": "paragraph"},
        ]
    )
    rendered = emit_blocks(normalize_speakers(enforce_structure(classified)))
    assert rendered == "VIDEOGRAPHER:\n\tToday's date is April 9, 2026.\n\tThe time is 8:12 a.m."
