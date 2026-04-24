from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.processor import run_pipeline
from spec_engine.models import BlockType


def test_run_pipeline_returns_blocks_and_text():
    result = run_pipeline(
        {
            "utterances": [
                {
                    "speaker": 1,
                    "transcript": "I went there last week.",
                    "words": [],
                }
            ]
        },
        {
            "speaker_map": {1: "THE WITNESS"},
            "witness_id": 1,
            "cause_number": "TEST-PROCESSOR",
        },
    )

    assert result["blocks"][0].block_type == BlockType.ANSWER
    assert isinstance(result["text"], str)


def test_run_pipeline_warns_when_legacy_ai_args_are_used():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_pipeline(
            {
                "utterances": [
                    {
                        "speaker": 1,
                        "transcript": "I went there last week.",
                        "words": [],
                    }
                ]
            },
            {
                "speaker_map": {1: "THE WITNESS"},
                "witness_id": 1,
                "cause_number": "TEST-PROCESSOR",
            },
            apply_ai=True,
        )

    assert len(caught) == 1
    assert issubclass(caught[0].category, DeprecationWarning)
