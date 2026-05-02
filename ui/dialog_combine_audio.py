"""
ui/dialog_combine_audio.py

Modal dialog for selecting and ordering 2-N audio (or video-with-audio)
files that should be combined into a single transcript input.

Workflow:
    1. User clicks "Multiple Files..." on the Transcribe tab
    2. This dialog opens, user adds files via "+ Add File" picker
    3. User reorders / removes as needed
    4. Format check + total duration update live
    5. User clicks "Combine & Use" → ffmpeg runs in background thread
    6. On success: dialog closes, self.result_path holds the combined file
    7. On failure: dialog stays open with error message; buttons re-enable

Caller pattern:
    dialog = CombineAudioDialog(parent=self, case_audio_dir=audio_dir)
    self.wait_window(dialog)
    if dialog.result_path:
        ...use the combined audio path...

Layer note: dialog only orchestrates UI + threading. The actual file work
lives in `pipeline/audio_combiner.py`. Per Section 4 of CLAUDE.md, ui/
must not contain business logic — it dispatches to pipeline/.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app_logging import get_logger
from pipeline.audio_combiner import (
    combine_audio_files,
    formats_match,
    probe_audio_format,
)
from ui._components import (
    AUDIO_VIDEO_EXTENSIONS,
    BTN_PRIMARY_AMBER,
    BTN_PRIMARY_AMBER_HOVER,
    BTN_UTILITY_BLUE,
    BTN_UTILITY_BLUE_HOVER,
)

logger = get_logger(__name__)


# Deepgram caps a single transcription request at 4 hours of audio. Keep
# this constant in sync with config.CHUNK_DURATION_SECONDS expectations.
DEEPGRAM_MAX_DURATION_SECONDS = 4 * 3600

_OK_GREEN = "#44AA66"
_WARN_AMBER = "#CCAA44"
_ERR_RED = "#CC4444"
_MUTED = "#667788"


# ── State enum (string constants for cheap test asserts) ─────────────────────


class CombineState:
    EMPTY = "empty"  # 0 files
    TOO_FEW = "too_few"  # 1 file (passthrough is allowed but not the
    # workflow this dialog exists for; force the
    # user to add a second so they don't open
    # this dialog by mistake)
    TOO_LONG = "too_long"  # combined > 4h, Deepgram refuses
    READY_LOSSLESS = "ready_lossless"
    READY_REENCODE = "ready_reencode"


def _format_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym', 'Ym Zs', or 'Zs' depending on magnitude."""
    seconds = max(0.0, float(seconds))
    if seconds >= 3600:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"
    if seconds >= 60:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s"
    return f"{int(seconds)}s"


class CombineAudioDialog(ctk.CTkToplevel):
    """Modal multi-file selection + combine dialog."""

    def __init__(self, parent, case_audio_dir: Path | None = None):
        super().__init__(parent)

        self._parent = parent
        self._case_audio_dir = Path(case_audio_dir) if case_audio_dir else None

        # Public — caller reads after wait_window returns.
        self.result_path: Path | None = None

        # Internal state.
        # Each entry: {"path": Path, "format": dict}
        # format is the full probe_audio_format() result (codec_name,
        # sample_rate, channels, duration, ...).
        self._files: list[dict] = []
        self._combining: bool = False

        self.title("Combine Multiple Audio Files")
        self.geometry("680x520")
        self.resizable(True, True)
        self.minsize(600, 480)

        # Modal: stay on top of parent + grab focus so the rest of the app
        # is inert until the user finishes here.
        try:
            self.transient(parent)
        except Exception:
            # transient() can fail if parent is in an unusual state
            # (already-destroyed test root, etc.) — not fatal for the
            # dialog's behavior, just less polished.
            pass
        self.grab_set()

        self._build_ui()
        self._refresh()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=12, pady=10)

        # Heading
        ctk.CTkLabel(
            outer,
            text="Files will be combined in the order shown below "
            "(chronological session order):",
            font=ctk.CTkFont(size=12),
            text_color="#AABBCC",
            justify="left",
            wraplength=620,
        ).pack(anchor="w", pady=(0, 6))

        # Scrollable file list
        self._list_frame = ctk.CTkScrollableFrame(
            outer,
            fg_color="#1A1A2A",
            border_width=1,
            border_color="#252535",
            height=220,
        )
        self._list_frame.pack(fill="both", expand=True, pady=(0, 8))

        # Add file / total duration row
        actions = ctk.CTkFrame(outer, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 6))

        self._add_btn = ctk.CTkButton(
            actions,
            text="+ Add File",
            width=120,
            fg_color=BTN_UTILITY_BLUE,
            hover_color=BTN_UTILITY_BLUE_HOVER,
            command=self._on_add_file,
        )
        self._add_btn.pack(side="left")

        self._duration_label = ctk.CTkLabel(
            actions,
            text="Total duration: 0s",
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
        )
        self._duration_label.pack(side="right")

        # Format check + status messages
        self._status_label = ctk.CTkLabel(
            outer,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=_MUTED,
            anchor="w",
            justify="left",
            wraplength=620,
        )
        self._status_label.pack(anchor="w", pady=(0, 8))

        # Footer buttons
        footer = ctk.CTkFrame(outer, fg_color="transparent")
        footer.pack(fill="x")

        self._cancel_btn = ctk.CTkButton(
            footer,
            text="Cancel",
            width=110,
            fg_color="transparent",
            border_width=1,
            border_color="#445",
            text_color="#AABBCC",
            command=self._on_cancel,
        )
        self._cancel_btn.pack(side="left")

        self._combine_btn = ctk.CTkButton(
            footer,
            text="Combine & Use",
            width=160,
            fg_color=BTN_PRIMARY_AMBER,
            hover_color=BTN_PRIMARY_AMBER_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            command=self._on_combine,
        )
        self._combine_btn.pack(side="right")

    # ── Public API ───────────────────────────────────────────────────────

    def add_file(self, path: Path) -> None:
        """Probe + add a file. Raises if the file isn't probeable."""
        path = Path(path)
        fmt = probe_audio_format(path)
        self._add_file_with_format(path, fmt)

    def _add_file_with_format(self, path: Path, fmt: dict) -> None:
        """Test seam — bypasses probe so unit tests can supply synthetic
        format dicts without needing ffmpeg + real audio fixtures.
        Production code goes through add_file()."""
        self._files.append({"path": Path(path), "format": dict(fmt)})
        self._refresh()

    def remove_file(self, idx: int) -> None:
        if 0 <= idx < len(self._files):
            self._files.pop(idx)
            self._refresh()

    def move_up(self, idx: int) -> None:
        if 1 <= idx < len(self._files):
            self._files[idx - 1], self._files[idx] = (
                self._files[idx],
                self._files[idx - 1],
            )
            self._refresh()

    def move_down(self, idx: int) -> None:
        if 0 <= idx < len(self._files) - 1:
            self._files[idx], self._files[idx + 1] = (
                self._files[idx + 1],
                self._files[idx],
            )
            self._refresh()

    # ── State computation (testable, widget-free) ────────────────────────

    def _check_state(self) -> str:
        n = len(self._files)
        if n == 0:
            return CombineState.EMPTY
        if n == 1:
            return CombineState.TOO_FEW
        total = sum(
            float(item["format"].get("duration", 0.0) or 0.0) for item in self._files
        )
        if total > DEEPGRAM_MAX_DURATION_SECONDS:
            return CombineState.TOO_LONG
        formats = [item["format"] for item in self._files]
        if formats_match(formats):
            return CombineState.READY_LOSSLESS
        return CombineState.READY_REENCODE

    def _total_duration(self) -> float:
        return sum(
            float(item["format"].get("duration", 0.0) or 0.0) for item in self._files
        )

    # ── Refresh (rebuild list rows + recompute status) ───────────────────

    def _refresh(self) -> None:
        # Tear down existing rows. Recreating from scratch is simpler than
        # selectively patching widget state and runs cheaply at this list
        # size (max ~6-10 rows in practice).
        for child in list(self._list_frame.winfo_children()):
            child.destroy()

        if not self._files:
            ctk.CTkLabel(
                self._list_frame,
                text='No files added yet — click "+ Add File" to begin.',
                font=ctk.CTkFont(size=11),
                text_color=_MUTED,
            ).pack(padx=10, pady=20)

        for idx, item in enumerate(self._files):
            self._build_row(idx, item)

        # Total duration + status update
        total = self._total_duration()
        self._duration_label.configure(
            text=f"Total duration: {_format_duration(total)}",
        )
        self._update_status_message()

    def _build_row(self, idx: int, item: dict) -> None:
        row = ctk.CTkFrame(self._list_frame, fg_color="#222232")
        row.pack(fill="x", padx=4, pady=2)

        # Index
        ctk.CTkLabel(
            row,
            text=f"{idx + 1}.",
            width=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#AABBCC",
        ).pack(side="left", padx=(8, 4), pady=4)

        # Basename + format hint
        path: Path = item["path"]
        fmt: dict = item["format"]
        codec = fmt.get("codec_name") or "?"
        sr = fmt.get("sample_rate") or 0
        ch = fmt.get("channels") or 0
        dur = float(fmt.get("duration") or 0.0)
        meta = f"{codec} {sr}Hz {ch}ch · {_format_duration(dur)}"

        text_box = ctk.CTkFrame(row, fg_color="transparent")
        text_box.pack(side="left", fill="x", expand=True, padx=(2, 4))
        ctk.CTkLabel(
            text_box,
            text=path.name,
            font=ctk.CTkFont(size=11),
            text_color="#DDE2E8",
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_box,
            text=meta,
            font=ctk.CTkFont(size=9),
            text_color=_MUTED,
            anchor="w",
        ).pack(anchor="w")

        # ↑ / ↓ / Remove buttons. ASCII fallback chars to dodge cp1252
        # console issues — the dialog itself renders unicode fine, but
        # consistency is cheap.
        n = len(self._files)
        up_state = "normal" if idx > 0 else "disabled"
        down_state = "normal" if idx < n - 1 else "disabled"

        ctk.CTkButton(
            row,
            text="^",
            width=28,
            height=24,
            fg_color="transparent",
            border_width=1,
            border_color="#445",
            text_color="#AABBCC",
            state=up_state,
            command=lambda i=idx: self.move_up(i),
        ).pack(side="left", padx=2, pady=4)

        ctk.CTkButton(
            row,
            text="v",
            width=28,
            height=24,
            fg_color="transparent",
            border_width=1,
            border_color="#445",
            text_color="#AABBCC",
            state=down_state,
            command=lambda i=idx: self.move_down(i),
        ).pack(side="left", padx=2, pady=4)

        ctk.CTkButton(
            row,
            text="Remove",
            width=72,
            height=24,
            fg_color="transparent",
            border_width=1,
            border_color="#553",
            text_color="#CCAAAA",
            command=lambda i=idx: self.remove_file(i),
        ).pack(side="left", padx=(2, 8), pady=4)

    def _update_status_message(self) -> None:
        state = self._check_state()
        text, color = "", _MUTED
        combine_enabled = False

        if state == CombineState.EMPTY:
            text = ""
            color = _MUTED
        elif state == CombineState.TOO_FEW:
            text = "Add at least one more file to combine."
            color = _MUTED
        elif state == CombineState.TOO_LONG:
            total_h = self._total_duration() / 3600.0
            text = (
                f"X Combined duration is {total_h:.2f}h — exceeds the "
                f"4-hour limit Deepgram accepts in a single call. "
                f"Use fewer files or shorter sessions."
            )
            color = _ERR_RED
        elif state == CombineState.READY_LOSSLESS:
            first_fmt = self._files[0]["format"]
            codec = first_fmt.get("codec_name") or "?"
            sr = first_fmt.get("sample_rate") or 0
            ch_label = (
                "stereo"
                if first_fmt.get("channels") == 2
                else (
                    "mono"
                    if first_fmt.get("channels") == 1
                    else f"{first_fmt.get('channels')}ch"
                )
            )
            text = (
                f"OK All files match ({codec.upper()}, {sr}Hz, {ch_label}). "
                f"Combination will be lossless."
            )
            color = _OK_GREEN
            combine_enabled = True
        elif state == CombineState.READY_REENCODE:
            text = (
                "! Files have different formats. Will re-encode to WAV "
                "at 24kHz mono (no audible quality loss but slightly slower)."
            )
            color = _WARN_AMBER
            combine_enabled = True

        self._status_label.configure(text=text, text_color=color)
        self._combine_btn.configure(
            state=("normal" if combine_enabled and not self._combining else "disabled")
        )

    # ── Button handlers ──────────────────────────────────────────────────

    def _on_add_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Select audio file",
            filetypes=AUDIO_VIDEO_EXTENSIONS,
        )
        if not path:
            return
        try:
            self.add_file(Path(path))
        except Exception as exc:
            logger.error("[CombineDialog] Probe failed for %s: %s", path, exc)
            messagebox.showerror(
                "Cannot read audio file",
                f"Failed to probe {Path(path).name}: {exc}",
                parent=self,
            )

    def _on_cancel(self) -> None:
        if self._combining:
            # Don't allow cancel mid-combine — ffmpeg subprocess is running
            # in a background thread and we'd leak a partial output file.
            return
        self.result_path = None
        self.destroy()

    def _on_combine(self) -> None:
        if self._combining:
            return
        state = self._check_state()
        if state not in (CombineState.READY_LOSSLESS, CombineState.READY_REENCODE):
            return
        if not self._case_audio_dir:
            messagebox.showerror(
                "Output location not set",
                "The dialog wasn't given a case audio directory to write "
                "the combined file into. Open this from the Transcribe tab "
                "after filling in case info.",
                parent=self,
            )
            return

        # Output naming: {case_audio_dir}/_combined/{first_stem}_combined{ext}
        first = self._files[0]["path"]
        target_dir = self._case_audio_dir / "_combined"
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / f"{first.stem}_combined{first.suffix}"

        self._combining = True
        self._combine_btn.configure(state="disabled", text="Combining...")
        self._cancel_btn.configure(state="disabled")
        self._add_btn.configure(state="disabled")
        self._status_label.configure(
            text="Running ffmpeg... this may take a few minutes for long files.",
            text_color=_MUTED,
        )

        ordered_paths = [item["path"] for item in self._files]
        thread = threading.Thread(
            target=self._run_combine_job,
            args=(ordered_paths, output_path),
            daemon=True,
        )
        thread.start()

    def _run_combine_job(self, ordered_paths: list[Path], output_path: Path) -> None:
        try:
            result = combine_audio_files(ordered_paths, output_path)
        except Exception as exc:
            logger.exception("[CombineDialog] combine_audio_files raised: %s", exc)
            self.after(0, self._on_combine_done, None, str(exc))
            return
        self.after(0, self._on_combine_done, result, None)

    def _on_combine_done(self, result, error: str | None) -> None:
        self._combining = False

        if error or (result and not result.success):
            err_msg = error or (result.error if result else "unknown error")
            self._combine_btn.configure(state="normal", text="Combine & Use")
            self._cancel_btn.configure(state="normal")
            self._add_btn.configure(state="normal")
            self._status_label.configure(
                text=f"X Combine failed: {err_msg[:200]}",
                text_color=_ERR_RED,
            )
            return

        # Success
        self.result_path = result.output_path
        logger.info(
            "[CombineDialog] Combined %d files via %s (lossless=%s) -> %s",
            len(self._files),
            result.method,
            result.lossless,
            result.output_path,
        )
        self.destroy()
