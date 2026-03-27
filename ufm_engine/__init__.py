"""Unified Formatting Module package.

This package contains the modular components used to render transcript-driven
Word templates, register available templates, merge generated DOCX content, and
share typed data contracts across the formatting pipeline.
"""

# ── STATUS: INACTIVE ─────────────────────────────────────────────────────────
# ufm_engine is NOT imported by main.py and is not part of the active pipeline.
# It exists as a future template-rendering subsystem.
# Do NOT import from ufm_engine in main.py without a deliberate activation step.
# Merger and section-ordering bugs were patched in March 2026 (Prompt 5 of 6).
# ─────────────────────────────────────────────────────────────────────────────
import logging as _logging
_logging.getLogger(__name__).debug("ufm_engine loaded (inactive subsystem)")

from .data_models import MergeResult, RenderRequest, TemplateDefinition
from .docx_merger import DocxMerger
from .ufm_finalizer import UFMFinalizer
from .ufm_formatter import UFMFormatter
from .template_registry import TemplateRegistry
from .template_renderer import TemplateRenderer

__all__ = [
    "DocxMerger",
    "MergeResult",
    "RenderRequest",
    "TemplateDefinition",
    "TemplateRegistry",
    "TemplateRenderer",
    "UFMFinalizer",
    "UFMFormatter",
]
