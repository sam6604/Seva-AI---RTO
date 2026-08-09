"""
Explicit language-switch detection — "I want to speak in English" while the
user is actually speaking Telugu, "hindi mein baat karo" typed in the middle
of an English conversation, etc.

Deliberately NOT an LLM call: this sits on the hot path of every single
turn, so it has to be near-free the way the Phase 1 service router is. It's
also deliberately conservative (rule-based, not fuzzy) — a missed switch
request just means the user asks again; a FALSE switch (changing someone's
language when they didn't ask) is much more disruptive, so precision matters
more than recall here.

Why this works across every input language with only English patterns: the
existing pipeline already translates every user message to English before
it reaches this point (see backend/main.py — both chat_text and chat_voice
translate to English before calling intelligence.respond()), so a request
made in Telugu script ("నాకు ఇంగ్లీష్‌లో మాట్లాడాలి") arrives here as
English text (e.g. "I need to speak in English") after that translation —
one pattern set, every source language covered, no per-language keyword
lists to maintain.
"""
import re
from typing import Optional

# BCP-47 codes matching the language picker in frontend/src/App.jsx.
LANGUAGE_NAME_TO_CODE = {
    "english": "en-IN",
    "hindi": "hi-IN",
    "telugu": "te-IN",
    "tamil": "ta-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "marathi": "mr-IN",
    "gujarati": "gu-IN",
    "bengali": "bn-IN",
    "punjabi": "pa-IN",
    "odia": "od-IN",
    "oriya": "od-IN",  # common alternate spelling
    "urdu": "ur-IN",
}

# Ordered from most to least specific isn't necessary here — every pattern
# requires an explicit verb (speak/talk/reply/switch/continue) near a
# language name, so a bare mention of a language name in conversation
# ("what documents does Telugu Nadu RTO need") won't false-positive.
_SWITCH_PATTERNS = [
    r"\b(speak|talk|reply|respond|answer|switch|continue|change)\b[^.!?]{0,25}\b(in|to|into)\b[^.!?]{0,15}\bLANG\b",
    r"\bi\s+(want|need|would like)\s+to\s+(speak|talk)\s+(in\s+)?LANG\b",
    r"\bLANG\b[^.!?]{0,12}\b(mein|me)\b[^.!?]{0,12}\b(baat|bolo|bolna|bataiye|jawab|reply)\b",
]


def detect_language_switch(english_text: str) -> Optional[str]:
    """
    Returns a BCP-47 language code if `english_text` (already translated to
    English by the caller) contains an explicit request to switch the
    conversation's response language, else None.
    """
    if not english_text:
        return None
    text = english_text.lower()
    for lang_name, code in LANGUAGE_NAME_TO_CODE.items():
        for pattern in _SWITCH_PATTERNS:
            if re.search(pattern.replace("LANG", re.escape(lang_name)), text):
                return code
    return None
