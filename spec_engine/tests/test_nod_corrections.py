from spec_engine.models import Block, JobConfig
from spec_engine.nod_corrections import apply_nod_corrections


def test_apply_nod_corrections_uses_confirmed_spellings_and_tracks_audit():
    block = Block(
        text="benavidez appeared in bear county",
        raw_text="benavidez appeared in bear county",
        speaker_id=1,
        meta={},
    )
    cfg = JobConfig(
        confirmed_spellings={
            "benavidez": "Benavides",
            "bear county": "Bexar County",
        }
    )

    result = apply_nod_corrections([block], cfg)

    assert result[0].text == "Benavides appeared in Bexar County"
    assert result[0].raw_text == "benavidez appeared in bear county"
    assert len(result[0].meta["corrections"]) == 2
