"""Typed data contracts for the UFM engine.

These models define the package-level request, registry, and merge payloads used
across rendering and assembly workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TemplateDefinition:
    """Describes a registered template and the fields it expects."""

    name: str
    template_path: Path
    required_fields: tuple[str, ...] = ()
    description: str = ""


@dataclass(slots=True)
class RenderRequest:
    """Represents one template rendering request."""

    template_path: Path
    output_path: Path
    context: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MergeResult:
    """Represents the outcome of a future DOCX merge operation."""

    output_path: Path
    merged_documents: tuple[Path, ...] = ()
