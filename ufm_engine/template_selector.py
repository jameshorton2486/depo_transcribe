"""Template selection rules for UFM rendering workflows."""

from __future__ import annotations


class TemplateSelector:
    """Select template keys based on job characteristics."""

    def select_templates(self, job_data: dict) -> list[str]:
        """Return the template keys required for a job.

        Args:
            job_data: Source job data used to decide conditional templates.

        Raises:
            ValueError: If job_data is not a dictionary.
        """
        if not isinstance(job_data, dict):
            raise ValueError("job_data must be a dictionary.")

        selected_templates = [
            "title_page",
            "appearance_page",
            "index_page",
        ]

        if job_data.get("is_remote", False):
            selected_templates.append("witness_setup_remote")
        else:
            selected_templates.append("witness_setup_standard")

        if job_data.get("include_signature", True):
            selected_templates.extend(["changes_signature", "signature_block"])

        selected_templates.append("certification")

        return selected_templates
