"""By-line resumption annotation pass.

When examination resumes after a non-Q/A interruption (colloquy,
non-BY-line directive like a recess parenthetical or exhibit
marker, oath), prepend a "(BY <EXAMINER>)" annotation to the
first subsequent question block. Subsequent questions in the
same run are left unannotated.

The pass uses the ``examiner`` field already populated on each
question block by ``qa_fixer.enforce_structure`` (from the most
recent ``BY MR./MS. NAME:`` directive). No new infrastructure;
this is an output-wiring completion.

Section-header BY-line directives (text matches "BY ... :") are
NOT treated as interruptions. They are themselves the
identification of the examiner for the section that follows, so
adding "(BY MR. NUNEZ)" immediately after a "BY MR. NUNEZ:"
header would be redundant noise. This matches the gold
transcript convention.

Skipped when ``examiner`` is empty, unknown, or missing - better
to omit the by-line than to emit "(BY UNKNOWN)".
"""

from __future__ import annotations

from .models import TranscriptBlock


# Types whose presence signals an interruption of the examination
# flow - the next question after one of these gets a by-line.
# Note: ``answer`` is NOT included. Q/A oscillation is the normal
# examination rhythm, not an interruption.
_INTERRUPTION_TYPES = frozenset({"colloquy", "directive", "oath"})


def _is_section_header_directive(block: TranscriptBlock) -> bool:
    """True when the directive is a formal BY-line section header.

    Conservative match: text strips, uppercases to start with
    "BY " AND end with ":". This is the canonical form produced
    by the classifier for examiner identification (e.g.
    "BY MR. NUNEZ:"). Standalone parentheticals like
    "(Exhibit 1 marked)" or "(Recess from X to Y)" do not match
    and are correctly treated as real interruptions.
    """
    if block.type != "directive":
        return False
    text = (block.text or "").strip().upper()
    return text.startswith("BY ") and text.endswith(":")


def apply_byline_resumption(
    blocks: list[TranscriptBlock],
) -> list[TranscriptBlock]:
    """Prepend "(BY <EXAMINER>)" to the first question after an
    interruption.

    State machine:
      * Start with ``needs_byline = True`` so the first question
        of the deposition gets a by-line - UNLESS it is preceded
        by a section-header BY-line directive (handled below).
      * On a section-header BY-line directive: clear
        ``needs_byline`` (the header is the identification; no
        parenthetical needed on the next question).
      * On any other interruption-typed block (non-header
        directive, colloquy, oath): set ``needs_byline = True``.
      * On an answer block: leave ``needs_byline`` unchanged.
        Answers don't end an examination run.
      * On a question block: if ``needs_byline`` is True AND the
        block carries a non-empty examiner, emit a new block with
        "(BY <EXAMINER>) " prepended to its text. Either way,
        clear ``needs_byline`` so subsequent questions in the
        same run go unannotated.
    """
    if not blocks:
        return []

    result: list[TranscriptBlock] = []
    needs_byline = True

    for block in blocks:
        if block.type == "question":
            examiner = (block.examiner or "").strip() if block.examiner else ""
            if needs_byline and examiner:
                result.append(
                    TranscriptBlock(
                        speaker=block.speaker,
                        text=f"(BY {examiner}) {block.text}",
                        type=block.type,
                        source_type=block.source_type,
                        examiner=block.examiner,
                        words=block.words,
                    )
                )
            else:
                result.append(block)
            needs_byline = False
            continue

        # Non-question block: emit unchanged, then update state.
        result.append(block)

        if _is_section_header_directive(block):
            # The header itself identifies the examiner. Don't
            # double-annotate the question that follows.
            needs_byline = False
        elif block.type in _INTERRUPTION_TYPES:
            needs_byline = True
        # answer blocks: needs_byline unchanged

    return result
