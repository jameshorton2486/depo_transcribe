"""
Depo-Pro Transcribe — launcher
Run: python app.py
.\.venv\Scripts\python.exe app.p

"""

import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

for _d in ("temp", "output", "logs", "work_files/transcripts"):
    os.makedirs(os.path.join(_HERE, _d), exist_ok=True)

from ui.app_window import DepoTranscribeApp

if __name__ == "__main__":
    app = DepoTranscribeApp()
    app.mainloop()
