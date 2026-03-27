"""Template registry for UFM template lookup."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_REGISTRY: dict[str, str] = {
    "title_page": "ufm_engine/templates/title_pages/fig17_title_page_freelance.docx",
    "appearance_page": "ufm_engine/templates/appearances/fig18_appearance_page.docx",
    "index_page": "ufm_engine/templates/index/fig22_index.docx",
    "witness_setup_remote": "ufm_engine/templates/witness_setup/fig23_witness_setup_remote.docx",
    "witness_setup_standard": "ufm_engine/templates/witness_setup/fig23_witness_setup_standard.docx",
    "transcript_body": "ufm_engine/templates/transcript_body/fig28_qa_transcript_body.docx",
    "changes_signature": "ufm_engine/templates/signature/fig19_changes_signature.docx",
    "signature_block": "ufm_engine/templates/signature/fig19a_signature_block.docx",
    "certification": "ufm_engine/templates/certification/fig20_certification.docx",
    "certification_cont": "ufm_engine/templates/certification/fig20a_certification_cont.docx",
    "nonstenographic_title": "ufm_engine/templates/title_pages/fig25_nonstenographic_title_page.docx",
}


def get_template_path(template_name: str) -> str:
    """Return an absolute template path for a registered template name.

    Args:
        template_name: Stable key identifying a supported template.

    Raises:
        ValueError: If the template name is not registered.
    """
    relative_path = TEMPLATE_REGISTRY.get(template_name)
    if relative_path is None:
        available = ", ".join(sorted(TEMPLATE_REGISTRY))
        raise ValueError(f"Unknown template '{template_name}'. Available templates: {available}")

    return str((REPO_ROOT / relative_path).resolve())


class TemplateRegistry:
    """Thin registry wrapper for template path lookup."""

    def get(self, template_name: str) -> str:
        """Return the resolved template path for a registered template."""
        return get_template_path(template_name)
