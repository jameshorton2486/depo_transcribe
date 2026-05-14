"""Experiment configurations for the merge-threshold investigation.

This module ONLY defines configurations. It does NOT execute
experiments. Runners in this directory import from here so the
matrix lives in exactly one place.

See ``docs/investigations/merge_threshold_testing/README.md`` for the
rationale behind each configuration.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MergeConfig:
    """A single merge-threshold experiment configuration."""

    name: str
    in_chunk_gap: float
    cross_chunk_gap: float
    description: str

    @property
    def slug(self) -> str:
        """Folder-safe identifier."""
        return self.name


TEST_A_CURRENT = MergeConfig(
    name="TEST_A_CURRENT",
    in_chunk_gap=0.6,
    cross_chunk_gap=1.25,
    description=(
        "Production defaults. Matches what ships today. "
        "Reference point — every other run is compared against this."
    ),
)

TEST_B_MODERATE = MergeConfig(
    name="TEST_B_MODERATE",
    in_chunk_gap=0.6,
    cross_chunk_gap=0.9,
    description=(
        "Same per-chunk merge; cross-chunk gap reduced to 0.9s. "
        "Goal: tighten the cross-chunk pass without disturbing the "
        "in-chunk pass."
    ),
)

TEST_C_TIGHT = MergeConfig(
    name="TEST_C_TIGHT",
    in_chunk_gap=0.6,
    cross_chunk_gap=0.6,
    description=(
        "Both stages aligned at 0.6s. Symmetric, conservative. "
        "Both gaps now agree with the Deepgram-side cadence "
        "(utt_split=0.8 yields utterances broken at ~0.8s silence)."
    ),
)

TEST_D_VERY_TIGHT = MergeConfig(
    name="TEST_D_VERY_TIGHT",
    in_chunk_gap=0.4,
    cross_chunk_gap=0.5,
    description=(
        "Aggressive tightening of both stages. Edge of the "
        "exploration. Expected to expose Deepgram diarization "
        "errors as separate small utterances rather than absorb "
        "them into larger blocks."
    ),
)

ALL_CONFIGS: list[MergeConfig] = [
    TEST_A_CURRENT,
    TEST_B_MODERATE,
    TEST_C_TIGHT,
    TEST_D_VERY_TIGHT,
]


def get_config(name: str) -> MergeConfig:
    """Look up a config by name. Raises KeyError if not in the matrix."""
    for c in ALL_CONFIGS:
        if c.name == name:
            return c
    raise KeyError(
        f"Unknown merge config: {name}. "
        f"Known: {[c.name for c in ALL_CONFIGS]}"
    )
