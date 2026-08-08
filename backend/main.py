import base64
import json
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

# Make the existing AI layer (intelligence.py, sarvam_client.py, dataset_loader.py
# in the project root) importable regardless of where uvicorn is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import intelligence
import sarvam_client as sc

app = FastAPI(title="SEVA AI backend")

# Wide open for local hackathon dev — tighten before shipping anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIO_TMP_DIR = Path(__file__).resolve().parent.parent / "audio_output"

# Neutral English source string for the one-time greeting, translated into
# whatever language the user picks on the language-selection screen. Kept
# here (not in intelligence.py) since it's UI chrome, not part of the AI
# conversation/history — it's never sent through intelligence.respond().
GREETING_EN = (
    "Namaste! I'm SEVA, your assistant for driving license and RTO services. "
    "How can I help you today?"
)


class ChatTurn(BaseModel):
    role: str
    content: str


class TextChatRequest(BaseModel):
    message: str
    history: List[ChatTurn] = []
    language: Optional[str] = None  # BCP-47 code, e.g. "hi-IN"; auto-detected if omitted


class GreetRequest(BaseModel):
    language: str  # BCP-47 code chosen on the language-selection screen


def _run_turn(history: List[Dict[str, str]], english_message: str, lang: str) -> dict:
    # service_id is left unset here so the hybrid RAG pipeline auto-detects
    # which of the 3 RTO services this message is about (Phase 1
    # service-aware retrieval) instead of every request being pinned to
    # driving_license.
    reply_en, citations = intelligence.respond(history, english_message)
    localized = sc.translate_text(reply_en, target_language_code=lang) if lang != "en-IN" else reply_en

    audio_path = Path(sc.tts(localized, language=lang))
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
    audio_path.unlink(missing_ok=True)

    return {
        "reply_text": localized,
        "audio_base64": audio_b64,
        "language": lang,
        "citations": citations,
        "history": history,  # intelligence.respond() appended to this in place
    }


@app.post("/api/chat/text")
def chat_text(req: TextChatRequest):
    lang = req.language or sc.detect_language(req.message)
    english_message = (
        sc.translate_text(req.message, source_language_code=lang, target_language_code="en-IN")
        if lang != "en-IN"
        else req.message
    )
    history = [turn.model_dump() for turn in req.history]
    result = _run_turn(history, english_message, lang)
    result["user_text"] = req.message
    return result


@app.post("/api/chat/voice")
async def chat_voice(audio: UploadFile = File(...), history: str = Form("[]")):
    hist = json.loads(history)

    ext = (audio.filename or "input.webm").rsplit(".", 1)[-1].lower()
    tmp_path = AUDIO_TMP_DIR / f"webinput_{uuid.uuid4()}.{ext}"
    tmp_path.parent.mkdir(exist_ok=True)
    tmp_path.write_bytes(await audio.read())

    native_text, lang = sc.stt_transcribe(str(tmp_path))
    tmp_path.unlink(missing_ok=True)

    english_message = sc.translate_text(native_text, source_language_code=lang, target_language_code="en-IN")
    result = _run_turn(hist, english_message, lang)
    result["user_text"] = native_text
    return result


@app.post("/api/greet")
def greet(req: GreetRequest):
    lang = req.language
    localized = sc.translate_text(GREETING_EN, target_language_code=lang) if lang != "en-IN" else GREETING_EN

    audio_path = Path(sc.tts(localized, language=lang))
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
    audio_path.unlink(missing_ok=True)

    return {"reply_text": localized, "audio_base64": audio_b64, "language": lang}


@app.get("/api/health")
def health():
    return {"ok": True, "sarvam_key_set": sc.SARVAM_API_KEY is not None}
