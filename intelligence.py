import os
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from sarvamai import SarvamAI

from dataset_loader import get_relevant_context

load_dotenv()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_CHAT_MODEL = "sarvam-105b"

_client = SarvamAI(api_subscription_key=SARVAM_API_KEY) if SARVAM_API_KEY else None

OUT_OF_SCOPE_REPLY = "Main sirf Driving License aur RTO se judi madad kar sakti hoon."

# Scope and behavior are enforced by instructing the model, not by hand-coded
# keyword lists or a rigid state machine — the reference material grounds
# the DL flow specifically, everything else is answered from the model's
# own general knowledge with a clear accuracy caveat.
SYSTEM_PROMPT = (
    "You are SEVA, a voice-first RTO (Regional Transport Office) help-desk assistant for India.\n\n"
    "For Learner's/Driving License (DL) applications specifically: you have fully "
    "verified, step-by-step reference material below. Guide the user through it "
    "naturally — ask any prerequisite questions it lists one at a time, then walk "
    "through the process step by step, waiting for the user to confirm each step "
    "is done before moving to the next. If the user's answer doesn't fit neatly "
    "(e.g. a vehicle type not explicitly listed), use your own judgment to respond "
    "helpfully and keep the conversation moving — don't just say you don't understand.\n\n"
    "For any other RTO topic (vehicle registration, permits, challans, traffic rules, "
    "etc.): you may answer using your own general knowledge, but always add a short "
    "warning that this isn't from verified data yet and to confirm with the official "
    "RTO source.\n\n"
    f"If a question is entirely unrelated to RTO/vehicles, reply with EXACTLY this "
    f"sentence and nothing else: \"{OUT_OF_SCOPE_REPLY}\"\n\n"
    "Keep responses short and simple, in a Hindi/English mix (Hinglish) unless the "
    "user is clearly writing in a different language."
)


def _call_llm(messages: List[Dict[str, str]]) -> str:
    if not _client:
        raise RuntimeError("SARVAM_API_KEY not set")
    resp = _client.chat.completions(model=SARVAM_CHAT_MODEL, messages=messages)
    return resp.choices[0].message.content.strip()


def respond(history: List[Dict[str, str]], user_message: str, service_id: str = "driving_license") -> Tuple[str, List[str]]:
    """
    Single entry point for the assistant. Given the conversation so far and
    the user's latest message, retrieves grounding context and lets the LLM
    decide how to respond — ask the next prereq question, narrate the next
    step, answer a tangent, or refuse — using the conversation history
    itself to track progress instead of a hand-coded state machine.

    Mutates `history` in place (appends the user turn and the reply) so the
    caller can just keep reusing the same list turn after turn. Returns
    (reply_text, citations) — citations is [] when the reply is a refusal.
    """
    if not _client:
        return "SARVAM_API_KEY set nahi hai, isliye main abhi jawaab nahi de sakta.", []

    citations = get_relevant_context(user_message, service_id, top_k=4)
    context_block = "\n".join(f"- {c}" for c in citations) if citations else "(no closely matching reference material)"

    augmented_message = f"Reference material:\n{context_block}\n\nUser: {user_message}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": augmented_message}]
    reply = _call_llm(messages)

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})

    is_refusal = OUT_OF_SCOPE_REPLY.strip().lower() in reply.strip().lower()
    return reply, ([] if is_refusal else citations)
