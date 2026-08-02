"""
session.py — the conversation.

The bot asks one thing, waits, reads what the student actually wrote, checks
it where it can, and responds to *that*. It remembers what they said earlier
and keeps the thread going.

TWO RULES IT NEVER BREAKS
    1. It never gives the answer. A wrong reply earns a narrower question.
    2. It never tells a student it "can't verify" something. That phrase makes
       the bot sound broken and shoves the work back rudely. If a step can't
       be checked, the reply just moves on warmly -- a student should never be
       able to tell which steps were verified and which weren't.
"""

import re
import time
from dataclasses import dataclass, field

import sympy

from .concepts import Concept
from . import phrasing

SESSION_TTL = 60 * 60           # an hour of quiet ends a conversation
MAX_SESSIONS = 500              # a class is ~200; headroom, not a cap


@dataclass
class Session:
    user_id: int
    concept_id: str
    q_index: int = 0
    values: dict = field(default_factory=dict)
    expr: object = None
    wrong_here: int = 0
    got_right: int = 0
    answers: list = field(default_factory=list)     # what they've told us
    started: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)

    def expired(self) -> bool:
        return time.time() - self.touched > SESSION_TTL


# Keyed by user id, so two hundred students hold two hundred separate
# conversations at once and never see each other's.
_SESSIONS: dict = {}


def _sweep():
    """Drop stale conversations so memory doesn't grow across a whole term."""
    for uid in [u for u, s in _SESSIONS.items() if s.expired()]:
        _SESSIONS.pop(uid, None)
    if len(_SESSIONS) > MAX_SESSIONS:
        oldest = sorted(_SESSIONS.items(), key=lambda kv: kv[1].touched)[:50]
        for uid, _ in oldest:
            _SESSIONS.pop(uid, None)


def get(user_id: int):
    s = _SESSIONS.get(user_id)
    if s and s.expired():
        _SESSIONS.pop(user_id, None)
        return None
    return s


def start(user_id: int, concept_id: str, values: dict, expr=None) -> Session:
    _sweep()
    s = Session(user_id=user_id, concept_id=concept_id,
                values=dict(values or {}), expr=expr)
    _SESSIONS[user_id] = s
    return s


def end(user_id: int):
    _SESSIONS.pop(user_id, None)


def active_count() -> int:
    _sweep()
    return len(_SESSIONS)


# ---------------------------------------------------------------------------
# READING WHAT THE STUDENT WROTE
# ---------------------------------------------------------------------------

def _numbers_in(text: str):
    out = []
    for tok in re.findall(r"-?\d+(?:\.\d+)?(?:/\d+)?", (text or "").replace("−", "-")):
        try:
            if "/" in tok:
                out.append(sympy.Rational(tok))
            elif "." in tok:
                out.append(sympy.Float(tok))
            else:
                out.append(sympy.Integer(tok))
        except Exception:
            pass
    return out


def _yes_no(text: str):
    """Negatives first, on word boundaries.

    Substring matching reads "no it isn't" as agreement, because "it is" sits
    inside "it isn't" -- marking a correct student wrong. For a bot meant to
    build confidence that's the worst failure available.
    """
    t = " " + (text or "").strip().lower() + " "
    if re.search(r"\b(no|nope|nah|not|isn'?t|aren'?t|doesn'?t|wasn'?t|can'?t|"
                 r"false|never|negative)\b", t):
        return False
    if re.search(r"\b(yes|yeah|yep|yup|true|correct|right|it is|sure)\b", t):
        return True
    return None


def _stuck_signal(text: str) -> bool:
    """Are they telling us they're lost, rather than answering?"""
    t = (text or "").strip().lower()
    return bool(re.search(r"(i (don'?t|do not) (know|get|understand)|no idea|"
                          r"\bstuck\b|confused|\blost\b|\bidk\b|dunno|"
                          r"^\s*help\s*$|^\s*\?+\s*$)", t))


# ---------------------------------------------------------------------------
# CHECKING — driven by data in the library, not hardcoded here
# ---------------------------------------------------------------------------
# Each concept may carry a "checks" list parallel to "questions". An entry is
# null (nothing to judge) or a small spec. Keeping it in the data file means
# an instructor can see and change what counts as correct.

def _subs(expr_str: str, values: dict):
    """Evaluate something like 'b**2 - 4*a*c' with the student's own numbers."""
    try:
        env = {k: sympy.sympify(v) for k, v in (values or {}).items()
               if isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v)}
        return sympy.sympify(expr_str).subs(env)
    except Exception:
        return None


def _run_check(spec, text, values, expr):
    """Returns (verdict, nudge). verdict None means nothing to judge."""
    if not spec:
        return None, ""
    kind = spec.get("kind")

    if kind == "number":
        want = _subs(spec["value"], values)
        nums = _numbers_in(text)
        if want is None or not getattr(want, "is_number", False) or not nums:
            return None, ""
        if any(sympy.simplify(n - want) == 0 for n in nums):
            return True, ""
        return False, spec.get("nudge", "Not that one. Try breaking it into "
                                        "smaller pieces and see where it shifts.")

    if kind == "pair":
        prod, summ = _subs(spec["product"], values), _subs(spec["sum"], values)
        nums = _numbers_in(text)
        if prod is None or summ is None or len(nums) < 2:
            return None, ""
        m, n = nums[0], nums[1]
        p_ok, s_ok = (m * n == prod), (m + n == summ)
        if p_ok and s_ok:
            return True, ""
        if p_ok:
            return False, (f"Those two do multiply to {prod} — that half's "
                           f"right. Now add them. Is that the number you need? "
                           f"Have a think about what the signs have to be.")
        if s_ok:
            return False, (f"They add up correctly. Now multiply them — do you "
                           f"land on {prod}?")
        return False, (f"Neither part holds yet. Try it in two stages: write "
                       f"out the pairs that multiply to {prod} first, then test "
                       f"each pair's sum.")

    if kind == "perfect_square":
        yn, want = _yes_no(text), _subs(spec["of"], values)
        if yn is None or want is None or not getattr(want, "is_number", False):
            return None, ""
        truth = bool(want >= 0 and sympy.sqrt(want).is_rational)
        if yn == truth:
            return True, ""
        return False, ("Have another look — is there a whole number you can "
                       "square to land exactly on it? Try a couple either side.")

    if kind == "yesno":
        yn, truth = _yes_no(text), spec.get("answer")
        if yn is None or truth is None:
            return None, ""
        if yn == bool(truth):
            return True, ""
        return False, spec.get("nudge", "Not quite — go back to what the "
                                        "definition actually requires.")

    if kind == "gcf":
        nums = _numbers_in(text)
        if not nums or expr is None or not isinstance(expr, sympy.Add):
            return None, ""
        coeffs = []
        for t in expr.args:
            co, _ = t.as_coeff_Mul()
            if not co.is_number or not co.is_integer:
                return None, ""
            coeffs.append(abs(sympy.Integer(co)))
        want = coeffs[0]
        for co in coeffs[1:]:
            want = sympy.gcd(want, co)
        if any(abs(n) == want for n in nums):
            return True, ""
        if any(n != 0 and want % abs(n) == 0 for n in nums):
            return False, ("That does divide into all of them — but is it the "
                           "biggest one that does? Try doubling it and see if "
                           "it still goes in cleanly.")
        return False, ("Check them one at a time: does your number go into "
                       "every term with nothing left over?")

    return None, ""


def check(concept: Concept, q_index: int, text: str, values: dict, expr=None):
    specs = getattr(concept, "checks", None) or []
    spec = specs[q_index] if q_index < len(specs) else None
    try:
        return _run_check(spec, text, values, expr)
    except Exception:
        return None, ""


# ---------------------------------------------------------------------------
# HOW IT TALKS
# ---------------------------------------------------------------------------
# Deliberately not "Question 3 of 5". A numbered checklist reads like a form.
# A mentor just keeps the thread going.

_AFTER_RIGHT = ["Yes — that's it.", "Exactly right.", "That's the one.",
                "Good, that's exactly what I was after.", "Spot on."]
_ONWARD = ["So now:", "Next thing to pin down:", "Right — so:",
           "Good. Here's the bit that matters:", "Okay, keep going:"]
_NEUTRAL = ["Okay, hold onto that.", "Good — that's what we need.",
            "Right, that gives us something to work with.", "Got it."]
_ENCOURAGE = ["You're nearly there.", "You're closer than you think.",
              "Good instinct — just not quite landed."]


def _pick(bank, seed):
    return bank[seed % len(bank)]


def first_question(session: Session, rendered: list, concept: Concept) -> str:
    return (f"**{concept.name}** — let's work through it together.\n\n"
            f"I'll ask one thing at a time. Answer with `/reply` and whatever "
            f"you've got, even if you're not sure of it.\n\n"
            f"{rendered[0]}")


def advance(session: Session, concept: Concept, text: str, rendered: list):
    """Read the answer, respond to it, decide what comes next.

    Returns (message, finished).
    """
    session.touched = time.time()
    session.answers.append((text or "").strip())

    # "I don't know" isn't a wrong answer -- it's a request for a smaller step.
    if _stuck_signal(text):
        session.wrong_here += 1
        return (f"No problem — that's a normal place to get stuck.\n\n"
                f"Take the smallest piece of it you can. Just this bit:\n\n"
                f"{rendered[session.q_index]}\n\n"
                f"_Or if you'd rather see the rule first, `/hint {concept.id}`. "
                f"No shame in it._"), False

    verdict, nudge = check(concept, session.q_index, text,
                           session.values, session.expr)

    # The model, if configured, only chooses the WORDS. It is never told the
    # answer and never decides the verdict -- SymPy already did that above.
    warm = phrasing.react(rendered[session.q_index], text, verdict, concept.name)

    if verdict is False:
        session.wrong_here += 1
        opener = warm or _pick(_ENCOURAGE, session.wrong_here)
        out = f"{opener} {nudge}".strip()
        if session.wrong_here >= 3:
            out += (f"\n\n_Third go at this one — `/hint {concept.id}` gives "
                    f"you the rule behind it. Sometimes that's the faster route._")
        return out, False

    if verdict is True:
        session.got_right += 1
    session.wrong_here = 0
    session.q_index += 1

    if session.q_index >= len(rendered):
        closer = ("**And that's the whole thing.**\n\n"
                  "Every step of that was you — I only kept asking. Which means "
                  "when this turns up on the midterm, you'll get there the same way.")
        if session.got_right:
            closer += f"\n\nYou got {session.got_right} of those right first time."
        closer += "\n\n_Did this actually help? The buttons below tell me._"
        return closer, True

    lead = warm or (_pick(_AFTER_RIGHT, session.q_index) if verdict is True
                    else _pick(_NEUTRAL, session.q_index))
    return f"{lead} {_pick(_ONWARD, session.q_index + 1)}\n\n{rendered[session.q_index]}", False
