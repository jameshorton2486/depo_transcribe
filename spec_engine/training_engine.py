"""
spec_engine/training_engine.py

AI-powered rule generation for the Training Engine.
"""

from __future__ import annotations

import json

from config import ANTHROPIC_API_KEY


RULE_GENERATION_SYSTEM_PROMPT = """You are an expert legal transcript
correction engine trained on the Texas Uniform Format Manual (UFM) and
Morson's English Guide for Court Reporters.

Analyze the provided transcript correction example and generate precise,
reusable correction rules for a transcript processing system.

ABSOLUTE CONSTRAINTS — these override everything else:
- NEVER generate rules that alter: uh, um, ah, uh-huh, uh-uh, yeah, yep,
  yup, nope, nah, mm-hmm, gonna, wanna. These are verbatim-protected legal
  record. Any rule touching these words is invalid and must not be output.
- NEVER generate rules targeting objection text. If the incorrect text
  starts with "Objection", skip it entirely.
- NEVER generate rules where "correct" is an empty string (no word deletions).
- Prefer specific multi-word corrections over broad single-word replacements.
- Rules must be deterministic and safe to apply to any transcript text.

CORRECTION TYPES:
  spelling_normalization, punctuation_correction, capitalization,
  legal_terminology, multi_word_phrase

For each rule: explain it briefly in "description".
Flag ambiguous cases in the "flags" array (do not generate low-confidence rules).

OUTPUT: Return ONLY valid JSON. No markdown, no preamble, no explanation.

{
  "rules": [
    {
      "type": "exact_replace",
      "incorrect": "subpoena deuces tikum",
      "correct": "subpoena duces tecum",
      "description": "Latin legal term: subpoena duces tecum",
      "priority": 10
    },
    {
      "type": "regex_replace",
      "pattern": "\\bokay\\b",
      "replacement": "Okay",
      "description": "Capitalize okay per Morson's English Guide",
      "priority": 20
    }
  ],
  "flags": [
    "Could not determine intent of change at line 3 — recommend manual review"
  ]
}
"""


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def generate_rules(
    incorrect_text: str,
    correct_text: str,
    rule_instruction: str = "",
    progress_callback: callable = None,
) -> dict:
    if not any(value.strip() for value in (incorrect_text, correct_text, rule_instruction)):
        return {"error": "No input provided.", "rules": [], "flags": [], "raw_json": ""}

    if not ANTHROPIC_API_KEY.strip():
        return {
            "error": "ANTHROPIC_API_KEY not set in .env",
            "rules": [],
            "flags": [],
            "raw_json": "",
        }

    user_message = (
        "INCORRECT TEXT:\n"
        f"{incorrect_text or '(none — use rule instruction only)'}\n\n"
        "CORRECTED TEXT:\n"
        f"{correct_text or '(none — use rule instruction only)'}\n\n"
        "RULE INSTRUCTION:\n"
        f"{rule_instruction or '(none provided)'}"
    )

    if progress_callback:
        progress_callback("Calling Claude API…")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=RULE_GENERATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        raw_json = _strip_markdown_fences(raw)
        parsed = json.loads(raw_json)
        rules = parsed.get("rules", []) if isinstance(parsed, dict) else []
        flags = parsed.get("flags", []) if isinstance(parsed, dict) else []
        return {
            "rules": rules if isinstance(rules, list) else [],
            "flags": flags if isinstance(flags, list) else [],
            "raw_json": raw_json,
            "error": None,
        }
    except json.JSONDecodeError as exc:
        return {"rules": [], "flags": [], "raw_json": raw_json, "error": str(exc)}
    except Exception as exc:
        return {"rules": [], "flags": [], "raw_json": "", "error": str(exc)}


def preview_rules_as_text(rules: list[dict], flags: list[str] | None = None) -> str:
    flags = flags or []
    lines = [f"── {len(rules)} rule{'s' if len(rules) != 1 else ''} proposed ──────────────────────────", ""]

    for idx, rule in enumerate(rules, start=1):
        lines.append(
            f"Rule {idx}  [{rule.get('type', '?')}]  priority={rule.get('priority', '?')}"
        )
        if rule.get("type") == "exact_replace":
            lines.append(f'  incorrect : "{rule.get("incorrect", "")}"')
            lines.append(f'  correct   : "{rule.get("correct", "")}"')
        else:
            lines.append(f'  pattern     : {rule.get("pattern", "")}')
            lines.append(f'  replacement : {rule.get("replacement", "")}')
        if rule.get("description"):
            lines.append(f'  note      : {rule.get("description", "")}')
        lines.append("")

    if flags:
        lines.append(
            f"── {len(flags)} flag{'s' if len(flags) != 1 else ''} ────────────────────────────────────"
        )
        for flag in flags:
            lines.append(f"⚠  {flag}")

    return "\n".join(lines).rstrip()
