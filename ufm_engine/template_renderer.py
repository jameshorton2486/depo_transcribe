"""DOCX template rendering utilities for the UFM engine."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from docxtpl import DocxTemplate


class TemplateRenderer:
    """Render a single DOCX template with dynamic context data."""

    def render_template(self, template_path: str, context: Dict, output_path: str) -> None:
        """Render one DOCX template and save the generated document.

        Args:
            template_path: Source DOCX template path.
            context: Data used to fill template placeholders.
            output_path: Destination path for the rendered DOCX file.

        Raises:
            FileNotFoundError: If the template file does not exist.
            ValueError: If paths are invalid or the rendering context is empty.
            RuntimeError: If loading, rendering, or saving the DOCX fails.
        """
        template_file = Path(template_path)
        destination = Path(output_path)

        self._validate_docx_path(template_file, "template_path")
        self._validate_docx_path(destination, "output_path")

        if not template_file.is_file():
            raise FileNotFoundError(f"Template file not found: {template_file}")

        if not context:
            raise ValueError("Template rendering context cannot be empty.")

        try:
            print(f"Template loaded: {template_file}")
            template = DocxTemplate(str(template_file))

            print("Render started")
            template.render(context)
            print("Render completed")

            destination.parent.mkdir(parents=True, exist_ok=True)
            template.save(str(destination))
            print(f"Output saved: {destination}")
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to render template '{template_file}': {exc}") from exc

    @staticmethod
    def _validate_docx_path(path: Path, label: str) -> None:
        """Validate that a path uses the DOCX extension."""
        if path.suffix.lower() != ".docx":
            raise ValueError(f"{label} must point to a .docx file: {path}")


if __name__ == "__main__":
    renderer = TemplateRenderer()
    renderer.render_template(
        template_path="ufm_engine/templates/title_pages/fig17_title_page_freelance.docx",
        context={"witness_name": "John Doe"},
        output_path="output/title_page.docx",
    )
