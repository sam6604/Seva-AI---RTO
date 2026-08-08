"""
Service/intent detection — "which of the 3 RTO services is this query
about?"

Deliberately NOT an LLM call: it's the first thing that happens on every
turn, sits in front of retrieval, and the requirements explicitly say to
avoid unnecessary LLM calls and unnecessary sequential API calls on the hot
path. A small keyword-rule classifier is effectively free (microseconds)
and, for a closed set of 3 known services, is plenty accurate — this is the
"metadata/service filtering before expensive retrieval" step.

Works on the English-translated message (the pipeline already translates
voice/text input to English before this point), so one rule set covers
every input language.

Uses word-stem substring checks (not exact multi-word phrases) so word
order/inflection ("transfer vehicle ownership" vs "ownership transfer",
"register a new vehicle" vs "vehicle registration") doesn't break matching.

Returns None when nothing matches, meaning "search across all services"
rather than guessing wrong and filtering out the right answer.
"""
import re
from typing import Optional

_TRANSFER_STEMS = ("transfer", "second-hand", "second hand", "used vehicle", "change of owner", "resale", "resell")
_REGISTRATION_STEMS = ("regist", "rc book", "hypothecation", "rc issue")
_DL_STEMS = ("driving licen", "driving test", "learner", " dl ", "dl ", " ll ")


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower()).strip() + " "


def detect_service(text: str) -> Optional[str]:
    t = _norm(text)

    if any(stem in t for stem in _TRANSFER_STEMS):
        return "vehicle_transfer"
    if any(stem in t for stem in _REGISTRATION_STEMS):
        return "vehicle_registration"
    if any(stem in t for stem in _DL_STEMS) or "licen" in t:
        return "driving_license"
    return None
