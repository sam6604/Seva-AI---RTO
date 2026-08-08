import uuid
from pathlib import Path

import streamlit as st

import intelligence
import sarvam_client as sc

st.set_page_config(page_title="SEVA AI — RTO Assistant", page_icon="🚗")
st.title("🚗 SEVA AI — RTO Assistant")
st.caption("Speak in any Indian language. SEVA replies back in the same language, by voice and text.")

DEFAULT_LANGUAGE = "hi-IN"
SERVICE_ID = "driving_license"
GREETING = "Namaste! Main SEVA AI hoon, RTO aur Driving License se judi madad ke liye. Aapko kis cheez mein madad chahiye?"


def init_state():
    if "initialized" in st.session_state:
        return
    st.session_state.initialized = True
    st.session_state.lang = DEFAULT_LANGUAGE
    st.session_state.llm_history = []  # [{"role": "user"/"assistant", "content": str}] — English, sent to the LLM
    st.session_state.chat_log = []  # [{"role", "lang", "text", "audio", "citations"}] — for display
    st.session_state.turn_id = 0


def bot_say(english_text: str, citations=None):
    lang = st.session_state.lang
    localized = sc.translate_text(english_text, target_language_code=lang)
    audio_path = Path(sc.tts(localized, language=lang))
    audio_bytes = audio_path.read_bytes()
    audio_path.unlink(missing_ok=True)  # bytes are kept in chat_log; no need to keep the file too
    st.session_state.chat_log.append(
        {"role": "assistant", "lang": lang, "text": localized, "audio": audio_bytes, "citations": citations or []}
    )


def user_turn_from_audio(audio_bytes: bytes) -> str:
    """Save recorded audio, transcribe natively, detect language, log it, return English text for the LLM."""
    tmp_path = Path("audio_output") / f"webinput_{uuid.uuid4()}.wav"
    tmp_path.parent.mkdir(exist_ok=True)
    tmp_path.write_bytes(audio_bytes)

    native_text, detected_lang = sc.stt_transcribe(str(tmp_path))
    tmp_path.unlink(missing_ok=True)  # only the transcript is needed past this point
    st.session_state.lang = detected_lang  # lock conversation language to what the user actually spoke
    st.session_state.chat_log.append({"role": "user", "lang": detected_lang, "text": native_text, "audio": None, "citations": []})

    return sc.translate_text(native_text, source_language_code=detected_lang, target_language_code="en-IN")


init_state()

if not st.session_state.llm_history:
    st.session_state.llm_history.append({"role": "assistant", "content": GREETING})
    bot_say(GREETING)

for msg in st.session_state.chat_log:
    with st.chat_message(msg["role"]):
        st.markdown(f"**({msg['lang']})** {msg['text']}")
        if msg["audio"]:
            st.audio(msg["audio"], format="audio/wav", autoplay=False)
        if msg.get("citations"):
            with st.expander("📚 Sources"):
                for c in msg["citations"]:
                    st.markdown(f"- {c}")

st.divider()
audio_value = st.audio_input("Tap to record your answer", key=f"audio_{st.session_state.turn_id}")
if audio_value is not None:
    english_reply = user_turn_from_audio(audio_value.getvalue())
    answer, citations = intelligence.respond(st.session_state.llm_history, english_reply, SERVICE_ID)
    bot_say(answer, citations=citations)
    st.session_state.turn_id += 1
    st.rerun()

if st.button("Start over"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
