"""
core/vlc_player.py

Thin VLC wrapper for Windows with graceful fallback when python-vlc
or the local VLC runtime is unavailable.
"""

from __future__ import annotations

import os
from typing import Any

_VLC_DIR = r"C:\Program Files\VideoLAN\VLC"
_VLC_DLL = os.path.join(_VLC_DIR, "libvlc.dll")
_VLC_READY = False


def _ensure_vlc_path() -> bool:
    global _VLC_READY
    if _VLC_READY:
        return True
    if not os.path.isfile(_VLC_DLL):
        return False
    try:
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(_VLC_DIR)
        _VLC_READY = True
        return True
    except OSError:
        return False


try:
    if _ensure_vlc_path():
        import vlc as _vlc  # type: ignore
    else:
        _vlc = None
except Exception:
    _vlc = None


class VLCPlayer:
    """Small adapter that keeps the UI code free of python-vlc details."""

    def __init__(self) -> None:
        self._instance: Any | None = None
        self._player: Any | None = None
        self._media_path: str | None = None

        if _vlc is None:
            return

        try:
            self._instance = _vlc.Instance()
            self._player = self._instance.media_player_new()
        except Exception:
            self._instance = None
            self._player = None

    @property
    def is_available(self) -> bool:
        return self._player is not None

    @property
    def is_loaded(self) -> bool:
        return self.is_available and bool(self._media_path)

    @property
    def is_playing(self) -> bool:
        if not self.is_available:
            return False
        try:
            return bool(self._player.is_playing())
        except Exception:
            return False

    @property
    def duration_seconds(self) -> float:
        if not self.is_available:
            return 0.0
        try:
            value = self._player.get_length()
            return max(0.0, float(value) / 1000.0)
        except Exception:
            return 0.0

    @property
    def position_seconds(self) -> float:
        if not self.is_available:
            return 0.0
        try:
            value = self._player.get_time()
            return max(0.0, float(value) / 1000.0)
        except Exception:
            return 0.0

    def load(self, media_path: str) -> bool:
        if not self.is_available or not media_path or not os.path.isfile(media_path):
            return False
        try:
            media = self._instance.media_new(media_path)
            self._player.set_media(media)
            self._media_path = media_path
            return True
        except Exception:
            self._media_path = None
            return False

    def play(self) -> bool:
        if not self.is_loaded:
            return False
        try:
            self._player.play()
            return True
        except Exception:
            return False

    def pause(self) -> bool:
        if not self.is_loaded:
            return False
        try:
            self._player.pause()
            return True
        except Exception:
            return False

    def stop(self) -> bool:
        if not self.is_loaded:
            return False
        try:
            self._player.stop()
            return True
        except Exception:
            return False

    def jump_to(self, seconds: float) -> bool:
        if not self.is_loaded:
            return False
        try:
            self._player.set_time(int(max(0.0, seconds) * 1000))
            self._player.play()
            return True
        except Exception:
            return False

    def set_volume(self, volume: int) -> bool:
        if not self.is_available:
            return False
        try:
            self._player.audio_set_volume(max(0, min(100, int(volume))))
            return True
        except Exception:
            return False

    def release(self) -> None:
        try:
            if self._player is not None:
                self._player.stop()
                self._player.release()
        except Exception:
            pass
        try:
            if self._instance is not None:
                self._instance.release()
        except Exception:
            pass
        self._player = None
        self._instance = None
        self._media_path = None
