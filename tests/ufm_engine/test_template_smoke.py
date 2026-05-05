"""Smoke tests for UFM templates and post-processor scaffolding."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = ROOT / "ufm_engine" / "templates" / "figures"
MANIFEST_PATH = ROOT / "ufm_engine" / "templates" / "manifest.json"
PROFILES_DIR = ROOT / "data" / "reporter_profiles"
SCHEMA_PATH = ROOT / "ufm_engine" / "templates" / "reporter_profile.schema.json"

EXPECTED_TEMPLATES = {
    "title_page_tx_state.docx",
    "title_page_federal.docx",
    "appearances.docx",
    "index_chronological.docx",
    "witness_setup_standard.docx",
    "witness_setup_interpreter.docx",
    "changes_signature_grid.docx",
    "witness_acknowledgment_notary.docx",
    "cert_tx_sig_required.docx",
    "cert_tx_sig_waived.docx",
    "cert_federal_frcp.docx",
    "cert_nonappearance.docx",
    "further_cert_trcp_203.docx",
}

EXPECTED_PROFILES = {
    "miah_bardot_sa_legal.json",
    "trisha_myler_lexitas_fortworth.json",
    "trisha_myler_lexitas_dallas.json",
}


def test_all_templates_exist():
    found = {f.name for f in TEMPLATES_DIR.glob("*.docx")}
    assert found == EXPECTED_TEMPLATES, f"Mismatch: {found ^ EXPECTED_TEMPLATES}"


def test_all_templates_are_valid_docx():
    for f in TEMPLATES_DIR.glob("*.docx"):
        with zipfile.ZipFile(f) as z:
            assert "word/document.xml" in z.namelist(), f"{f.name} missing document.xml"


def test_manifest_references_existing_files():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    for t in manifest["templates"]:
        assert (TEMPLATES_DIR / t["filename"]).exists(), t["filename"]


def test_manifest_covers_all_templates():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_files = {t["filename"] for t in manifest["templates"]}
    assert manifest_files == EXPECTED_TEMPLATES


def test_all_reporter_profiles_exist():
    found = {f.name for f in PROFILES_DIR.glob("*.json")}
    assert found == EXPECTED_PROFILES


def test_reporter_profiles_validate_against_schema():
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for f in PROFILES_DIR.glob("*.json"):
        profile = json.loads(f.read_text(encoding="utf-8"))
        jsonschema.validate(profile, schema)


def test_post_processor_imports_and_runs(tmp_path):
    from ufm_engine.post_processor.format_box import apply_format_box
    out = tmp_path / "test_out.docx"
    apply_format_box(
        input_path=TEMPLATES_DIR / "appearances.docx",
        output_path=out,
        apply_line_numbers=False,
        render_firm_footer=False,
    )
    assert out.exists()
