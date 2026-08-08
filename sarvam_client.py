import base64
import os
import sys
import uuid
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv
from sarvamai import SarvamAI

load_dotenv()

if __name__ == "__main__":
    # Windows consoles default to a legacy codepage that can't encode
    # Hindi/Devanagari text returned by Sarvam — force UTF-8 for stdout.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

_client = SarvamAI(api_subscription_key=SARVAM_API_KEY) if SARVAM_API_KEY else None


def _ensure_output_dir():
    out = Path("audio_output")
    out.mkdir(exist_ok=True)
    return out


def stt_and_translate(audio_file_path: str) -> str:
    """
    Send an audio file to Sarvam Saaras (translate mode) and return the
    English translation of the speech. Raises Exception on failure.
    """
    if not _client:
        raise RuntimeError("SARVAM_API_KEY not set in environment")

    with open(audio_file_path, "rb") as f:
        resp = _client.speech_to_text.translate(file=f)

    if not resp.transcript:
        raise RuntimeError(f"Unexpected Sarvam STT response: {resp}")
    return resp.transcript


_AUDIO_MIME_TYPES = {
    "wav": "audio/wav",
    "webm": "audio/webm",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
}


def stt_transcribe(audio_file_path: str) -> Tuple[str, str]:
    """
    Send an audio file to Sarvam Saaras (transcribe mode, auto language
    detection) and return (native_script_transcript, detected_language_code).
    Unlike stt_and_translate(), this keeps the transcript in the speaker's
    own language/script instead of translating to English.
    """
    if not _client:
        raise RuntimeError("SARVAM_API_KEY not set in environment")

    path = Path(audio_file_path)
    ext = path.suffix.lstrip(".").lower()
    # Explicit (filename, bytes, content_type) tuple — Python's mimetypes
    # module maps .webm to "video/webm" by default, which would mislabel
    # browser-recorded audio, so we set the content type ourselves.
    content_type = _AUDIO_MIME_TYPES.get(ext, "application/octet-stream")
    file_tuple = (path.name, path.read_bytes(), content_type)

    resp = _client.speech_to_text.transcribe(file=file_tuple, mode="transcribe", language_code="unknown")

    if not resp.transcript:
        raise RuntimeError(f"Unexpected Sarvam STT response: {resp}")
    return resp.transcript, resp.language_code


def detect_language(text: str) -> str:
    """
    Detect the BCP-47 language code of plain typed text using Sarvam's
    language identification API. Used for the text-input path, where (unlike
    voice) there's no STT step to detect language from.
    """
    if not _client:
        raise RuntimeError("SARVAM_API_KEY not set in environment")
    resp = _client.text.identify_language(input=text)
    return resp.language_code


def translate_text(text: str, target_language_code: str, source_language_code: str = "en-IN") -> str:
    """
    Translate `text` from source_language_code to target_language_code using
    Sarvam's text translation API. Returns the original text unchanged if the
    source and target are the same.
    """
    if source_language_code == target_language_code:
        return text
    if not _client:
        raise RuntimeError("SARVAM_API_KEY not set in environment")

    resp = _client.text.translate(
        input=text, source_language_code=source_language_code, target_language_code=target_language_code
    )
    return resp.translated_text


def tts(text: str, language: str) -> str:
    """
    Call Sarvam Bulbul to synthesize audio for `text` in `language`
    (a BCP-47 code like "hi-IN"). Saves to ./audio_output/<uuid>.wav and
    returns the file path.

    NOTE: If SARVAM_API_KEY is not set, this will create a placeholder
    empty file so the demo flow can run without real TTS access.
    """
    out_dir = _ensure_output_dir()
    fname = f"{uuid.uuid4()}.wav"
    out_path = out_dir / fname

    if not _client:
        # Create a tiny placeholder file so demos can proceed offline
        out_path.write_bytes(b"")
        return str(out_path)

    resp = _client.text_to_speech.convert(
        text=text, language_code=language, speaker="anushka", model="bulbul:v2"
    )

    if not resp.audios:
        raise RuntimeError(f"Unexpected Sarvam TTS response: {resp}")
    out_path.write_bytes(base64.b64decode(resp.audios[0]))
    return str(out_path)


if __name__ == "__main__":
    # Simple smoke test that tries to exercise both functions.
    SAMPLE_AUDIO = "sample_input.wav"
    SAMPLE_TEXT = "Namaste, yeh SEVA AI ka demo greeting hai."

    print("Running sarvam_client smoke test...")
    if not SARVAM_API_KEY:
        print("SARVAM_API_KEY not set — tts() will create a placeholder file and stt test is skipped.")
    else:
        try:
            print("Testing STT (will attempt to call Sarvam Saaras)...")
            if not Path(SAMPLE_AUDIO).exists():
                print(f"Sample audio not found: {SAMPLE_AUDIO}; skipping STT test")
            else:
                print(stt_and_translate(SAMPLE_AUDIO))
        except Exception as e:
            print("STT test failed:", e)

    try:
        print("Testing TTS (Bulbul)...")
        out = tts(SAMPLE_TEXT, language="hi-IN")
        print("TTS output saved to:", out)
    except Exception as e:
        print("TTS test failed:", e)
