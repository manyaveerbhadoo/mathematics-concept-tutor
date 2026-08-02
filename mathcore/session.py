"""
session.py — turns a one-shot reply into a conversation.

Before: the bot fired five questions and the conversation ended. A student
answered question 1 and had nowhere to go, so they left and opened ChatGPT.

Now: the bot asks ONE question, waits, reads the student's answer, checks it
where SymPy can, responds to what they actually said, and moves on.

WHAT IT STILL NEVER DOES:
    Give the answer. A wrong answer earns a narrower question, not a
    correction. "Your product is right, check the sum" is a nudge; "it's
    -2 and -3" is a solution, and we never cross that line.
"""

import re
import time
from dataclasses import dataclass, field

import sympy

from .concepts import Concept
from .parser import parse_student, MathInputError

SESSION_TTL = 60 * 60           # an hour of inactivity ends a session


@dataclass
class Session:
    user_id: int
    concept_id: str
    q_index: int = 0
    values: dict = field(default_factory=dict)
    expr: object = None
    wrong_here: int = 0          # wrong answers on the CURRENT question
    started: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)

    def expired(self) -> bool:
        return time.time() - self.touched > SESSION_TTL


_SESSIONS: dict = {}


def get(user_id: int):
    s = _SESSIONS.get(user_id)
    if s and s.expired():
        _SESSIONS.pop(user_id, None)
        return None
    return s


def start(user_id: int, concept_id: str, values: dict, expr=None) -> Session:
    s = Session(user_id=user_id, concept_id=concept_id, values=dict(values), expr=expr)
    _SESSIONS[user_id] = s
    return s


def end(user_id: int):
    _SESSIONS.pop(user_id, None)


# ---------------------------------------------------------------------------
# ANSWER CHECKING
# ---------------------------------------------------------------------------
# Each checker returns (verdict, nudge):
#   verdict True  -> right, move on
#   verdict False -> wrong, `nudge` says WHY without saying what's right
#   verdict None  -> we can't check this one; accept and continue

def _numbers_in(text: str):
    """Pull the numbers a student typed, however they phrased it."""
    out = []
    for tok in re.findall(r"-?\d+(?:\.\d+)?(?:/\d+)?", text.replace("−", "-")):
        try:
            out.append(sympy.Rational(tok) if "/" in tok else sympy.Integer(tok)
                       if "." not in tok else sympy.Float(tok))
        except Exception:
            pass
    return out


def _yes_no(text: str):
    """Read agreement or disagreement from a free-text reply.

    Negatives are tested FIRST and on word boundaries. Naive substring
    matching reads "no it isn't" as agreement, because "it is" sits inside
    "it isn't" -- which marks a correct student wrong. That is the worst
    possible failure for a bot meant to build confidence.
    """
    t = " " + text.strip().lower() + " "
    if re.search(r"\b(no|nope|nah|not|isn'?t|aren'?t|doesn'?t|wasn'?t|"
                 r"false|never|negative)\b", t):
        return False
    if re.search(r"\b(yes|yeah|yep|yup|true|correct|right|it is|sure)\b", t):
        return True
    return None


def _factor_pair(text, values, expr):
    """Two numbers multiplying to c and adding to b."""
    nums = _numbers_in(text)
    if len(nums) < 2:
        return None, ""
    m, n = nums[0], nums[1]
    try:
        b, c = sympy.sympify(values["b"]), sympy.sympify(values["c"])
    except Exception:
        return None, ""
    prod_ok, sum_ok = (m * n == c), (m + n == b)
    if prod_ok and sum_ok:
        return True, "Both conditions hold — that's the pair."
    if prod_ok and not sum_ok:
        return False, (f"Your product is right — those two do multiply to {c}. "
                       f"Now add them. Is that the middle coefficient you need? "
                       f"What does that tell you about the signs?")
    if sum_ok and not prod_ok:
        return False, (f"Your sum is right, but check the product. "
                       f"Multiply them — do you get {c}?")
    return False, (f"Neither condition holds yet. Take it one at a time: "
                   f"first list the pairs that multiply to {c}, then test each "
                   f"one's sum.")


def _discriminant(text, values, expr):
    nums = _numbers_in(text)
    if not nums:
        return None, ""
    try:
        a, b, c = (sympy.sympify(values[k]) for k in ("a", "b", "c"))
    except Exception:
        return None, ""
    want = b**2 - 4*a*c
    if any(n == want for n in nums):
        return True, "That's the discriminant."
    return False, ("Not quite. Work it out one piece at a time: what is b² on "
                   "its own? What is 4ac on its own? Watch the sign of c.")


def _is_perfect_square(text, values, expr):
    yn = _yes_no(text)
    if yn is None:
        return None, ""
    try:
        a, b, c = (sympy.sympify(values[k]) for k in ("a", "b", "c"))
    except Exception:
        return None, ""
    disc = b**2 - 4*a*c
    truth = bool(disc >= 0 and sympy.sqrt(disc).is_rational)
    if yn == truth:
        return True, "Correct — and that settles whether it factors."
    return False, ("Check again: is there a whole number that squares to give "
                   "your discriminant? Try a few and see how close you get.")


def _gcf(text, values, expr):
    nums = _numbers_in(text)
    if not nums or expr is None or not isinstance(expr, sympy.Add):
        return None, ""
    coeffs = []
    for t in expr.args:
        c, _ = t.as_coeff_Mul()
        if c.is_number:
            coeffs.append(abs(sympy.Integer(c)) if c.is_integer else None)
    if not coeffs or any(c is None for c in coeffs):
        return None, ""
    want = coeffs[0]
    for c in coeffs[1:]:
        want = sympy.gcd(want, c)
    if any(abs(n) == want for n in nums):
        return True, "That's the greatest common factor."
    if any(want % abs(n) == 0 for n in nums if n != 0):
        return False, ("That does divide all of them — but is it the LARGEST "
                       "one that does? Try doubling it and see if it still works.")
    return False, ("Check each term separately: does your number divide into "
                   "every single one with nothing left over?")


def _degrees_radians(text, values, expr):
    nums = _numbers_in(text)
    if not nums:
        return None, ""
    return None, ""     # too many valid forms to judge fairly


# (concept_id, question_index) -> checker
_CHECKS = {
    # Q2 asks them to LIST every pair -- a correct listing must not be marked
    # wrong just because one pair doesn't sum right. Only Q3 asks which pair.
    ("factoring-quadratic-simple", 2): _factor_pair,
    ("quadratic-formula", 1): _discriminant,
    ("quadratic-formula", 2): _is_perfect_square,
    ("gcf-factoring", 0): _gcf,
    ("angles-degrees-radians", 2): _degrees_radians,
}


def check(concept_id: str, q_index: int, text: str, values: dict, expr=None):
    fn = _CHECKS.get((concept_id, q_index))
    if not fn:
        return None, ""
    try:
        return fn(text, values, expr)
    except Exception:
        return None, ""


# ---------------------------------------------------------------------------
# CONVERSATION FLOW
# ---------------------------------------------------------------------------

_ACK = [
    "Good — next one.",
    "That's it. Keep going.",
    "Right. On to the next.",
    "Correct. Next step.",
]

_UNCHECKED = [
    "Noted — I can't verify that one automatically, so check it yourself as you go.",
    "Alright. Hold onto that and keep going.",
]


def advance(session: Session, concept: Concept, text: str, rendered: list):
    """Read the student's answer and decide what to say next.

    Returns (message, finished).
    """
    session.touched = time.time()
    verdict, nudge = check(session.concept_id, session.q_index, text,
                           session.values, session.expr)

    # Wrong: stay on this question and narrow it.
    if verdict is False:
        session.wrong_here += 1
        out = [f"**Not yet.** {nudge}"]
        if session.wrong_here >= 2:
            out.append("")
            out.append(f"_Two goes at this one. If you want the rule, "
                       f"`/hint {concept.id}` — but try once more first._")
        out.append("")
        out.append(f"**Question {session.q_index + 1}:** {rendered[session.q_index]}")
        return "\n".join(out), False

    # Right, or unverifiable: move on.
    session.wrong_here = 0
    session.q_index += 1

    if session.q_index >= len(rendered):
        return ("**That's the whole ladder.** You worked it out yourself — "
                "which means you can do the next one without me.\n\n"
                "_Was this useful? The buttons below help me improve it._"), True

    lead = (_ACK[session.q_index % len(_ACK)] if verdict is True
            else _UNCHECKED[session.q_index % len(_UNCHECKED)])
    body = (f"{lead}\n\n**Question {session.q_index + 1} of {len(rendered)}:** "
            f"{rendered[session.q_index]}")
    return body, False


def first_question(session: Session, rendered: list, concept: Concept) -> str:
    total = len(rendered)
    return (f"**This is: {concept.name}**\n\n"
            f"I'll take you through it one question at a time. Answer with "
            f"`/reply <your answer>` and I'll respond to what you say.\n\n"
            f"**Question 1 of {total}:** {rendered[0]}")
