"""Pipeline walkthrough — opt-in stage-output capture for inspection.

Enabled by setting WALKTHROUGH_CAPTURE=1 in the environment. When
unset (the production default), capture_stage is a no-op.
"""

from tools.walkthrough.capture import capture_stage

__all__ = ["capture_stage"]
