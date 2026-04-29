# Depo-Pro Transcribe

Depo-Pro Transcribe is a desktop app that converts deposition audio/video into a clean reading-copy transcript: media is preprocessed, transcribed by Deepgram, cleaned by a single Claude pass in `clean_format`, and exported to a Word `.docx`.

## Install / Run
Create a virtual environment, install dependencies, set `DEEPGRAM_API_KEY` and `ANTHROPIC_API_KEY` in `.env`, then run:

```bash
pip install -r requirements.txt
python app.py
```

## Test
Run the test suite with:

```bash
pytest
```
