import re


QUESTION_WORDS = {
    "who", "what", "when", "where", "why", "how",
    "did", "do", "does", "can", "could", "would",
    "is", "are", "was", "were",
}


def is_question(text: str) -> bool:
    t = text.strip().lower()

    if not t:
        return False

    if t.endswith("?"):
        return True

    first = t.split(" ", 1)[0]
    return first in QUESTION_WORDS


def normalize_speaker(speaker: str) -> str:
    if speaker is None:
        return "UNKNOWN"

    if str(speaker) == "0":
        return "THE REPORTER"

    if str(speaker) == "1":
        return "THE WITNESS"

    return f"SPEAKER {speaker}"


def two_space_fix(text: str) -> str:
    return re.sub(r"([.!?])\s+", r"\1  ", text)


def format_blocks(blocks):
    """
    blocks = list of:
    {
        "speaker": int or str,
        "text": str
    }
    """

    output = []
    prev_was_question = False

    for b in blocks:
        text = b.get("text", "").strip()
        speaker = b.get("speaker")

        if not text:
            continue

        text = two_space_fix(text)

        if is_question(text):
            line = f"Q.  {text}"
            prev_was_question = True
        elif prev_was_question:
            line = f"A.  {text}"
            prev_was_question = False
        else:
            spk = normalize_speaker(speaker)
            line = f"{spk}:  {text}"

        output.append(line)

    return "\n".join(output)
