r"""
Depo-Pro Transcribe — launcher
Run: python app.py
cd C:\Users\james\PycharmProjects\depo_transcribe
.\.venv\Scripts\python.exe app.py


"""

import os
import sys


_HERE = os.path.dirname(os.path.abspath(__file__))
_RUNTIME_DIRS = ("temp", "output", "logs", "work_files/transcripts")


def _bootstrap_paths() -> None:
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)


def _ensure_runtime_dirs() -> None:
    for relative_dir in _RUNTIME_DIRS:
        os.makedirs(os.path.join(_HERE, relative_dir), exist_ok=True)


def main() -> None:
    _bootstrap_paths()
    _ensure_runtime_dirs()

    from ui.app_window import DepoTranscribeApp

    app = DepoTranscribeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
