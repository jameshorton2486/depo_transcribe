"""
spec_engine — DepoPro Transcript Processing Spec v1.0 implementation.

Transforms Deepgram DOCX output into Texas UFM court-ready legal transcripts.

Author reference: Miah Bardot, CSR No. 12129, SA Legal Solutions
Spec version: 1.0, March 2026

Pipeline (8 steps):
  Step 1: parse_blocks()       — Deepgram DOCX → List[Block]
  Step 2: load_job_config()    — JobConfig (speaker map, case info, spellings)
  Step 3: clean_block()        — Apply all text corrections in priority order
  Step 4: classify_block()     — Assign LineType (Q/A/SP/PN/FLAG)
  Step 5: emit_line()          — Write formatted paragraph to output Document
  Step 6: write_corrections_log() — Page 1
  Step 7: write_caption()      — Page 2
  Step 8: write_certificate()  — Final page

Do NOT import from this package until Phase 3 is complete.
"""

__version__ = "1.0.0"
