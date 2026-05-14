"""One-shot integrity inspector for the Phase-A raw store output."""
from __future__ import annotations

import json
import sys
from pathlib import Path

case = Path(sys.argv[1])
raw_store_path = next(case.glob("Deepgram/raw_dg_response_*.json"))
canon_path = case / "Deepgram" / "raw_deepgram.json"

new_file = json.loads(raw_store_path.read_text(encoding="utf-8"))
canon = json.loads(canon_path.read_text(encoding="utf-8"))

print("--- New immutable raw store ---")
print(f"path: {raw_store_path.name}")
print(f"schema_version: {new_file['schema_version']}")
print(f"saved_at_utc: {new_file['saved_at_utc']}")
print(f"saved_at_local: {new_file['saved_at_local']}")
print(f"audio_file: {new_file['audio_file']}")
print(f"model: {new_file['model']}")
print(f"chunk_count: {new_file['chunk_count']}")
print()

print("--- Per-chunk integrity ---")
total_words = 0
total_utts = 0
for c in new_file["chunks"]:
    resp = c["deepgram_response"]
    if resp:
        results = resp.get("results", {}) or {}
        channels = results.get("channels", []) or []
        words = []
        if channels:
            alts = channels[0].get("alternatives", []) or []
            if alts:
                words = alts[0].get("words", []) or []
        utts = results.get("utterances", []) or []
        total_words += len(words)
        total_utts += len(utts)
        print(
            f"  chunk {c['index']}: offset={c['start_seconds']:.0f}s "
            f"words={len(words)} utterances={len(utts)}"
        )
print()
print(f"Immutable raw: total native words across chunks: {total_words}")
print(f"Immutable raw: total native utterances across chunks: {total_utts}")
print()

print("--- Canonical raw_deepgram.json (post-mutation) ---")
print(f"chunk_count: {canon.get('chunk_count')}")
print(f"raw_utterances (post per-chunk merge): {len(canon.get('raw_utterances') or [])}")
print(f"utterances (post assembler merge): {len(canon.get('utterances') or [])}")
print(f"words (assembled): {len(canon.get('words') or [])}")
print()

print("--- Sample first-chunk first-utterance comparison ---")
# Verify the first utterance in the immutable raw matches a first
# utterance in canon["chunks"][0] (which is the same payload).
new_first_chunk = new_file["chunks"][0]["deepgram_response"]
canon_first_chunk = (canon.get("chunks") or [None])[0]
if new_first_chunk and canon_first_chunk:
    n_utts = new_first_chunk.get("results", {}).get("utterances", []) or []
    c_utts = canon_first_chunk.get("results", {}).get("utterances", []) or []
    print(f"new file chunk 0 native utterance count: {len(n_utts)}")
    print(f"canon  file chunk 0 native utterance count: {len(c_utts)}")
    if n_utts and c_utts:
        n_first = n_utts[0]
        c_first = c_utts[0]
        print(f"new first utt:   speaker={n_first.get('speaker')} start={n_first.get('start')} text={n_first.get('transcript')[:80]!r}")
        print(f"canon first utt: speaker={c_first.get('speaker')} start={c_first.get('start')} text={c_first.get('transcript')[:80]!r}")
        match = n_first.get("transcript") == c_first.get("transcript") and n_first.get("speaker") == c_first.get("speaker")
        print(f"Match: {match}")
