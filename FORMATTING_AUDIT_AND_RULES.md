# DEPO-PRO TRANSCRIBE — FORMATTING AUDIT & NEW RULE IMPLEMENTATION GUIDE
# For: Claude Code
# Target repo: C:\Users\james\PycharmProjects\depo_transcribe
# Reporter: Miah Bardot, CSR No. 12129 — SA Legal Solutions, San Antonio TX
#
# PURPOSE
# ─────────────────────────────────────────────────────────────────────────────
# This prompt tells Claude Code how to:
#   1. Audit the existing formatting structure completely
#   2. Understand where every formatting decision is made
#   3. Implement new formatting rules correctly
#   4. Verify changes without breaking existing output
#
# Use this prompt when:
#   - The transcript looks wrong and you need to find why
#   - You want to change how something looks in the DOCX or textbox
#   - You are adding a new visual rule (color, indent, spacing, font)
#   - You want to understand the full formatting pipeline end-to-end

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — MANDATORY: READ ALL FORMATTING FILES BEFORE MAKING ANY CHANGES
# ══════════════════════════════════════════════════════════════════════════════
#
# Claude Code must read every file listed below IN FULL before touching
# anything. Do not skip this step. The files are interdependent and making
# a change in one without understanding the others will break the output.

```powershell
cd C:\Users\james\PycharmProjects\depo_transcribe

# Read every formatting file completely
Get-Content spec_engine\emitter.py
Get-Content spec_engine\document_builder.py
Get-Content spec_engine\models.py
Get-Content spec_engine\pages\caption.py
Get-Content spec_engine\pages\certificate.py
Get-Content spec_engine\pages\corrections_log.py
Get-Content spec_engine\pages\post_record.py
Get-Content spec_engine\pages\title_page.py
Get-Content spec_engine\pages\witness_index.py
Get-Content spec_engine\pages\_lined_page.py
Get-Content spec_engine\pages\cert_exhibits.py
Get-Content spec_engine\pages\changes_signature.py
Get-Content spec_engine\pages\exhibit_index.py
```

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — UNDERSTAND THE CURRENT FORMATTING ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
#
# After reading the files, Claude Code must answer these questions before
# making any changes. Print the answers to the terminal.

```powershell
python -c "
import sys
sys.path.insert(0, r'C:\Users\james\PycharmProjects\depo_transcribe')
from spec_engine.emitter import (
    FONT_NAME, FONT_SIZE, COLOR_ORANGE, COLOR_NAVY, COLOR_BLACK,
    TAB_720, TAB_1440, TAB_2160, _STANDARD_TABS,
)
from docx.shared import Pt

print('=== CURRENT FORMATTING CONSTANTS ===')
print(f'Font:         {FONT_NAME}')
print(f'Size:         {FONT_SIZE.pt}pt')
print(f'Tab stops:    {TAB_720} / {TAB_1440} / {TAB_2160} twips')
print(f'Tab inches:   {TAB_720/1440:.3f}\" / {TAB_1440/1440:.3f}\" / {TAB_2160/1440:.3f}\"')
print(f'Color orange: RGB({0xB4},{0x5F},{0x06}) — scopist flags')
print(f'Color navy:   RGB({0x1E},{0x3A},{0x5F}) — parentheticals')
print(f'Color black:  default — all other text')
"

python -c "
import sys
sys.path.insert(0, r'C:\Users\james\PycharmProjects\depo_transcribe')
from spec_engine.emitter import create_document
from docx.shared import Twips
doc = create_document()
s = doc.sections[0]
print()
print('=== CURRENT PAGE LAYOUT ===')
print(f'Page width:     {s.page_width.inches:.3f}\"  ({s.page_width.twips} twips)')
print(f'Page height:    {s.page_height.inches:.3f}\"  ({s.page_height.twips} twips)')
print(f'Left margin:    {s.left_margin.inches:.3f}\"  ({s.left_margin.twips} twips)')
print(f'Right margin:   {s.right_margin.inches:.3f}\"  ({s.right_margin.twips} twips)')
print(f'Top margin:     {s.top_margin.inches:.3f}\"  ({s.top_margin.twips} twips)')
print(f'Bottom margin:  {s.bottom_margin.inches:.3f}\"  ({s.bottom_margin.twips} twips)')
"
```

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — FORMATTING ARCHITECTURE REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
#
# This is the complete map of where every formatting decision lives.
# Claude Code must use this map to find the correct place for any change.
#
# ─────────────────────────────────────────────────────────────────────────────
# FILE: spec_engine/emitter.py
# PURPOSE: Every visual formatting decision for the transcript body
# ─────────────────────────────────────────────────────────────────────────────
#
# CONSTANTS (change these to affect ALL paragraphs of that type):
#
#   FONT_NAME = "Courier New"        — font used everywhere
#   FONT_SIZE = Pt(12)               — size used everywhere
#   COLOR_ORANGE = RGBColor(...)     — scopist flag color (bold orange)
#   COLOR_NAVY   = RGBColor(...)     — parenthetical line color
#   COLOR_BLACK  = RGBColor(...)     — all other text
#   TAB_720  = 720 twips  (0.5")    — Q./A. label position
#   TAB_1440 = 1440 twips (1.0")    — Q./A. text start position
#   TAB_2160 = 2160 twips (1.5")    — speaker label text start position
#
# FUNCTIONS (change these to affect one specific line type):
#
#   emit_blocks()          — plain-text output for the TEXTBOX and _corrected.txt
#                            ONE LINE PER BLOCK. \n between blocks only.
#                            NO textwrap. NO hard line breaks inside a block.
#
#   emit_q_line(doc, text) — Q. lines in the DOCX
#                            Format: \tQ.  {text}
#                            One paragraph per block.
#
#   emit_a_line(doc, text) — A. lines in the DOCX
#                            Format: \tA.  {text}
#                            One paragraph per block.
#
#   emit_sp_line(doc, text)— Speaker label lines in the DOCX
#                            Format: \t\t\t{BOLD LABEL}:  {text}
#                            One paragraph per block.
#                            Label is bold. Content is not bold.
#
#   emit_pn_line(doc, text)— Parenthetical lines in the DOCX
#                            Format: \t\t\t\t{text}
#                            Color: COLOR_NAVY
#
#   emit_flag_line(doc, t) — Scopist flag lines in the DOCX
#                            Color: COLOR_ORANGE, bold=True
#
#   emit_header_line(...)  — EXAMINATION / CROSS-EXAMINATION headers
#                            Centered, bold
#
#   emit_by_line(...)      — BY MR. JONES: attribution lines
#                            Left-aligned, plain
#
#   create_document()      — Creates the Document with correct page setup
#                            Change margins, paper size, orientation here
#
#   _set_paragraph_format()— Applied to every paragraph
#                            Controls: line spacing, space before/after
#
#   _apply_standard_tabs() — Applies the three standard tab stops to a para
#                            Uses _STANDARD_TABS = [TAB_720, TAB_1440, TAB_2160]
#
#   LineNumberTracker      — Tracks 25 lines per page (UFM requirement)
#                            Change LINES_PER_PAGE here if needed
#
#   emit_line_numbered()   — Emits a numbered line (for line-numbered DOCX)
#                            Same format as emit_*_line() but with line number
#
# IMPORTANT STATE: textwrap and _wrap_lines() have been REMOVED from emitter.py.
#   Do NOT re-introduce them. Word handles visual word-wrap automatically.
#   Hard line breaks only occur between blocks (one block = one paragraph).
#
# ─────────────────────────────────────────────────────────────────────────────
# FILE: spec_engine/document_builder.py
# PURPOSE: Assembles the complete DOCX from all parts in the correct order
# ─────────────────────────────────────────────────────────────────────────────
#
#   Document assembly order:
#     1. write_title_page()       — Style/title page (Fig03 UFM)
#     2. write_caption()          — Texas district court caption (Page 2)
#     3. Transcript body          — Q/A/SP/PN lines via emit_line()
#     4. write_post_record_section() — Post-record spellings colloquy
#     5. write_witness_index()    — Witness examination index
#     6. write_exhibit_index()    — Exhibit listing
#     7. write_certificate()      — Reporter certification page
#     8. write_cert_exhibits()    — Exhibit certification page
#     9. write_changes_signature()— Changes and Signature page (UFM Fig 7/7A)
#
#   NOTE: corrections_log is intentionally excluded from DOCX output.
#   It is printed to the terminal run log only — not part of the certified
#   transcript. Never add it back to the DOCX.
#
# ─────────────────────────────────────────────────────────────────────────────
# FILE: spec_engine/pages/caption.py
# PURPOSE: Texas district court caption page (Page 2)
# ─────────────────────────────────────────────────────────────────────────────
#
#   Contains:
#     - Case style (Plaintiff vs. Defendant)
#     - Court name and judicial district
#     - Cause number
#     - Deponent name, date, time, location
#     - Reporter credentials line
#     - Appearances block (FOR THE PLAINTIFF: / FOR THE DEFENDANT:)
#
# ─────────────────────────────────────────────────────────────────────────────
# FILE: spec_engine/pages/certificate.py
# PURPOSE: Reporter's certification page (last page)
# ─────────────────────────────────────────────────────────────────────────────
#
#   Contains:
#     - "I, Miah Bardot, Certified Court Reporter..."
#     - Certification language
#     - Signature line
#     - CSR number
#
# ─────────────────────────────────────────────────────────────────────────────
# FILE: spec_engine/pages/_lined_page.py
# PURPOSE: Shared helper that builds the 25-line bordered table format
# ─────────────────────────────────────────────────────────────────────────────
#
#   Used by: title_page.py, changes_signature.py, cert_exhibits.py,
#            exhibit_index.py, witness_index.py
#
#   Creates the standard UFM bordered page with 25 numbered lines.
#   Do NOT use this for the transcript body — only for the pre/post pages.
#
# ─────────────────────────────────────────────────────────────────────────────
# FILE: spec_engine/models.py — LineType enum
# PURPOSE: Defines the legal line types the pipeline understands
# ─────────────────────────────────────────────────────────────────────────────
#
#   LineType.Q      — Question line
#   LineType.A      — Answer line
#   LineType.SP     — Speaker label line (colloquy)
#   LineType.PN     — Parenthetical line
#   LineType.FLAG   — Scopist flag
#   LineType.HEADER — Examination header (EXAMINATION / CROSS-EXAMINATION)
#   LineType.BY     — BY attribution line
#   LineType.PLAIN  — Plain text (no special formatting)

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — HOW TO IMPLEMENT A NEW FORMATTING RULE
# ══════════════════════════════════════════════════════════════════════════════
#
# DECISION TREE — find the right place for your change:
#
# "I want to change something in the TEXTBOX display"
#   → spec_engine/emitter.py → emit_blocks()
#   → This is plain text. No bold. No color. Tabs and newlines only.
#
# "I want to change something in the DOCX for ALL line types"
#   → spec_engine/emitter.py → _set_paragraph_format() or _add_run()
#   → Example: change line spacing from double to single
#
# "I want to change something in the DOCX for ONE specific line type"
#   → spec_engine/emitter.py → emit_q_line() / emit_a_line() / emit_sp_line()
#     / emit_pn_line() / emit_flag_line() / emit_header_line() / emit_by_line()
#   → Example: make Q. lines bold, or change the parenthetical color
#
# "I want to change the font or font size"
#   → spec_engine/emitter.py → FONT_NAME and FONT_SIZE constants
#   → Changing these affects every paragraph in the transcript body
#
# "I want to change tab stop positions (indentation)"
#   → spec_engine/emitter.py → TAB_720, TAB_1440, TAB_2160 constants
#   → TAB_720: where Q./A. label sits
#   → TAB_1440: where Q./A. text begins
#   → TAB_2160: where speaker label text begins
#   → NOTE: Twips conversion: 1 inch = 1440 twips
#
# "I want to change the page margins"
#   → spec_engine/emitter.py → create_document()
#   → section.left_margin, section.right_margin, etc.
#   → Current: 1.25" left / 1.0" right / 1.0" top / 1.0" bottom
#
# "I want to change the caption page"
#   → spec_engine/pages/caption.py → write_caption()
#
# "I want to change the certificate page"
#   → spec_engine/pages/certificate.py → write_certificate()
#
# "I want to add a new page type"
#   → Create a new file in spec_engine/pages/
#   → Add its import and call to spec_engine/document_builder.py
#   → Follow the pattern of an existing page file
#
# "I want to change how line numbers look"
#   → spec_engine/emitter.py → emit_line_numbered()
#   → LineNumberTracker class → LINES_PER_PAGE constant
#
# "I want to add a new visual style (e.g. a new color, a new bold pattern)"
#   → Add a new COLOR_ constant at the top of emitter.py
#   → Add a new emit_*_line() function following existing patterns
#   → Add the new LineType to spec_engine/models.py if needed
#   → Add the dispatch mapping in emit_line()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — FORMATTING RULES THAT MUST NEVER BE VIOLATED
# ══════════════════════════════════════════════════════════════════════════════
#
# RULE F1 — ONE PARAGRAPH PER BLOCK
#   Every emit_*_line() function produces exactly one paragraph.
#   Never loop over wrapped lines. Never call add_paragraph() more than once
#   per emit call. Word handles visual word-wrap at the page margin.
#
# RULE F2 — NO HARD LINE BREAKS INSIDE BLOCKS
#   textwrap, _wrap_lines(), WRAP_WIDTH, and QA_WRAP_WIDTH have been removed.
#   Do not add them back. A \n inside a paragraph breaks tab indentation.
#
# RULE F3 — TEXTBOX IS PLAIN TEXT ONLY
#   emit_blocks() produces a plain string. No bold, no color, no font.
#   Use \t for indentation. Use \n between blocks only.
#
# RULE F4 — CORRECTIONS LOG NEVER IN DOCX
#   write_corrections_log() is intentionally commented out of document_builder.py.
#   The corrections log appears in the terminal run log only.
#   Never add it back to the DOCX output.
#
# RULE F5 — CERTIFIED AND REVIEW DOCX ARE ALWAYS SEPARATE
#   core/confidence_docx_exporter.py produces the _review.docx.
#   spec_engine/document_builder.py produces the certified transcript.
#   Never merge them.
#
# RULE F6 — COLORS ARE SEMANTIC
#   COLOR_ORANGE: scopist flags only (bold orange #B45F06)
#   COLOR_NAVY:   parentheticals only (navy #1E3A5F)
#   COLOR_BLACK:  everything else
#   Do not introduce new colors without updating this rule.
#
# RULE F7 — TAB STOPS ARE FIXED
#   The three tab stops (0.5" / 1.0" / 1.5") implement the Texas UFM layout.
#   Do not change them without explicit instruction. Changing them shifts the
#   entire transcript column layout.
#
# RULE F8 — DOUBLE SPACING IS MANDATORY
#   _set_paragraph_format() sets WD_LINE_SPACING.DOUBLE on every paragraph.
#   space_before and space_after are always Pt(0).
#   Do not change this. Double spacing is a UFM legal requirement.
#
# RULE F9 — FONT IS FIXED
#   Courier New 12pt is the Texas UFM standard for court transcripts.
#   Do not change FONT_NAME or FONT_SIZE without explicit instruction.

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — VERIFY THE CHANGE BEFORE COMMITTING
# ══════════════════════════════════════════════════════════════════════════════

```powershell
cd C:\Users\james\PycharmProjects\depo_transcribe

# 1. Compile check — must pass before any further testing
python -m py_compile spec_engine\emitter.py
python -m py_compile spec_engine\document_builder.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: compile error — fix before proceeding" -ForegroundColor Red
    exit 1
}
Write-Host "PASS: compiles clean" -ForegroundColor Green

# 2. Visual structure test — verify one paragraph per block, correct prefixes
python -c "
import sys
sys.path.insert(0, r'C:\Users\james\PycharmProjects\depo_transcribe')
from spec_engine.emitter import (
    emit_q_line, emit_a_line, emit_sp_line,
    emit_pn_line, emit_flag_line, emit_header_line,
    emit_blocks, create_document
)
from spec_engine.models import Block, BlockType

LONG = 'This is a long line of text that should not be wrapped at any character boundary whatsoever because Word handles visual word-wrap automatically at the right margin.'

doc = create_document()
n0 = len(doc.paragraphs)

emit_q_line(doc, LONG)
emit_a_line(doc, LONG)
emit_sp_line(doc, 'THE REPORTER:  ' + LONG)
emit_pn_line(doc, '(Whereupon, the deposition commenced at 9:58 a.m.)')
emit_flag_line(doc, '[SCOPIST: FLAG 1: verify from audio]')
emit_header_line(doc, 'EXAMINATION')

added = len(doc.paragraphs) - n0
print(f'Paragraphs added: {added} (should be 6 — one per emit call)')
print('PASS' if added == 6 else 'FAIL — extra paragraphs detected (wrapping re-introduced?)')
print()

# Check Q line format
q_para = doc.paragraphs[n0]
q_text = ''.join(r.text for r in q_para.runs)
print(f'Q line text: {repr(q_text[:60])}')
print('Q format OK' if q_text.startswith('\tQ.  ') else 'FAIL: Q prefix wrong')

# Check A line format
a_para = doc.paragraphs[n0 + 1]
a_text = ''.join(r.text for r in a_para.runs)
print('A format OK' if a_text.startswith('\tA.  ') else 'FAIL: A prefix wrong')

# Check SP line has bold label
sp_para = doc.paragraphs[n0 + 2]
has_bold = any(r.bold for r in sp_para.runs)
print('SP bold label OK' if has_bold else 'FAIL: SP label not bold')
print()

# Check emit_blocks — no inner newlines
blocks = [
    Block(speaker_id=0, speaker_name='THE REPORTER', speaker_role='REPORTER',
          text=LONG, block_type=BlockType.SP, start=0.0, end=5.0),
    Block(speaker_id=1, speaker_name='MR.  DAVIS', speaker_role='EXAMINER',
          text=LONG, block_type=BlockType.Q, start=5.0, end=10.0),
    Block(speaker_id=2, speaker_name='MS.  TREVINO', speaker_role='WITNESS',
          text=LONG, block_type=BlockType.A, start=10.0, end=15.0),
]
result = emit_blocks(blocks)
result_lines = result.split(chr(10))
print(f'emit_blocks line count: {len(result_lines)} (should be 3 — one per block)')
for i, line in enumerate(result_lines):
    inner_nl = chr(10) in line
    print(f'  Block {i+1}: {len(line)} chars, inner newline: {inner_nl}')
    if inner_nl:
        print('  FAIL: inner newline — hard wrapping still present')
    else:
        print('  PASS')
"

# 3. Full test suite
python -m pytest spec_engine\tests\ -q --tb=short 2>&1 | tail -5
```

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — COMMON FORMATTING CHANGES AND HOW TO IMPLEMENT THEM
# ══════════════════════════════════════════════════════════════════════════════
#
# ── CHANGE THE Q./A. PREFIX FORMAT ────────────────────────────────────────────
#
#   Current:  \tQ.  {text}   (tab + Q. + two spaces + text)
#   To change: edit emit_q_line() and emit_a_line() in emitter.py
#
#   Example — change to "Q.  " with no leading tab:
#     _add_run(para, f'Q.  {_clean(text)}')
#
# ── CHANGE SPEAKER LABEL FORMAT ───────────────────────────────────────────────
#
#   Current:  \t\t\t{BOLD LABEL}:  {text}   (3 tabs + bold label + 2 spaces)
#   To change: edit emit_sp_line() in emitter.py
#
#   The label is split from content by _split_speaker_text(text).
#   The label run has bold=True. The content run has bold=False.
#
# ── CHANGE PARENTHETICAL FORMAT ───────────────────────────────────────────────
#
#   Current:  \t\t\t\t{text}   (4 tabs + text, navy color)
#   To change: edit emit_pn_line() in emitter.py
#   Color constant: COLOR_NAVY = RGBColor(0x1E, 0x3A, 0x5F)
#
# ── CHANGE SCOPIST FLAG COLOR ─────────────────────────────────────────────────
#
#   Current:  bold orange   COLOR_ORANGE = RGBColor(0xB4, 0x5F, 0x06)
#   To change: edit COLOR_ORANGE constant at top of emitter.py
#   The flag function: emit_flag_line() uses bold=True, color=COLOR_ORANGE
#
# ── CHANGE FONT ───────────────────────────────────────────────────────────────
#
#   Current:  Courier New 12pt
#   To change: edit FONT_NAME and FONT_SIZE constants at top of emitter.py
#   Note: Changing font affects every paragraph in the transcript body
#
# ── CHANGE LINE SPACING ────────────────────────────────────────────────────────
#
#   Current:  WD_LINE_SPACING.DOUBLE (mandatory for UFM)
#   To change: edit _set_paragraph_format() in emitter.py
#   Also: space_before = Pt(0), space_after = Pt(0) — both must stay 0
#
# ── CHANGE TAB STOP POSITIONS ─────────────────────────────────────────────────
#
#   Current tab stops (twips → inches):
#     TAB_720  =  720 twips = 0.50"  Q./A. label
#     TAB_1440 = 1440 twips = 1.00"  Q./A. text start
#     TAB_2160 = 2160 twips = 1.50"  Speaker text start
#
#   To change: edit the constant values at top of emitter.py
#   Formula: inches × 1440 = twips
#   Example: to move speaker text to 2.0":  TAB_2160 = 2880
#
# ── CHANGE PAGE MARGINS ────────────────────────────────────────────────────────
#
#   Current margins:
#     Left:   1.25" (1800 twips)  — UFM standard
#     Right:  1.00" (1440 twips)
#     Top:    1.00" (1440 twips)
#     Bottom: 1.00" (1440 twips)
#
#   To change: edit create_document() in emitter.py
#   Formula: inches × 1440 = twips
#
# ── CHANGE LINES PER PAGE ─────────────────────────────────────────────────────
#
#   Current:  25 lines per transcript body page (UFM standard)
#   To change: edit LineNumberTracker.LINES_PER_PAGE in emitter.py
#   Note: Changing this affects page break positions in line-numbered output
#
# ── ADD A BRAND NEW LINE TYPE ─────────────────────────────────────────────────
#
#   1. Add the new value to LineType enum in spec_engine/models.py
#   2. Add a new emit_*_line() function in emitter.py
#   3. Add the dispatch entry in emit_line() in emitter.py
#   4. Add handling in emit_blocks() for the textbox plain-text version
#   5. Add handling in emit_line_numbered() for line-numbered output
#   6. Add classifier logic in spec_engine/classifier.py if needed

# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 — DESCRIBE YOUR NEW FORMATTING RULE HERE
# ══════════════════════════════════════════════════════════════════════════════
#
# [FILL IN: Describe the formatting change you want]
#
# CHANGE REQUESTED:
#   [FILL IN]
#
# WRONG (current output):
#   [FILL IN — paste exact text or describe visual]
#
# RIGHT (desired output):
#   [FILL IN — paste exact text or describe visual]
#
# WHICH STEP APPLIES (from Step 7 above):
#   [FILL IN — e.g. "Change the Q./A. prefix format"]
#
# WHICH FILE TO EDIT (from the architecture in Step 3):
#   [FILL IN — e.g. "spec_engine/emitter.py → emit_q_line()"]
