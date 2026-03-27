"""
config.py — Depo-Pro Tools
Central configuration for all pipeline constants and API keys.

Edit this file to change any pipeline behaviour without touching pipeline code.
API keys are loaded from the .env file — never hardcode them here.
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
# 600 = 10 minutes. Files shorter than this are sent as a single chunk.
CHUNK_DURATION_SECONDS = 600

# Overlap between adjacent chunks in seconds.
# Prevents words at chunk boundaries from being dropped.
# The assembler deduplicates the overlapping region.
CHUNK_OVERLAP_SECONDS = 20

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
