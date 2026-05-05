"""
ufm_engine/populator/populate.py

Populate a UFM template with case data:
  - Resolve block-level <w:sdt> conditional wrappers per `block_toggles`:
      toggle == True  -> unwrap (keep contents, remove sdt wrapper)
      toggle == False -> remove the entire sdt + contents
      toggle missing  -> default-on (treated as True per recipe §6)
  - Fill content-control <w:sdt> placeholders from `fields`. The sdt
    wrapper is preserved so a downstream tool can re-locate the field.
  - Null/missing field whose sdt is still visible: leave placeholder
    text in place and log a warning.

Distinguishes block sdts from content-control sdts by parent: block
sdts sit at body level (or inside another body-level sdt); content
controls sit inside a paragraph or run.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping, Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

log = logging.getLogger(__name__)

BLOCK_TAG_PREFIX = "block_"


def populate(
    template_path: Path,
    output_path: Path,
    *,
    fields: Mapping[str, object],
    block_toggles: Optional[Mapping[str, bool]] = None,
) -> None:
    """Populate a template and write the result to `output_path`.

    Args:
        template_path: path to a `.docx` produced by build_templates.
        output_path: where the populated `.docx` is written.
        fields: tag -> value map for content controls.
        block_toggles: tag -> bool for conditional blocks. Missing keys
            default to True (block kept and unwrapped). Pass an empty
            dict to disable the default and require explicit toggles.
    """
    if not template_path.exists():
        raise FileNotFoundError(template_path)

    doc = Document(str(template_path))
    toggles = dict(block_toggles) if block_toggles is not None else None

    _resolve_block_sdts(doc, toggles)
    _fill_content_controls(doc, fields)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


# ---------------------------------------------------------------------------
# Block sdt resolution
# ---------------------------------------------------------------------------

def _resolve_block_sdts(doc, toggles: Optional[Mapping[str, bool]]) -> None:
    """Resolve every conditional block sdt in the document.

    Walks the entire body — not just top-level children — so inline
    block sdts (e.g. an "AND VIDEOTAPED " phrase wrapped within a
    paragraph) are handled the same way as full-paragraph block sdts.

    Snapshots the list before mutating: removing an outer sdt also
    detaches any inner sdts in the same pass, so we skip detached
    elements rather than crash.
    """
    body = doc.element.body
    sdts = [
        s for s in body.iter(qn("w:sdt"))
        if (_sdt_tag(s) or "").startswith(BLOCK_TAG_PREFIX)
    ]
    for sdt in sdts:
        if sdt.getparent() is None:
            # Already removed when an outer block was deleted.
            continue
        tag = _sdt_tag(sdt)
        keep = _toggle_value(tag, toggles)
        if keep:
            _unwrap_sdt(sdt)
        else:
            _remove_sdt(sdt)


def _toggle_value(tag: str, toggles: Optional[Mapping[str, bool]]) -> bool:
    """Default-on if `toggles` is None or the key is absent."""
    if toggles is None:
        return True
    return bool(toggles.get(tag, True))


def _unwrap_sdt(sdt) -> None:
    """Replace the sdt with its sdtContent children, preserving order."""
    parent = sdt.getparent()
    idx = list(parent).index(sdt)
    content = sdt.find(qn("w:sdtContent"))
    if content is None:
        parent.remove(sdt)
        return
    children = list(content)
    parent.remove(sdt)
    for offset, child in enumerate(children):
        parent.insert(idx + offset, child)


def _remove_sdt(sdt) -> None:
    parent = sdt.getparent()
    if parent is not None:
        parent.remove(sdt)


# ---------------------------------------------------------------------------
# Content control population
# ---------------------------------------------------------------------------

def _fill_content_controls(doc, fields: Mapping[str, object]) -> None:
    """Walk every remaining <w:sdt> and set its text from `fields`."""
    body = doc.element.body
    for sdt in body.iter(qn("w:sdt")):
        tag = _sdt_tag(sdt)
        if tag is None:
            continue
        if tag in fields and fields[tag] is not None:
            _set_sdt_text(sdt, str(fields[tag]))
        else:
            log.warning("populator: no value for field %r; placeholder kept", tag)


def _sdt_tag(sdt) -> Optional[str]:
    pr = sdt.find(qn("w:sdtPr"))
    if pr is None:
        return None
    tag_el = pr.find(qn("w:tag"))
    if tag_el is None:
        return None
    return tag_el.get(qn("w:val"))


def _set_sdt_text(sdt, value: str) -> None:
    """Replace the sdt's content text with `value`, preserving the sdt wrapper.

    Strategy:
      - clear `<w:showingPlcHdr/>` so Word renders it as populated
      - find the first <w:r> in sdtContent; replace its <w:t> with `value`
      - drop any other runs inside sdtContent
      - if no run exists, create one with the document's default font
    """
    pr = sdt.find(qn("w:sdtPr"))
    if pr is not None:
        showing = pr.find(qn("w:showingPlcHdr"))
        if showing is not None:
            pr.remove(showing)

    content = sdt.find(qn("w:sdtContent"))
    if content is None:
        content = OxmlElement("w:sdtContent")
        sdt.append(content)

    runs = content.findall(qn("w:r"))
    if not runs:
        run = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        rfonts = OxmlElement("w:rFonts")
        rfonts.set(qn("w:ascii"), "Courier New")
        rfonts.set(qn("w:hAnsi"), "Courier New")
        rpr.append(rfonts)
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "24")
        rpr.append(sz)
        run.append(rpr)
        content.append(run)
        runs = [run]

    primary = runs[0]
    for extra in runs[1:]:
        content.remove(extra)

    for t in list(primary.findall(qn("w:t"))):
        primary.remove(t)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = value
    primary.append(t)
