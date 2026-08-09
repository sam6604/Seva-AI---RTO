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
from dataset_loader import load_dataset
from retrieval import KNOWN_SERVICES, get_official_links

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

    # Phase 3: translate/TTS failures (network issues, API errors, an
    # unsupported language code) must not crash the whole request — the
    # text reply is still useful on its own, so degrade to text-only
    # instead of raising a 500. `error` is None on the happy path; the
    # frontend only needs to show something if it's set.
    error = None

    try:
        localized = sc.translate_text(reply_en, target_language_code=lang) if lang != "en-IN" else reply_en
    except Exception as e:
        localized = reply_en
        error = f"Translation to {lang} failed, showing English text instead."

    audio_b64 = ""
    try:
        audio_path = Path(sc.tts(localized, language=lang))
        audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
        audio_path.unlink(missing_ok=True)
    except Exception as e:
        # Voice failing should never block text — TEST requirement: "if
        # voice fails, text should still work."
        error = error or "Voice reply is unavailable right now; text reply still works."

    return {
        "reply_text": localized,
        "audio_base64": audio_b64,
        "language": lang,
        "citations": citations,
        "history": history,  # intelligence.respond() appended to this in place
        "error": error,
    }


def _error_result(history: List[Dict[str, str]], lang: str, message: str) -> dict:
    """Uniform shape for a handled failure — same keys the frontend already
    expects from a normal turn, so no special-case handling is needed there,
    it just shows `error` if present instead of crashing on a malformed
    response."""
    return {
        "reply_text": message,
        "audio_base64": "",
        "language": lang or "en-IN",
        "citations": [],
        "history": history,
        "error": message,
    }


@app.post("/api/chat/text")
def chat_text(req: TextChatRequest):
    history = [turn.model_dump() for turn in req.history]
    if not req.message or not req.message.strip():
        return _error_result(history, req.language, "Please type a question.")

    try:
        lang = req.language or sc.detect_language(req.message)
        english_message = (
            sc.translate_text(req.message, source_language_code=lang, target_language_code="en-IN")
            if lang != "en-IN"
            else req.message
        )
    except Exception:
        return _error_result(history, req.language, "Couldn't process that message right now — please try again.")

    result = _run_turn(history, english_message, lang)
    result["user_text"] = req.message
    return result


@app.post("/api/chat/voice")
async def chat_voice(audio: UploadFile = File(...), history: str = Form("[]")):
    try:
        hist = json.loads(history)
    except (json.JSONDecodeError, TypeError):
        hist = []

    tmp_path = None
    try:
        ext = (audio.filename or "input.webm").rsplit(".", 1)[-1].lower()
        tmp_path = AUDIO_TMP_DIR / f"webinput_{uuid.uuid4()}.{ext}"
        tmp_path.parent.mkdir(exist_ok=True)
        tmp_path.write_bytes(await audio.read())

        native_text, lang = sc.stt_transcribe(str(tmp_path))
    except Exception:
        return _error_result(hist, None, "Couldn't understand the audio — please try again or type your question.")
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    try:
        english_message = sc.translate_text(native_text, source_language_code=lang, target_language_code="en-IN")
    except Exception:
        return _error_result(hist, lang, "Couldn't process what you said right now — please try again.")

    result = _run_turn(hist, english_message, lang)
    result["user_text"] = native_text
    return result


@app.post("/api/greet")
def greet(req: GreetRequest):
    lang = req.language
    try:
        localized = sc.translate_text(GREETING_EN, target_language_code=lang) if lang != "en-IN" else GREETING_EN
    except Exception:
        # Text falls back to English, but the user's selected language must
        # NOT be silently overwritten — that would reset the whole app to
        # English even though they picked Hindi/Telugu/etc. (regression
        # caught by TEST 7: "verify existing language selection still works").
        localized = GREETING_EN

    audio_b64 = ""
    try:
        audio_path = Path(sc.tts(localized, language=lang))
        audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
        audio_path.unlink(missing_ok=True)
    except Exception:
        pass  # greeting text still shows even if audio fails

    return {"reply_text": localized, "audio_base64": audio_b64, "language": lang}


@app.get("/api/official-links")
def official_links():
    """
    Phase 3: the real, verified official government portal link(s) for each
    RTO service (see data/*/official_links.json — same source of truth Phase
    2's RAG grounding uses, just exposed directly here so the frontend can
    render an explicit "Open Official Portal" control without needing a full
    chat turn). No LLM call, no user data involved — purely static, so this
    endpoint can't itself be a source of hallucinated or unsafe links.
    """
    return {
        service_id: {
            "label": KNOWN_SERVICES.get(service_id, service_id),
            "links": [{"label": c.link_label, "url": c.url} for c in get_official_links(service_id)],
        }
        for service_id in KNOWN_SERVICES
    }


@app.get("/api/checklist/{service_id}")
def checklist(service_id: str):
    """
    Flat, deduplicated list of documents needed for a service, read straight
    from the verified dataset (same source of truth as the RAG pipeline) —
    not hand-duplicated in the frontend, so it can't drift out of sync with
    the real data. Only driving_license has verified steps today; other
    service ids return an empty list rather than guessing.
    """
    try:
        dataset = load_dataset(service_id)
    except FileNotFoundError:
        return {"service_id": service_id, "documents": []}

    seen = []
    for step in dataset.get("steps", []):
        for doc in step.get("docs_needed", []):
            if doc not in seen:
                seen.append(doc)
    return {"service_id": service_id, "documents": seen}


@app.get("/api/health")
def health():
    return {"ok": True, "sarvam_key_set": sc.SARVAM_API_KEY is not None}
