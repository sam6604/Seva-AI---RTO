# SEVA AI — Voice + RTO Intelligence Module

Voice-first RTO help-desk assistant. Speak in any Indian language, SEVA
detects the language and replies in text + voice in the same language.

## Architecture

- `sarvam_client.py` — Sarvam SDK wrappers: `stt_transcribe` (native-script
  transcription + language auto-detect), `translate_text`, `tts`.
- `dataset_loader.py` — `load_dataset()` (the DL flow's structured data) and
  `get_relevant_context()` (RAG retrieval over everything in `data/`).
- `intelligence.py` — one function, `respond(history, user_message)`. A
  single system prompt tells the model how to behave (guide the DL flow
  step-by-step using the verified reference data; answer other RTO topics
  from general knowledge with a caveat; refuse anything unrelated). The
  model tracks conversation progress itself via `history` — there's no
  hand-coded state machine, keyword classifier, or step tracker.
- `app.py` — Streamlit UI: mic input, chat log, TTS playback, source
  citations.

## Where to put the RAG dataset

Drop JSON files into **`data/`** — every file there is automatically
flattened into text chunks and indexed for retrieval (see
`dataset_loader._flatten_to_chunks`), so any reasonable JSON shape works,
no code changes needed.

- `data/dl_dataset.json` — the driving-license flow's structured data
  (prereq questions, steps, docs needed). This is the one flow treated as
  fully verified. `load_dataset()` reads this file specifically — replace
  its contents with your teammate's real data, keeping the same schema
  (see the file for the shape), or repoint `load_dataset()` in
  `dataset_loader.py` if the real data module works differently.
- `data/faq.json` (or any other `.json` file you add here) — general
  RTO/DL knowledge, `[{"q": "...", "a": "..."}]` or any other shape. Used
  purely for RAG grounding on any RTO topic, not just DL.

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your Sarvam key:
   ```bash
   cp .env.example .env
   ```
   ```
   SARVAM_API_KEY=your_actual_key_here
   ```
   Loads automatically via `python-dotenv`. `.env` is git-ignored.

No OpenAI/Anthropic key needed — voice (STT/TTS/translate) and the LLM both
run through the single Sarvam key.

## Running

```bash
streamlit run app.py
```
Opens at `http://localhost:8501`. Click "Tap to record your answer", speak,
SEVA responds in text + voice. Click "Start over" to reset.

To sanity-check the Sarvam client in isolation (no Streamlit):
```bash
python sarvam_client.py
```
