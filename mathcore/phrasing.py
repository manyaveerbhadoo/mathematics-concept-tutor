"""
phrasing.py — OPTIONAL language model layer.

The bot works completely without this. Turn it on and replies stop sounding
templated: the model reads what the student actually wrote and responds to
*that* instead of picking from a list of canned openers.

------------------------------------------------------------------------
THE SAFETY PROPERTY, AND WHY IT HOLDS
------------------------------------------------------------------------
The model is never told the answer. It receives exactly three things:

    1. the question the student was asked
    2. the words the student typed
    3. a verdict token -- RIGHT, WRONG or UNKNOWN -- computed by SymPy

That's it. Not the correct value, not the expression, not the solution.

So there is no prompt, jailbreak, or clever phrasing that can extract the
answer from it, because the answer was never in the context window. This is
the difference between a filter ("you have the answer, don't say it") and an
architecture ("you don't have the answer"). Filters fall. This can't.

The model also never decides whether a student is right. SymPy does that,
deterministically, before the model is called. The model only chooses words.

If the key is missing, the request fails, or the reply looks wrong, we fall
straight back to the templates. It fails closed, every time.
"""

import json
import os
import re
import urllib.error
import urllib.request

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("MATHBOT_MODEL", "claude-haiku-4-5-20251001")

# OFF unless BOTH are set deliberately: an API key *and* an explicit opt-in.
# Requiring two switches means an API key that happens to be in the
# environment for some other project can never quietly start billing you
# through this one. Nothing here contacts a paid service by default.
ENABLED = bool(API_KEY) and os.environ.get("MATHBOT_LLM", "0") == "1"
TIMEOUT = float(os.environ.get("MATHBOT_LLM_TIMEOUT", "6"))

_ENDPOINT = "https://api.anthropic.com/v1/messages"

_SYSTEM = """You are a warm, encouraging maths tutor talking to a first-year \
university student in a Discord chat.

You will be given: the question the student was just asked, what they typed \
back, and a verdict computed by a separate symbolic maths engine.

Write ONE short reply, 1-2 sentences, reacting to what they actually wrote.

Absolute rules:
- NEVER state the answer to the question, or any part of it. You have not \
been told it and must not guess it.
- NEVER perform the calculation yourself or assert any mathematical value.
- If the verdict is WRONG, encourage them and point at what to re-check, \
without revealing what the right value is.
- If the verdict is RIGHT, confirm briefly and warmly. Do not restate their \
answer as if grading it.
- If the verdict is UNKNOWN, respond neutrally and warmly. Do NOT say you \
cannot check or verify it -- never mention your own limitations.
- No emoji. No markdown headers. Plain conversational sentences.
- British-ish, friendly, never patronising. Sound like a good TA, not a robot."""

_BANNED = re.compile(
    r"\b(the answer is|it is actually|correct answer|should be|equals)\b", re.I)


def available() -> bool:
    return ENABLED


def react(question: str, student_answer: str, verdict, concept_name: str = ""):
    """One warm sentence reacting to the student. None if unavailable.

    `verdict` is True / False / None -- already decided by SymPy.
    """
    if not ENABLED:
        return None

    token = {True: "RIGHT", False: "WRONG"}.get(verdict, "UNKNOWN")
    user = (f"Topic: {concept_name}\n"
            f"Question they were asked: {question}\n"
            f"What they typed: {student_answer}\n"
            f"Verdict from the maths engine: {token}\n\n"
            f"Write the reply.")

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 120,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }).encode()

    req = urllib.request.Request(
        _ENDPOINT, data=payload,
        headers={"content-type": "application/json",
                 "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read())
        text = "".join(b.get("text", "") for b in body.get("content", [])).strip()
    except Exception:
        return None            # fail closed, always

    if not text or len(text) > 400 or _BANNED.search(text):
        return None
    return text
