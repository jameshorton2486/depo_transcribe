from spec_engine.models import Block
from spec_engine.preamble_rules import apply_preamble_rules


def test_apply_preamble_rules_normalizes_reporter_opening_text():
    block = Block(
        text="I am the court for a license with csr number 12129 for this deposition.",
        raw_text="I am the court for a license with csr number 12129 for this deposition.",
        speaker_id=4,
        meta={},
    )

    result = apply_preamble_rules([block])

    assert result[0].text == "I am the court reporter, licensed with CSR No. 12129 for this deposition."
    assert len(result[0].meta["corrections"]) == 2


def test_apply_preamble_rules_ignores_late_non_preamble_blocks():
    blocks = [Block(text="Plain text", raw_text="Plain text", speaker_id=1, meta={}) for _ in range(10)]
    target = Block(
        text="court for a license",
        raw_text="court for a license",
        speaker_id=1,
        meta={},
    )
    blocks.append(target)

    result = apply_preamble_rules(blocks)

    assert result[-1].text == "court for a license"
