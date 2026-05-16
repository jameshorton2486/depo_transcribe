"""Anthropic-backed transcript cleanup for clean-format output."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from clean_format.low_confidence_markers import (
    inject_markers,
    validate_marker_round_trip,
)
from clean_format.prompt import CLEAN_FORMAT_SYSTEM_PROMPT
from config import ANTHROPIC_API_KEY, LOW_CONFIDENCE_THRESHOLD
from core.config import AI_MODEL, MIN_UTTERANCE_RETENTION_DOCUMENT

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore[assignment]

CHUNK_CHAR_LIMIT = 80_000
# Sonnet 4.6 synchronous Messages API hard cap is 64,000 output tokens; we
# stay well below that. 32,768 gives ~2.6x headroom over the prior 12,288
# value, which was insufficient for 80,000-char input chunks where the
# cleaned output is roughly the same size as the input. Raising max_tokens
# has no rate-limit downside per Anthropic docs — only actually-generated
# output tokens count against OTPM.
MAX_TOKENS = 32_768

# ── Sentence / punctuation normalisation ─────────────────────────────────────
# Two spaces after sentence-ending . or ? before the next non-space character.
# Abbreviation titles (Dr., Mr., etc.) are tokenised before this runs so their
# trailing period is not double-spaced.
_SENTENCE_DOUBLE_SPACE_RE = re.compile(r"([.?!])\s+(?=\S)")

# Times must have no leading zero: "08:12 a.m." → "8:12 a.m."
_LEADING_ZERO_TIME_RE = re.compile(r"\b0([1-9]):(\d{2}\s*[ap]\.m\.)", re.IGNORECASE)

# Actual em-dash / en-dash → spaced double-hyphen (Morson's / UFM rule)
_EM_DASH_RE = re.compile(r"\s*[—–]\s*")

# Normalise any run of spaces around "--" to exactly " -- "
_SPACED_DOUBLE_HYPHEN_RE = re.compile(r"\s*--\s*")

# Mid-word false-start dash ("run--ning") must not be touched by the hyphen
# normaliser above; protect it with a placeholder round-trip.
_MIDWORD_FALSE_START_RE = re.compile(r"(?<=\w)--(?=\s*[A-Za-z])")

# Honorific spacing rule: MR./MS./DR. inside ALL-CAPS speaker labels must
# be followed by exactly one space (canonical UFM / Miah Bardot spec,
# confirmed by James 2026-05-15). Collapses any pre-existing wider spacing
# back down to a single space.
# Example: "MR.  DUNNELL" → "MR. DUNNELL"
# Example: "MR. DUNNELL"  → "MR. DUNNELL"  (idempotent)
_HONORIFIC_SPACING_RE = re.compile(r"\b(MR|MS|DR)\.\s+(?=[A-Z])")

# ── Line-type detection regexes ───────────────────────────────────────────────
# Q/A lines: canonical input is "\tQ.\t…" / "\tA.\t…"; the formatter also
# tolerates the legacy bare "Q.\t…" / "A.\t…" form from older AI prompts.
_QA_LINE_RE = re.compile(r"^\t?(?P<label>[QA])\.\t(?P<text>.*)$")

# Speaker label lines: zero or more leading tabs, then ALL-CAPS label, colon,
# then either one tab (legacy intermediate) or one-or-more spaces (canonical
# "two spaces after colon" form). The output is always canonical regardless
# of which input variant matched.
_LABEL_LINE_RE = re.compile(
    r"^\t*(?P<label>[A-Z][A-Z .'\-]+?):[ \t]+(?P<text>.+)$"
)

# Parenthetical lines: any leading tabs, then (…). Canonical output is four
# leading tabs.
_PAREN_LINE_RE = re.compile(r"^\t*\((?P<content>[^)]+\.?)\)\s*$")

# Raw Deepgram "Speaker N:" lines in the input (used to count utterances).
_INPUT_UTTERANCE_RE = re.compile(r"^Speaker\s+\d+:", re.MULTILINE)

# Formatted utterance lines in the output (used to verify retention).
# Counts canonical "\tQ.\t", "\tA.\t", and "\t\t\tLABEL:" patterns,
# plus legacy variants for tolerance during the cutover.
_OUTPUT_UTTERANCE_RE = re.compile(
    r"^\t?(?:Q|A)\.\t|^\t{0,3}[A-Z][A-Z .'\-]+:[ \t]",
    re.MULTILINE,
)

# Dunnell mis-attribution: Deepgram sometimes labels Billy Dunnell's
# appearance statement as a VIDEOGRAPHER block.  Detect and relabel.
# Handles both legacy ("VIDEOGRAPHER:\t…") and canonical
# ("\t\t\tTHE VIDEOGRAPHER:  …") input shapes.
_DUNNELL_RE = re.compile(
    r"^\t*(?:THE\s+)?VIDEOGRAPHER:\s+(?P<text>Billy\s+Dunnell\s+here\s+on\s+behalf\s+of\s+.*)$",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


class OutputTruncatedError(RuntimeError):
    """Raised when Anthropic returns stop_reason='max_tokens' for a chunk."""

    def __init__(self, chunk_index: int, chunk_count: int, model: str):
        self.chunk_index = chunk_index
        self.chunk_count = chunk_count
        self.model = model
        super().__init__(
            f"Output truncated at max_tokens on chunk {chunk_index}/{chunk_count} "
            f"(model={model}). Cleanup aborted to prevent silent content loss."
        )


class ContentLossError(RuntimeError):
    """Raised when the AI cleanup pass drops too many utterances."""

    def __init__(self, input_count: int, output_count: int, threshold: float):
        self.input_count = input_count
        self.output_count = output_count
        self.threshold = threshold
        self.ratio = output_count / input_count if input_count else 0.0
        super().__init__(
            f"Content loss detected: {output_count}/{input_count} utterances "
            f"({self.ratio:.1%}) below threshold {threshold:.0%}. "
            f"Cleanup aborted to prevent silent content loss."
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_whitespace(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _speaker_blocks(raw_text: str) -> list[str]:
    blocks = [block.strip() for block in (raw_text or "").split("\n\n")]
    return [block for block in blocks if block]


def split_transcript(
        raw_text: str, max_chunk_chars: int = CHUNK_CHAR_LIMIT
) -> list[str]:
    """Split raw speaker blocks into chunks near the requested character limit."""
    blocks = _speaker_blocks(raw_text)
    if not blocks:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for block in blocks:
        block_size = len(block) + 2
        if current and current_size + block_size > max_chunk_chars:
            chunks.append("\n\n".join(current))
            current = [block]
            current_size = block_size
            continue

        if not current and block_size > max_chunk_chars:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            running: list[str] = []
            running_size = 0
            for line in lines:
                line_size = len(line) + 1
                if running and running_size + line_size > max_chunk_chars:
                    chunks.append("\n".join(running))
                    running = [line]
                    running_size = line_size
                else:
                    running.append(line)
                    running_size += line_size
            if running:
                chunks.append("\n".join(running))
            current = []
            current_size = 0
            continue

        current.append(block)
        current_size += block_size

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _case_meta_for_prompt(case_meta: dict[str, Any]) -> dict[str, Any]:
    ordered_keys = [
        "cause_number",
        "court",
        "county",
        "judicial_district",
        "deposition_date",
        "start_time",
        "end_time",
        "witness_name",
        "witness_credentials",
        "plaintiff_name",
        "defendant_names",
        "reporter_name",
        "reporter_csr",
        "attorneys",
        "videographer_name",
        # Phase 2: NOD-derived authoritative data.
        # confirmed_spellings: wrong->right dict the model applies as proper-noun corrections.
        # deepgram_keyterms: list of NOD entities given to Deepgram; lets the model
        # preserve those spellings as canonical.
        "confirmed_spellings",
        "deepgram_keyterms",
    ]
    return {
        key: case_meta.get(key)
        for key in ordered_keys
        if case_meta.get(key) not in (None, "", [], {})
    }


def build_user_message(
        chunk: str, case_meta: dict[str, Any], chunk_index: int, chunk_count: int
) -> str:
    meta_json = json.dumps(
        _case_meta_for_prompt(case_meta), indent=2, ensure_ascii=False
    )
    return (
        f"Case metadata:\n{meta_json}\n\n"
        f"Transcript chunk {chunk_index} of {chunk_count}:\n"
        f"{chunk}\n"
    )


def _response_text(response: Any) -> str:
    parts = []
    for item in getattr(response, "content", []) or []:
        text = getattr(item, "text", "")
        if text:
            parts.append(text)
    output = "\n".join(parts).strip()
    if not output:
        raise RuntimeError("Anthropic response did not include text content")
    return output


def _response_stop_reason(response: Any) -> str:
    return getattr(response, "stop_reason", "") or ""


def _count_input_utterances(text: str) -> int:
    return len(_INPUT_UTTERANCE_RE.findall(text or ""))


def _count_output_utterances(text: str) -> int:
    output = text or ""
    count = len(_OUTPUT_UTTERANCE_RE.findall(output))
    return count or len(_INPUT_UTTERANCE_RE.findall(output))


def _normalize_body_text(text: str) -> str:
    """
    Apply Miah Bardot / Texas UFM typographic rules to body text.

    Rules applied in order:
    1. Protect mid-word false-start dashes ("run--ning") from dash normalisation.
    2. Remove leading zeros from times ("08:12 a.m." → "8:12 a.m.").
    3. Convert em-dashes and en-dashes to spaced double-hyphen (" -- ").
    4. Normalise any existing "--" spacing to exactly " -- ".
    5. Protect common lowercase title abbreviations so their trailing period
       is NOT double-spaced (Dr., Mr., Ms., Mrs. → one space, not two).
       Uppercase honorifics inside labels are handled separately at label
       emission time.
    6. Apply two-space rule after every sentence-ending . ? ! before the next
       non-space character.
    7. Restore the protected title tokens.
    8. Restore the protected mid-word dash.
    9. Collapse any run of more than two consecutive spaces to exactly two
       (prevents triple-spacing from interacting patterns).
    """
    # Step 1 – protect mid-word false-start dashes
    text = _MIDWORD_FALSE_START_RE.sub("__FALSESTART_DASH__", text)

    # Step 2 – leading-zero time fix
    text = _LEADING_ZERO_TIME_RE.sub(r"\1:\2", text)

    # Steps 3–4 – dash normalisation
    text = _EM_DASH_RE.sub(" -- ", text)
    text = _SPACED_DOUBLE_HYPHEN_RE.sub(" -- ", text)

    # Step 5 – protect lowercase titles (one space preserved)
    for title, token in {
        "Dr. ": "__TITLE_DR__",
        "Mr. ": "__TITLE_MR__",
        "Ms. ": "__TITLE_MS__",
        "Mrs. ": "__TITLE_MRS__",
    }.items():
        text = text.replace(title, token)

    # Step 6 – two spaces after sentence-ending punctuation
    text = _SENTENCE_DOUBLE_SPACE_RE.sub(r"\1  ", text)

    # Step 7 – restore lowercase titles
    for token, title in {
        "__TITLE_DR__": "Dr. ",
        "__TITLE_MR__": "Mr. ",
        "__TITLE_MS__": "Ms. ",
        "__TITLE_MRS__": "Mrs. ",
    }.items():
        text = text.replace(token, title)

    # Step 8 – restore mid-word dash
    text = text.replace("__FALSESTART_DASH__", "--")

    # Step 9 – collapse triple+ spaces to two (never more than two)
    text = re.sub(r"   +", "  ", text)

    return text


def _normalize_label_honorifics(label: str) -> str:
    """
    Apply the single-space-after-honorific rule for ALL-CAPS speaker labels.

    Canonical UFM / Miah Bardot spec (confirmed by James 2026-05-15):
      MR.  DUNNELL → MR. DUNNELL
      MS.  MALONEY → MS. MALONEY
      DR.  KARAM   → DR. KARAM
    Collapses any whitespace run between an honorific period and the
    following capital letter to exactly one space. Idempotent on input
    that is already single-spaced.
    """
    return _HONORIFIC_SPACING_RE.sub(lambda m: f"{m.group(1)}. ", label)


def _emit_canonical_qa(label_letter: str, text: str) -> str:
    """Emit a canonical Q. or A. line: \\tQ.\\t<text> or \\tA.\\t<text>."""
    return f"\t{label_letter}.\t{_normalize_body_text(text)}"


def _emit_canonical_speaker(label: str, text: str) -> str:
    """Emit a canonical speaker colloquy line: \\t\\t\\t<LABEL>:  <text>."""
    normalized_label = _normalize_label_honorifics(label.strip())
    body = _normalize_body_text(text)
    return f"\t\t\t{normalized_label}:  {body}"


def _emit_canonical_speaker_label_only(label: str) -> str:
    """Emit a canonical label-only speaker line: \\t\\t\\t<LABEL>:."""
    return f"\t\t\t{_normalize_label_honorifics(label.strip())}:"


def _emit_canonical_parenthetical(content: str) -> str:
    """Emit a canonical parenthetical line: \\t\\t\\t\\t(<content>)."""
    inner = content.strip()
    if not inner.endswith("."):
        inner += "."
    return f"\t\t\t\t({inner})"


def _postprocess_formatted_text(formatted_text: str) -> str:
    """
    Normalize AI-cleaned transcript text to the canonical UFM / Miah Bardot
    output contract.

    Canonical output:
      Q/A:           \\tQ.\\t{text}    /    \\tA.\\t{text}
      Speaker:       \\t\\t\\t{LABEL}:  {text}   (two spaces after colon)
      Parenthetical: \\t\\t\\t\\t({text}.)        (four leading tabs)
      Honorifics:    MR. / MS. / DR. (one space after period)

    The function accepts both canonical input (already conforming) and the
    legacy intermediate shape ("Q.\\t…", "LABEL:\\t…") and converts every
    output line to canonical regardless of input shape.
    """
    lines: list[str] = []
    for raw_line in (formatted_text or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            lines.append("")
            continue

        # ── Dunnell mis-attribution rescue ──
        # VIDEOGRAPHER block saying "Billy Dunnell here on behalf of..." is
        # relabeled to MR. DUNNELL with canonical 3-tab prefix and single
        # space inside the honorific label.
        dunnell_match = _DUNNELL_RE.match(line)
        if dunnell_match:
            lines.append(
                _emit_canonical_speaker("MR. DUNNELL", dunnell_match.group("text"))
            )
            continue

        # ── Strip leading tabs for prefix-based matching ──
        # Both canonical (3 leading tabs) and legacy (0 leading tabs) input
        # share the same content after the leading whitespace is stripped.
        stripped = line.lstrip("\t")

        # ── REPORTER label normalization ──
        # Variants: "COURT REPORTER:", "THE COURT REPORTER:", "THE REPORTER:"
        # all collapse to canonical "THE REPORTER:".
        matched_reporter = False
        for prefix in (
                "THE COURT REPORTER:",
                "COURT REPORTER:",
                "THE REPORTER:",
        ):
            if stripped.startswith(prefix):
                remainder = stripped[len(prefix):]
                body = remainder.lstrip(" \t")
                if not body:
                    lines.append(_emit_canonical_speaker_label_only("THE REPORTER"))
                else:
                    lines.append(_emit_canonical_speaker("THE REPORTER", body))
                matched_reporter = True
                break
        if matched_reporter:
            continue

        # ── VIDEOGRAPHER label normalization ──
        matched_videographer = False
        for prefix in (
                "THE VIDEOGRAPHER:",
                "VIDEOGRAPHER:",
        ):
            if stripped.startswith(prefix):
                remainder = stripped[len(prefix):]
                body = remainder.lstrip(" \t")
                if not body:
                    lines.append(
                        _emit_canonical_speaker_label_only("THE VIDEOGRAPHER")
                    )
                else:
                    lines.append(
                        _emit_canonical_speaker("THE VIDEOGRAPHER", body)
                    )
                matched_videographer = True
                break
        if matched_videographer:
            continue

        # ── Q/A lines ──
        if stripped.startswith("Q.\t"):
            lines.append(_emit_canonical_qa("Q", stripped[3:]))
            continue
        if stripped.startswith("A.\t"):
            lines.append(_emit_canonical_qa("A", stripped[3:]))
            continue

        # ── Parenthetical lines ──
        paren_match = _PAREN_LINE_RE.match(line)
        if paren_match:
            lines.append(
                _emit_canonical_parenthetical(paren_match.group("content"))
            )
            continue

        # ── Generic ALL-CAPS speaker label ──
        label_match = _LABEL_LINE_RE.match(line)
        if label_match:
            label = label_match.group("label")
            text = label_match.group("text")
            lines.append(_emit_canonical_speaker(label, text))
            continue

        # ── BY-line (flush left, no text after colon) ──
        # e.g. "BY MR. GARZA:" — preserve as-is per Part 10 of prompt.
        if stripped.startswith("BY ") and stripped.endswith(":"):
            lines.append(stripped)
            continue

        # ── EXAMINATION headers (ALL CAPS, no punctuation) ──
        if stripped in {"EXAMINATION", "FURTHER EXAMINATION"}:
            lines.append(stripped)
            continue

        # ── Fallback: body-text normalization only ──
        lines.append(_normalize_body_text(line))

    # Trim leading/trailing blank lines but preserve per-line leading tabs
    # (canonical Q/A and speaker lines start with \t / \t\t\t prefixes).
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


# ── API client helpers ────────────────────────────────────────────────────────

def _build_client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    if Anthropic is None:
        raise RuntimeError("anthropic package is not installed")
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Public API ────────────────────────────────────────────────────────────────

def format_transcript(
        raw_text: str,
        case_meta: dict[str, Any],
        *,
        client: Any | None = None,
        model: str | None = None,
        max_chunk_chars: int = CHUNK_CHAR_LIMIT,
        deepgram_words: list[dict[str, Any]] | None = None,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> str:
    """Backward-compatible wrapper — returns formatted text only."""
    formatted_text, _ = format_transcript_with_status(
        raw_text,
        case_meta,
        client=client,
        model=model,
        max_chunk_chars=max_chunk_chars,
        deepgram_words=deepgram_words,
        low_confidence_threshold=low_confidence_threshold,
    )
    return formatted_text


def format_transcript_with_status(
        raw_text: str,
        case_meta: dict[str, Any],
        *,
        client: Any | None = None,
        model: str | None = None,
        max_chunk_chars: int = CHUNK_CHAR_LIMIT,
        deepgram_words: list[dict[str, Any]] | None = None,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> tuple[str, dict[str, Any]]:
    """Format a raw Deepgram transcript into canonical Miah Bardot / UFM output.

    Pipeline:
      Step A  Inject ‹LC:word› markers for Deepgram tokens below the
              confidence threshold (requires deepgram_words).
      Step B  Split the marked text into ≤ CHUNK_CHAR_LIMIT chunks on
              speaker-block boundaries.
      Step C  Send each chunk to the AI with the system prompt and case
              metadata.  The AI normalises speaker labels, Q./A. format,
              and verbatim fidelity per prompt.py.
      Step D  Postprocess each AI response into canonical UFM output
              (\\tQ.\\t…, \\t\\t\\tLABEL:  …, \\t\\t\\t\\t(parenthetical.)),
              apply sentence double-spacing, dash normalisation, etc.
      Step E  Validate marker round-trip and utterance retention ratio.
      Step F  Join chunks and return.
    """
    marked_text = (
        inject_markers(raw_text, deepgram_words, threshold=low_confidence_threshold)
        if deepgram_words
        else raw_text
    )
    selected_model = model or AI_MODEL
    chunks = split_transcript(marked_text, max_chunk_chars=max_chunk_chars)
    status: dict[str, Any] = {
        "schema_version": "1.0",
        "model": selected_model,
        "success": True,
        "failure_reason": None,
        "input_utterance_count": 0,
        "output_utterance_count": 0,
        "utterance_retention_ratio": 0.0,
        "chunk_count": len(chunks),
        "chunks_truncated": [],
        "errors": [],
    }
    if not chunks:
        return "", status

    api_client = _build_client(client)
    rendered_chunks: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        response = api_client.messages.create(
            model=selected_model,
            max_tokens=MAX_TOKENS,
            system=CLEAN_FORMAT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_user_message(
                        chunk, case_meta, index, len(chunks)
                    ),
                }
            ],
        )
        response_text = _response_text(response)
        stop_reason = _response_stop_reason(response)

        if stop_reason == "max_tokens":
            logger.error(
                "Anthropic output truncated chunk_index=%s chunk_count=%s "
                "model=%s stop_reason=%s",
                index, len(chunks), selected_model, stop_reason,
            )
            raise OutputTruncatedError(index, len(chunks), selected_model)

        if deepgram_words:
            validate_marker_round_trip(chunk, response_text)

        rendered_chunks.append(_postprocess_formatted_text(response_text))

    final_text = (
        "\n\n".join(part for part in rendered_chunks if part.strip()).rstrip()
    )

    input_utterance_count = _count_input_utterances(marked_text)
    output_utterance_count = _count_output_utterances(final_text)

    if input_utterance_count > 0:
        ratio = output_utterance_count / input_utterance_count
        if ratio < MIN_UTTERANCE_RETENTION_DOCUMENT:
            raise ContentLossError(
                input_count=input_utterance_count,
                output_count=output_utterance_count,
                threshold=MIN_UTTERANCE_RETENTION_DOCUMENT,
            )

    status["input_utterance_count"] = input_utterance_count
    status["output_utterance_count"] = output_utterance_count
    status["utterance_retention_ratio"] = (
        output_utterance_count / input_utterance_count
        if input_utterance_count else 0.0
    )
    return final_text, status


# ── Case metadata helpers ─────────────────────────────────────────────────────

def _extract_city(attorney: dict[str, Any]) -> str:
    for key in ("city", "city_state_zip", "address"):
        value = _normalize_whitespace(str(attorney.get(key, "") or ""))
        if value:
            if "," in value:
                return value.split(",")[0].strip()
            return value
    return ""


def _attorneys_from_ufm(ufm_fields: dict[str, Any]) -> list[dict[str, str]]:
    attorneys: list[dict[str, str]] = []
    for role_key, role_name in (
            ("plaintiff_counsel", "plaintiff"),
            ("defense_counsel", "defendant"),
    ):
        for entry in ufm_fields.get(role_key, []) or []:
            name = _normalize_whitespace(str(entry.get("name", "") or ""))
            if not name:
                continue
            attorneys.append(
                {
                    "name": name,
                    "role": role_name,
                    "city": _extract_city(entry),
                }
            )
    return attorneys


def build_case_meta_from_ufm(ufm_fields: dict[str, Any]) -> dict[str, Any]:
    """Project existing job-config UFM data into the clean-format case metadata shape."""
    witness_name = _normalize_whitespace(
        str(ufm_fields.get("witness_name", "") or "")
    )
    witness_core, _, witness_credentials = witness_name.partition(",")
    defendant_name = _normalize_whitespace(
        str(ufm_fields.get("defendant_name", "") or "")
    )

    return {
        "cause_number": _normalize_whitespace(
            str(ufm_fields.get("cause_number", "") or "")
        ),
        "court": _normalize_whitespace(
            str(
                ufm_fields.get("court_caption")
                or ufm_fields.get("court_type")
                or ""
            )
        ),
        "county": _normalize_whitespace(str(ufm_fields.get("county", "") or "")),
        "judicial_district": _normalize_whitespace(
            str(ufm_fields.get("judicial_district", "") or "")
        ),
        "deposition_date": _normalize_whitespace(
            str(ufm_fields.get("depo_date", "") or "")
        ),
        "start_time": _normalize_whitespace(
            str(ufm_fields.get("depo_time_start", "") or "")
        ),
        "end_time": _normalize_whitespace(
            str(ufm_fields.get("depo_time_end", "") or "")
        ),
        "witness_name": witness_core or witness_name,
        "witness_credentials": witness_credentials.strip(),
        "plaintiff_name": _normalize_whitespace(
            str(ufm_fields.get("plaintiff_name", "") or "")
        ),
        "defendant_names": [defendant_name] if defendant_name else [],
        "reporter_name": _normalize_whitespace(
            str(ufm_fields.get("reporter_name", "") or "")
        ),
        "reporter_csr": _normalize_whitespace(
            str(
                ufm_fields.get("reporter_csr")
                or ufm_fields.get("csr_number")
                or ""
            )
        ),
        "attorneys": _attorneys_from_ufm(ufm_fields),
        "videographer_name": _normalize_whitespace(
            str(ufm_fields.get("videographer_name", "") or "")
        ),
        # Phase 2 placeholders.  Populated from job_config.json at the
        # _run_clean_format_job call site.  Defaults keep existing callers working.
        "confirmed_spellings": {},
        "deepgram_keyterms": [],
    }


def load_case_meta(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_deepgram_words_from_json(
        path: str | Path,
) -> list[dict[str, Any]] | None:
    """Load the Deepgram word array from a raw_deepgram.json file.

    Returns the ``words`` list when present and non-empty; ``None`` in every
    degraded case.  Never raises — callers pass the result directly to
    ``format_transcript(..., deepgram_words=...)`` and the yellow-highlight
    pipeline degrades gracefully to "no markers."

    Expected schema: dict with top-level ``"words"`` key holding a list of
    Deepgram word dicts, as written by ``core/job_runner.py`` to
    ``{case_dir}/Deepgram/raw_deepgram.json``.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    words = data.get("words")
    if not isinstance(words, list) or not words:
        return None
    return words
