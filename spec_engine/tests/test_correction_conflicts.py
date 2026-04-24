from spec_engine.corrections import (
    CorrectionState,
    apply_case_corrections,
    apply_multiword_corrections,
    apply_universal_corrections,
    safe_apply,
)
from spec_engine.models import CorrectionRecord, JobConfig


def test_apply_universal_corrections_allows_nonconflicting_chain():
    records: list[CorrectionRecord] = []

    result = apply_universal_corrections(
        "Action form and alright",
        records,
        block_index=0,
    )

    assert result == "Objection.  Form. and all right"
    assert [record.pattern for record in records] == [
        r'\bAction form\b[.]?',
        r'\balright\b',
    ]


def test_safe_apply_blocks_conflicting_followup_rewrite():
    state = CorrectionState()
    records: list[CorrectionRecord] = []

    text = safe_apply(
        "Action form",
        "Objection.  Form.",
        r'\bAction form\b[.]?',
        state,
        records,
        block_index=0,
        protected_after="Objection.  Form.",
    )
    blocked = safe_apply(
        text,
        "Form.",
        "destructive_followup",
        state,
        records,
        block_index=0,
    )

    assert blocked == "Objection.  Form."
    assert [record.pattern for record in records] == [r'\bAction form\b[.]?']


def test_multiword_corrections_use_shared_conflict_state():
    state = CorrectionState()
    records: list[CorrectionRecord] = []

    result = apply_multiword_corrections(
        "subpoena deuces tikum",
        records,
        block_index=0,
        state=state,
    )
    blocked = safe_apply(
        result,
        "tecum",
        "destructive_followup",
        state,
        records,
        block_index=0,
    )

    assert blocked == "subpoena duces tecum"


def test_case_corrections_use_shared_conflict_state():
    state = CorrectionState()
    records: list[CorrectionRecord] = []
    cfg = JobConfig(confirmed_spellings={"Cogger": "Matthew Allan Coger"})

    result = apply_case_corrections(
        "Cogger testified.",
        cfg,
        records,
        block_index=0,
        state=state,
    )
    blocked = safe_apply(
        result,
        "Testified.",
        "destructive_followup",
        state,
        records,
        block_index=0,
    )

    assert blocked == "Matthew Allan Coger testified."
