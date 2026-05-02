from spec_engine.models import TranscriptBlock
from spec_engine.speaker_mapper import (
    ROLE_ATTORNEY,
    ROLE_WITNESS,
    detect_speaker_role,
    enforce_role_consistency,
    smooth_speaker_sequence,
)


def test_smooth_speaker_sequence_repairs_short_middle_flip():
    blocks = [
        TranscriptBlock(speaker="Attorney", text="Did you go there?", type="question"),
        TranscriptBlock(speaker="Witness", text="Okay", type="colloquy"),
        TranscriptBlock(
            speaker="Attorney", text="When did you arrive?", type="question"
        ),
    ]

    smoothed = smooth_speaker_sequence(blocks)

    assert smoothed[1].speaker == "Attorney"


def test_detect_speaker_role_uses_simple_heuristics():
    assert (
        detect_speaker_role(
            TranscriptBlock(
                speaker="Speaker 1", text="Did you go there?", type="question"
            )
        )
        == ROLE_ATTORNEY
    )
    assert (
        detect_speaker_role(
            TranscriptBlock(speaker="Speaker 2", text="Yes, I did.", type="answer")
        )
        == ROLE_WITNESS
    )


def test_enforce_role_consistency_carries_forward_last_known_role():
    blocks = [
        TranscriptBlock(speaker="Speaker 1", text="Did you go there?", type="question"),
        TranscriptBlock(
            speaker="Speaker 1", text="On Tuesday afternoon", type="colloquy"
        ),
    ]

    roles = enforce_role_consistency(blocks)

    assert roles == [ROLE_ATTORNEY, ROLE_ATTORNEY]
