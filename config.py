"""
config.py — application runtime and pipeline configuration.

This is the top-level config module used by the active audio/transcription
pipeline and app runtime. It is distinct from core/config.py, which stores
shared core-layer constants such as job-config and keyterm settings.

Edit this file to change pipeline/runtime behavior without touching pipeline
code. API keys are loaded from the .env file — never hardcode them here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_HERE / ".env")

# ── API Keys ──────────────────────────────────────────────────────────────────
# Set these in your .env file — do not hardcode values here.
DEEPGRAM_API_KEY  = os.getenv("DEEPGRAM_API_KEY",  "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Deepgram model ────────────────────────────────────────────────────────────
# "nova-3"         — standard depositions (default)
# "nova-3-medical" — expert witness / heavy medical vocabulary
DEEPGRAM_MODEL = "nova-3"

# Deepgram upload timeout settings
DEEPGRAM_CONNECTION_TIMEOUT = 60      # seconds to establish connection
DEEPGRAM_READ_TIMEOUT = 600           # seconds to wait for response
DEEPGRAM_WRITE_TIMEOUT = 600          # seconds to complete upload
DEEPGRAM_CHUNK_SIZE_LIMIT_MB = 200    # warn if chunk exceeds this

# ── Audio normalization ───────────────────────────────────────────────────────
# Output sample rate after FFmpeg normalization.
# 24 kHz preserves the 4–8 kHz consonant band critical for legal speech
# accuracy (names, case numbers, plural endings).
# Must match the sample_rate sent to Deepgram.
TARGET_SAMPLE_RATE = 24000

# ── Chunking ──────────────────────────────────────────────────────────────────
# Maximum duration per audio chunk in seconds.
# 3600 = 1 hour. Files shorter than this are sent as a single chunk.
#
# WHY 3600 (raised from 600 in 2026-04):
# Deepgram assigns its own speaker IDs per call. When a deposition was
# split into multiple chunks, pipeline/assembler.py's _build_speaker_remap
# tried to reconcile chunk-local speaker IDs by temporal overlap inside
# the 20-second CHUNK_OVERLAP_SECONDS window. That heuristic fails when
# a speaker doesn't actually speak during the overlap window — their
# chunk-local ID has no anchor and can collide with a different
# global speaker downstream. The visible symptom was the witness's
# audio being labeled as opposing counsel (Symptom A).
#
# Single-call Deepgram gets consistent speaker IDs throughout, which
# is what the Playground does. Raising the chunk limit lets typical
# depositions (under 1 hour of recorded audio) skip chunking entirely.
# Deepgram's pre-recorded API limit is 2 GB / 10 hours; we are well
# under both at 1 hour of 24 kHz mono PCM (~172 MB).
#
# Multi-hour depositions still chunk, but with 6x fewer chunk
# boundaries — same cross-chunk-merge risk per boundary, fewer
# boundaries.
CHUNK_DURATION_SECONDS = 3600

# Overlap between adjacent chunks in seconds.
# Prevents words at chunk boundaries from being dropped.
# The assembler deduplicates the overlapping region.
CHUNK_OVERLAP_SECONDS = 20

# ── Default keyterms for SA Legal Solutions depositions ────────────────────────
# These help Deepgram lock onto the reporter, filing firm, and common phrases
# before case-specific keyterms are merged from the intake form.
DEFAULT_KEYTERMS = [
    "Miah Bardot",
    "Bardot",
    "CSR 12129",
    "SA Legal Solutions",
    "San Antonio",
    "objection form",
    "pass the witness",
]

# ── Confidence flagging ───────────────────────────────────────────────────────
# Words with Deepgram confidence below this threshold are written to the
# flagged_words.txt output file for human review.
# Range: 0.0–1.0. Default 0.85 flags the bottom ~5% of word confidence.
LOW_CONFIDENCE_THRESHOLD = 0.85

# ── File paths ────────────────────────────────────────────────────────────────
# All output files (transcript, JSON, flagged words) are written here.
OUTPUT_DIR = str(_HERE / "output")

# Temporary files created during pipeline processing are stored here.
# This directory is auto-created and auto-cleaned after each run.
TEMP_DIR = str(_HERE / "temp")

# ── Processing mode ───────────────────────────────────────────────────────────
# STRICT_MODE: when True, processing aborts if validate_blocks() returns any
# errors. When False, errors are recorded but processing continues.
STRICT_MODE = False
