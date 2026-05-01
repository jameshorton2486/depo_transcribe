import logging

# Initialize logger
logger = logging.getLogger(__name__)

def build_blocks(alt):
    """
    Parses transcription data into structured blocks.
    Prioritizes paragraph-based parsing for better speaker grouping.
    """
    blocks = []

    # ================================
    # 🔥 PRIORITY 1 — PARAGRAPHS
    # ================================
    if "paragraphs" in alt and alt["paragraphs"].get("paragraphs"):
        logger.info("[BlockBuilder] Using paragraph-based parsing")

        for para in alt["paragraphs"]["paragraphs"]:
            speaker = para.get("speaker", "UNKNOWN")
            text = para.get("text", "").strip()

            if not text:
                continue

            blocks.append({
                "speaker": speaker,
                "text": text,
                "type": "paragraph"
            })

        # Return immediately if paragraphs are found to avoid fallback logic
        return blocks

    # ================================
    # 🪵 FALLBACK — UTTERANCES
    # ================================
    if "utterances" in alt:
        logger.info("[BlockBuilder] Falling back to utterance-based parsing")
        
        for utt in alt["utterances"]:
            speaker = utt.get("speaker", "UNKNOWN")
            text = utt.get("text", "").strip()

            if not text:
                continue

            blocks.append({
                "speaker": speaker,
                "text": text,
                "type": "utterance"
            })

    return blocks