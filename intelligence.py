import os
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from sarvamai import SarvamAI

from retrieval import format_official_links, get_process_outline, retrieve

load_dotenv()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_CHAT_MODEL = "sarvam-105b"

_client = SarvamAI(api_subscription_key=SARVAM_API_KEY) if SARVAM_API_KEY else None

OUT_OF_SCOPE_REPLY = "Main sirf Driving License, Vehicle Registration aur Vehicle Ownership Transfer se judi madad kar sakti hoon."

# Shown when retrieval doesn't have enough verified evidence to ground a
# full answer (either the service has no verified process dataset yet, e.g.
# vehicle transfer/registration today, or the fused retrieval confidence is
# too low for this specific question) — per the hard "do not hallucinate"
# requirement, we hand this back to the user instead of guessing, and skip
# the LLM call entirely so it's also the fastest path in the pipeline.
#
# Phase 2: this is no longer a dead end. When we know which service the
# user meant, we still have a verified, real official portal link for it
# (see data/*/official_links.json) even though we don't have the verified
# step-by-step data — so the fallback stays actionable instead of just
# apologetic.
INSUFFICIENT_EVIDENCE_TEMPLATE = (
    "Mere paas is sawaal ke liye abhi verified/confirmed jaankari nahi hai. "
    "Kripya official RTO source (Parivahan portal ya apne nazdeeki RTO office) se confirm kariye."
)


def _insufficient_evidence_reply(service_id: Optional[str]) -> str:
    links_block = format_official_links(service_id)
    if not links_block:
        return INSUFFICIENT_EVIDENCE_TEMPLATE
    return (
        f"{INSUFFICIENT_EVIDENCE_TEMPLATE}\n\n"
        f"Aap seedha yahan se shuru kar sakte hain (official portal):\n{links_block}"
    )


# Scope and behavior are enforced by instructing the model, not by
# hand-coded keyword lists or a rigid state machine. Retrieval decides
# *whether* there's grounding evidence (see respond()); this prompt decides
# *how* the model uses whatever evidence it's given.
#
# Phase 3 Part 2: the closing "what language/register to write in" paragraph
# is now built dynamically from the resolved target language instead of a
# fixed "always Hinglish" instruction. Why this matters: respond() only ever
# sees the ENGLISH-TRANSLATED user message (translation happens upstream in
# backend/main.py before intelligence.respond() is called), so the model
# itself has no way to tell whether the user originally wrote in Hindi,
# Telugu, or Hinglish — a fixed "respond in Hinglish" instruction would
# produce Hinglish-flavored English even when the target is Hindi/Telugu/etc,
# which is exactly the "accidentally converting Hindi into Hinglish" failure
# mode called out by the spec. Instead: when the target is a specific Indian
# language, this reply is going to be machine-translated into that
# language's proper script afterward (see backend/main.py's translate_text
# call) — so the model should write clean, plain English here for a clean
# translation, not a Hindi/English blend that would confuse the translator.
# Hinglish is reserved for when the target IS English (the user is
# communicating in English or intentionally mixing already).
def _language_instruction(target_lang: str) -> str:
    if target_lang == "en-IN":
        return (
            "Write your reply in English. If the user's own phrasing mixed Hindi words into English "
            "(Hinglish) — you can tell from their message below — you may reply in that same natural "
            "Hinglish style. Otherwise write clean English."
        )
    return (
        "Write your reply in clean, plain, simple English. This text will be automatically machine-"
        "translated into the user's selected language afterward, so do NOT mix languages, do NOT use "
        "transliterated Hindi/English blends (Hinglish), and do NOT write in any script other than "
        "English here — a clean, unambiguous English sentence translates correctly into proper native "
        "script; a Hinglish sentence does not."
    )


def _build_system_prompt(target_lang: str = "en-IN") -> str:
    return (
        "You are SEVA, a voice-first RTO (Regional Transport Office) help-desk assistant for India, "
        "covering three services: Driving Licence, Vehicle Registration, and Vehicle Ownership Transfer.\n\n"
        "You will be given a block of 'Reference material' retrieved for this specific question, each "
        "line tagged with its source. Ground your answer in that material — do not invent documents, "
        "fees, eligibility rules, procedures, government requirements, application status, or official "
        "URLs that aren't in the reference material. If the reference material only partially covers the "
        "question, answer the part it covers and clearly say the rest isn't confirmed yet.\n\n"
        "Be actionable, not just explanatory: every reply should end with a clear 'what to do next' — "
        "the next concrete action the user should take, not only a description of the process. When the "
        "reference material includes a 'Full process outline', use it to figure out where the user "
        "currently is in the process (from the conversation so far) and continue from there — name the "
        "required documents at the step where they're actually needed, don't front-load every document "
        "for every step at once. When the reference material includes an official portal link, give the "
        "user that exact link as the actionable next step (e.g. 'you can do this at <link>'), instead of "
        "just saying to check the official website.\n\n"
        "For the Driving Licence prerequisite flow specifically, when reference material for it is "
        "present: guide the user through it naturally — ask any prerequisite questions one at a time, "
        "then walk through the steps, waiting for the user to confirm each step is done before moving on. "
        "If the user's answer doesn't fit neatly, use your own judgment to keep the conversation moving.\n\n"
        "Field-level guidance ('what should I enter here?', 'what is X field?', 'what does this field "
        "mean?'): when the user is asking about a specific form field and reference material for it is "
        "present, answer in this shape — (1) what the field means, (2) what information they should "
        "enter, (3) where they can find that information (e.g. which document), when applicable, (4) a "
        "simple concrete example, (5) what NOT to enter, when useful. Never invent a value for the user "
        "to type in. If they ask 'what should I enter here' without naming which field, ask them to tell "
        "you the field's label or name — you cannot see their screen, and you should never assume or "
        "guess which field they mean.\n\n"
        "If the reference material says data is not yet verified for a service, say so plainly and point "
        "the user to the official RTO/Parivahan source — don't fill the gap from general knowledge.\n\n"
        f"If a question is entirely unrelated to RTO/vehicles, reply with EXACTLY this sentence and "
        f"nothing else: \"{OUT_OF_SCOPE_REPLY}\"\n\n"
        "Keep responses short and simple. " + _language_instruction(target_lang)
    )


# Backward-compatible module-level constant (English-target prompt) for any
# code that still imports SYSTEM_PROMPT directly.
SYSTEM_PROMPT = _build_system_prompt("en-IN")


# Phase 3: shown when the LLM call itself fails or returns something
# unusable (network error, API error, empty response) — a clear, friendly
# message instead of a crash, per the explicit error-handling requirement.
ASSISTANT_UNAVAILABLE_REPLY = (
    "Abhi mujhe jawaab dene mein dikkat aa rahi hai (connection ya server issue). "
    "Kripya thodi der baad phir try kariye."
)


class AssistantUnavailableError(Exception):
    """Raised when the LLM call fails or returns something unusable — callers
    should show a friendly message instead of crashing (Phase 3 requirement:
    never assume response.content exists before using it)."""


def _call_llm(messages: List[Dict[str, str]]) -> str:
    if not _client:
        raise RuntimeError("SARVAM_API_KEY not set")
    try:
        resp = _client.chat.completions(model=SARVAM_CHAT_MODEL, messages=messages)
    except Exception as e:  # network error, API error, rate limit, etc.
        raise AssistantUnavailableError(f"Sarvam chat API call failed: {e}") from e

    choices = getattr(resp, "choices", None)
    if not choices:
        raise AssistantUnavailableError("Sarvam chat API returned no choices")
    content = getattr(choices[0].message, "content", None)
    if not content or not content.strip():
        raise AssistantUnavailableError("Sarvam chat API returned an empty response")
    return content.strip()


def respond(
    history: List[Dict[str, str]],
    user_message: str,
    service_id: Optional[str] = None,
    target_lang: str = "en-IN",
) -> Tuple[str, List[str]]:
    """
    Single entry point for the assistant.

    `service_id`: pass None (the default) to let the hybrid retrieval
    pipeline auto-detect which of the 3 RTO services the message is about
    (metadata/service filtering); pass an explicit id to pin it (e.g. a
    frontend service selector, if one gets added later).

    `target_lang`: the BCP-47 code the reply will ultimately be shown/spoken
    in (Phase 3 Part 2) — shapes whether the model may use Hinglish (only
    when target_lang == "en-IN") or must write clean English for downstream
    translation (any other target). Does not affect retrieval or grounding,
    only the language instruction in the system prompt.

    Mutates `history` in place (appends the user turn and the reply) so the
    caller can just keep reusing the same list turn after turn. Returns
    (reply_text, citations) — citations is [] for a refusal or an
    insufficient-evidence response.
    """
    if not _client:
        return "SARVAM_API_KEY set nahi hai, isliye main abhi jawaab nahi de sakta.", []

    result = retrieve(user_message, service_id=service_id, top_k=4)

    if result.insufficient_evidence:
        reply = _insufficient_evidence_reply(result.service_id)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        return reply, []

    citations = [f"[{c.source}] {c.text}" for c in result.chunks]
    context_block = "\n".join(f"- {c}" for c in citations)

    # Phase 2: attach the complete ordered process outline (not just the
    # top-k retrieved fragments) so the model can track continuous
    # multi-turn progress and give a concrete "what's next", and attach the
    # official portal link so the answer ends with something actionable.
    extra_blocks = []
    outline = get_process_outline(result.service_id)
    if outline:
        extra_blocks.append(f"Full process outline (for tracking progress; use conversation history "
                             f"to judge which step the user is on):\n{outline}")
    links_block = format_official_links(result.service_id)
    if links_block:
        extra_blocks.append(f"Official portal link(s) for this service:\n{links_block}")
    extra_context = ("\n\n" + "\n\n".join(extra_blocks)) if extra_blocks else ""

    augmented_message = f"Reference material:\n{context_block}{extra_context}\n\nUser: {user_message}"
    messages = [{"role": "system", "content": _build_system_prompt(target_lang)}] + history + [{"role": "user", "content": augmented_message}]

    try:
        reply = _call_llm(messages)
    except AssistantUnavailableError:
        reply = ASSISTANT_UNAVAILABLE_REPLY
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        return reply, []

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})

    is_refusal = OUT_OF_SCOPE_REPLY.strip().lower() in reply.strip().lower()
    return reply, ([] if is_refusal else citations)
