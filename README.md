# Depo-Pro Transcribe

Depo-Pro Transcribe is a Windows desktop app for turning deposition audio into a clean reading-copy Word document. The active path is `pipeline/` for audio + Deepgram transcription and `clean_format/` for Anthropic cleanup plus Texas-style DOCX generation.

Install dependencies with `pip install -r requirements.txt`, set `DEEPGRAM_API_KEY` and `ANTHROPIC_API_KEY` in `.env`, and run the app with `python app.py`.

Run tests with `pytest`. If you are making code changes with an AI assistant, read [CLAUDE.md](./CLAUDE.md) first.
