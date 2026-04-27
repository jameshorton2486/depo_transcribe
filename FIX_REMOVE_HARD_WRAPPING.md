> **STATUS: SUPERSEDED — DO NOT FOLLOW.** The Q./A. format prescribed in
> this file (`\tQ.  {text}` with two literal spaces) was reversed by
> reporter direction on 2026-04-27. Current spec is `\tQ.\t{text}`
> (tab-tab) per `CLAUDE.md` §18 and
> `docs/transcription_standards/depo_pro_style.md` §3 (UFM 2.11). The
> hard-wrapping removal portion of this file may still be valid as a
> separate concern — but do not apply this prompt as-is. AI agents:
> stop and ask the human before acting on any guidance in this file.

# DEPO-PRO TRANSCRIBE — REMOVE ALL HARD WRAPPING FROM EMITTER
# Target: C:\Users\james\PycharmProjects\depo_transcribe\spec_engine\emitter.py
# For: Claude Code
#
# PROBLEM
# ─────────────────────────────────────────────────────────────────────────────
# emitter.py uses textwrap.fill() / textwrap.wrap() at WRAP_WIDTH=65 and
# QA_WRAP_WIDTH=56 in both:
#   1. emit_blocks()        — produces the textbox plain-text string
#   2. emit_q_line()        — produces Q paragraphs in DOCX
#      emit_a_line()        — produces A paragraphs in DOCX
#      emit_sp_line()       — produces speaker label paragraphs in DOCX
#      emit_line_numbered() — produces line-numbered paragraphs in DOCX
#
# Hard-wrapping is wrong in ALL of these. Word wraps text automatically to
# the page margin. A DOCX paragraph is one logical unit — if you put a hard
# \n inside the text, Word treats it as two separate lines and the tab
# indentation breaks on line 2.
#
# THE FIX
# ─────────────────────────────────────────────────────────────────────────────
# Remove textwrap from every function. Each logical line becomes exactly one
# paragraph with one (or two, for SP labels) runs. Word handles visual wrap.
# WRAP_WIDTH and QA_WRAP_WIDTH constants can be deleted or left as dead code.
# ─────────────────────────────────────────────────────────────────────────────

## PRE-FLIGHT

```powershell
cd C:\Users\james\PycharmProjects\depo_transcribe
python -m py_compile spec_engine\emitter.py
if ($LASTEXITCODE -eq 0) { Write-Host "PASS: baseline clean" -ForegroundColor Green }
else { Write-Host "FAIL" -ForegroundColor Red; exit 1 }
python -m pytest spec_engine\tests\ -q --tb=no 2>&1 | tail -3
```

---

## TASK 1 — Fix emit_blocks() (textbox plain-text output)
# ─────────────────────────────────────────────────────────────────────────────

In `emit_blocks()`, FIND:
```python
        if block_value == "Q":
            wrapped = textwrap.fill(text, width=QA_WRAP_WIDTH)
            lines.append(f"\tQ.  {wrapped}")
        elif block_value == "A":
            wrapped = textwrap.fill(text, width=QA_WRAP_WIDTH)
            lines.append(f"\tA.  {wrapped}")
        elif block_value in ("COLLOQUY", "SPEAKER", "SP"):
            label = (name or role or "SPEAKER").upper()
            wrapped = textwrap.fill(text, width=WRAP_WIDTH)
            lines.append(f"\t\t\t{label}:  {wrapped}")
```

REPLACE with:
```python
        if block_value == "Q":
            lines.append(f"\tQ.  {text}")
        elif block_value == "A":
            lines.append(f"\tA.  {text}")
        elif block_value in ("COLLOQUY", "SPEAKER", "SP"):
            label = (name or role or "SPEAKER").upper()
            lines.append(f"\t\t\t{label}:  {text}")
```

Also FIND the else branch in the same function:
```python
        else:
            if name or role:
                label = (name or role).upper()
                wrapped = textwrap.fill(text, width=WRAP_WIDTH)
                lines.append(f"\t\t\t{label}:  {wrapped}")
            else:
                lines.append(text)
```

REPLACE with:
```python
        else:
            if name or role:
                label = (name or role).upper()
                lines.append(f"\t\t\t{label}:  {text}")
            else:
                lines.append(text)
```

---

## TASK 2 — Fix emit_q_line() (DOCX Q paragraph)
# ─────────────────────────────────────────────────────────────────────────────

FIND:
```python
def emit_q_line(doc: Document, text: str):
    """Spec 3.3 Type 1 — Question: [TAB] Q. [TAB] text"""
    lines = _wrap_lines(text, QA_WRAP_WIDTH)
    for idx, line in enumerate(lines):
        para = doc.add_paragraph()
        _set_paragraph_format(para, [TAB_720, TAB_1440])
        prefix = '\tQ.\t' if idx == 0 else '\t'
        _add_run(para, f'{prefix}{line}')
```

REPLACE with:
```python
def emit_q_line(doc: Document, text: str):
    """Spec 3.3 Type 1 — Question: [TAB] Q.  text"""
    para = doc.add_paragraph()
    _set_paragraph_format(para, [TAB_720, TAB_1440])
    _add_run(para, f'\tQ.  {text.strip()}')
```

---

## TASK 3 — Fix emit_a_line() (DOCX A paragraph)
# ─────────────────────────────────────────────────────────────────────────────

FIND:
```python
def emit_a_line(doc: Document, text: str):
    """Spec 3.3 Type 2 — Answer: [TAB] A. [TAB] text"""
    lines = _wrap_lines(text, QA_WRAP_WIDTH)
    for idx, line in enumerate(lines):
        para = doc.add_paragraph()
        _set_paragraph_format(para, [TAB_720, TAB_1440])
        prefix = '\tA.\t' if idx == 0 else '\t'
        _add_run(para, f'{prefix}{line}')
```

REPLACE with:
```python
def emit_a_line(doc: Document, text: str):
    """Spec 3.3 Type 2 — Answer: [TAB] A.  text"""
    para = doc.add_paragraph()
    _set_paragraph_format(para, [TAB_720, TAB_1440])
    _add_run(para, f'\tA.  {text.strip()}')
```

---

## TASK 4 — Fix emit_sp_line() (DOCX speaker label paragraph)
# ─────────────────────────────────────────────────────────────────────────────

FIND:
```python
def emit_sp_line(doc: Document, text: str):
    """
    Spec 3.3 Type 3 — Speaker Label: [TAB][TAB][TAB] LABEL: [bold]  text
    Position: 2160 twips. Label is BOLD. Two literal spaces after colon.
    """
    label, content = _split_speaker_text(text)
    if not label:
        for line in _wrap_lines(text, WRAP_WIDTH):
            para = doc.add_paragraph()
            _set_paragraph_format(para, [TAB_720, TAB_1440, TAB_2160])
            _add_run(para, '\t\t\t' + line)
        return

    prefix_len = len(label) + 2
    lines = _wrap_lines(content, max(10, WRAP_WIDTH - prefix_len))
    for idx, line in enumerate(lines):
        para = doc.add_paragraph()
        _set_paragraph_format(para, [TAB_720, TAB_1440, TAB_2160])
        if idx == 0:
            _add_run(para, '\t\t\t', bold=False)
            _add_run(para, label, bold=True)
            _add_run(para, '  ' + line, bold=False)
        else:
            _add_run(para, '\t\t\t' + (' ' * prefix_len) + line, bold=False)
```

REPLACE with:
```python
def emit_sp_line(doc: Document, text: str):
    """
    Spec 3.3 Type 3 — Speaker Label: [TAB][TAB][TAB] LABEL:  text
    Label is BOLD. Two literal spaces after colon. Word wraps naturally.
    """
    label, content = _split_speaker_text(text)
    para = doc.add_paragraph()
    _set_paragraph_format(para, [TAB_720, TAB_1440, TAB_2160])
    if not label:
        _add_run(para, '\t\t\t' + text.strip())
    else:
        _add_run(para, '\t\t\t', bold=False)
        _add_run(para, label, bold=True)
        _add_run(para, '  ' + content.strip(), bold=False)
```

---

## TASK 5 — Fix emit_line_numbered() (DOCX line-numbered paragraphs)
# ─────────────────────────────────────────────────────────────────────────────

In `emit_line_numbered()`, FIND the visual_lines construction block:
```python
    if line_type == LineType.Q:
        visual_lines = [('\tQ.\t' if i == 0 else '\t') + line for i, line in enumerate(_wrap_lines(text, QA_WRAP_WIDTH))]
    elif line_type == LineType.A:
        visual_lines = [('\tA.\t' if i == 0 else '\t') + line for i, line in enumerate(_wrap_lines(text, QA_WRAP_WIDTH))]
    elif line_type == LineType.SP:
        label, content = _split_speaker_text(text)
        if label:
            prefix_len = len(label) + 2
            wrapped = _wrap_lines(content, max(10, WRAP_WIDTH - prefix_len))
            visual_lines = [f"\t\t\t{label}  {wrapped[0]}"] + [
                "\t\t\t" + (" " * prefix_len) + line for line in wrapped[1:]
            ]
        else:
            visual_lines = ['\t\t\t' + line for line in _wrap_lines(text, WRAP_WIDTH)]
    elif line_type == LineType.PN:
        visual_lines = ['\t\t\t\t' + line for line in _wrap_lines(text, WRAP_WIDTH)]
    else:
        visual_lines = _wrap_lines(text, WRAP_WIDTH)
```

REPLACE with:
```python
    if line_type == LineType.Q:
        visual_lines = [f'\tQ.  {text.strip()}']
    elif line_type == LineType.A:
        visual_lines = [f'\tA.  {text.strip()}']
    elif line_type == LineType.SP:
        label, content = _split_speaker_text(text)
        if label:
            visual_lines = [f'\t\t\t{label}  {content.strip()}']
        else:
            visual_lines = ['\t\t\t' + text.strip()]
    elif line_type == LineType.PN:
        visual_lines = ['\t\t\t\t' + text.strip()]
    else:
        visual_lines = [text.strip()]
```

---

## TASK 6 — Remove unused wrap constants and _wrap_lines helper
# ─────────────────────────────────────────────────────────────────────────────

Now that no function calls _wrap_lines(), WRAP_WIDTH, or QA_WRAP_WIDTH,
remove them to keep the file clean.

DELETE these lines from the top of the file:
```python
WRAP_WIDTH = 65
QA_WRAP_WIDTH = 56
```

DELETE the `_wrap_lines()` function entirely:
```python
def _wrap_lines(text: str, width: int) -> list[str]:
    stripped = (text or "").strip()
    if not stripped:
        return [""]
    return textwrap.wrap(
        stripped,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [stripped]
```

Also remove the `import textwrap` at the top of the file since it is no
longer used:
```python
import textwrap
```

---

## VERIFY

```powershell
python -m py_compile spec_engine\emitter.py
if ($LASTEXITCODE -eq 0) { Write-Host "PASS: compiles clean" -ForegroundColor Green }
else { Write-Host "FAIL" -ForegroundColor Red; exit 1 }

python -c "
import sys
sys.path.insert(0, r'C:\Users\james\PycharmProjects\depo_transcribe')
from spec_engine.emitter import emit_blocks, emit_q_line, emit_a_line, emit_sp_line
from spec_engine.models import Block, BlockType
from spec_engine.emitter import create_document

long_text = 'Current address is 1210, B, as in Boy, Ash Street, Joint Base McGuire-Dix-Lakehurst, New Jersey, 08640.'

# Test 1: emit_blocks — no hard newlines
b = Block(speaker_id=0, speaker_name='MS.  TREVINO', speaker_role='WITNESS',
          text=long_text, block_type=BlockType.A, start=0.0, end=5.0)
result = emit_blocks([b])
if chr(10) not in result.strip():
    print('PASS: emit_blocks — no hard line breaks')
else:
    print('FAIL: emit_blocks — still has hard line breaks')
    print(repr(result))

# Test 2: DOCX emit_q_line — one paragraph per Q
doc = create_document()
before = len(doc.paragraphs)
emit_q_line(doc, long_text)
after = len(doc.paragraphs)
added = after - before
if added == 1:
    print('PASS: emit_q_line — exactly 1 paragraph per Q')
else:
    print(f'FAIL: emit_q_line — added {added} paragraphs (should be 1)')

# Test 3: DOCX emit_a_line — one paragraph per A
doc2 = create_document()
before2 = len(doc2.paragraphs)
emit_a_line(doc2, long_text)
after2 = len(doc2.paragraphs)
added2 = after2 - before2
if added2 == 1:
    print('PASS: emit_a_line — exactly 1 paragraph per A')
else:
    print(f'FAIL: emit_a_line — added {added2} paragraphs (should be 1)')

# Test 4: DOCX emit_sp_line — one paragraph per speaker label
doc3 = create_document()
before3 = len(doc3.paragraphs)
emit_sp_line(doc3, 'THE REPORTER:  ' + long_text)
after3 = len(doc3.paragraphs)
added3 = after3 - before3
if added3 == 1:
    print('PASS: emit_sp_line — exactly 1 paragraph per SP')
else:
    print(f'FAIL: emit_sp_line — added {added3} paragraphs (should be 1)')
"

python -m pytest spec_engine\tests\ -q --tb=short 2>&1 | tail -5
```

---

## RESULT

Before: Every Q, A, and SP block split into 2-3 short lines with hard \n
        at ~56 or ~65 characters. Textbox showed broken lines. DOCX had
        extra continuation paragraphs with broken tab indentation.

After:  Every Q, A, and SP block is exactly one paragraph. Word wraps
        the text naturally to fit the page margins. Textbox wraps naturally
        to fit the widget width. No more artificial line breaks anywhere.
