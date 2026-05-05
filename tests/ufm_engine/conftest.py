"""Make project root importable for ufm_engine tests.

This directory is intentionally NOT a package (no __init__.py) to avoid
a naming collision: a `tests/ufm_engine/__init__.py` would shadow the
source package `ufm_engine/` because pytest puts `tests/` on sys.path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
