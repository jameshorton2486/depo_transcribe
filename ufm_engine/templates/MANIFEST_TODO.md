# Manifest TODO

## block_interpreted on the TX state title page

The federal title page now wires `block_interpreted` (UFM Figure 17/Federal),
emitting "(INTERPRETED FROM [Language] TO ENGLISH)" wrapped in a paragraph
sdt. The TX state title page does not yet wire this block, so
`block_interpreted` was removed from `title_page_tx_state.conditional_blocks`
to keep the manifest honest.

To re-add for TX state:

1. Confirm the canonical TX/UFM phrasing for the interpreted notation on
   Figure 17 (the federal phrasing may or may not match TX convention).
2. Add the corresponding `_wrap_in_block_sdt(doc, "block_interpreted", 1)`
   paragraph to `build_title_page_tx_state` in
   `ufm_engine/generator/build_templates.py`, mirroring the federal
   implementation (lines 398–403 as of phase 5).
3. Restore `"block_interpreted"` to `conditional_blocks` and
   `"block_interpreted": false` to `default_blocks` for `title_page_tx_state`.
4. Regenerate templates: `python -m ufm_engine.generator.build_templates`.

The `witness_setup_interpreter` template (UFM Figure 27) is unrelated;
that's a standalone template for an interpreted setup, not a block on the
title page.
