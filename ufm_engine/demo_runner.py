"""Example runner for template selection and context building."""

from __future__ import annotations

from pprint import pprint

from .context_builder import ContextBuilder
from .template_selector import TemplateSelector


def main() -> None:
    """Build sample context and show the selected template keys."""
    job_data = {
        "witness_name": "John Doe",
        "date": "2026-03-20",
        "is_remote": True,
        "reporter_name": "Jane Smith",
        "csr_number": "12345",
        "include_signature": True,
    }

    context = ContextBuilder().build_context(job_data)
    selected_templates = TemplateSelector().select_templates(job_data)

    print("Selected templates:")
    pprint(selected_templates)
    print("\nContext:")
    pprint(context)


if __name__ == "__main__":
    main()
