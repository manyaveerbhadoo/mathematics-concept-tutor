"""
tutor.py — the bot's teaching voice. Ties Steps 1-3 together.

    parser.py   reads what the student typed
    detect.py   works out which idea they were reaching for
    concepts.py holds what we know about that idea
    tutor.py    decides what to actually SAY

THE TEACHING ORDER, and it is deliberate:
    1. Name the idea.
    2. State the general pattern -- what you are ALWAYS doing here.
    3. Ask a question using the student's OWN numbers.
    4. Explain why the method is allowed.
    5. Warn about the usual trap.
    6. Name the escape route if the method stalls.

WHAT DELIBERATELY DOES NOT HAPPEN HERE:
    We do not show a fully worked example unless the student asks for one
    with /example. Handing over a solved problem of the same shape lets a
    student pattern-match their way through without ever doing the thinking
    -- which looks like teaching and isn't.
"""

import re
from dataclasses import dataclass, field

import sympy

from .parser import parse_student, MathInputError
from .detect import detect_transformation, detect_in_single, _free_symbol
from .concepts import ConceptLibrary, Concept

_LIB = None


def library() -> ConceptLibrary:
    global _LIB
    if _LIB is None:
        _LIB = ConceptLibrary()
    return _LIB


# ---------------------------------------------------------------------------
# PERSONALISATION — put the student's own numbers in the question.
# ---------------------------------------------------------------------------
# A generic "what two numbers multiply to your last term?" is easy to skim
# past. "What two numbers multiply to 6 and add to -5?" is a question the
# student has to actually answer. Same information, completely different
# amount of thinking.
#
# Note what these never do: state the answer. They restate the METHOD using
# the student's actual coefficients, and stop.

def _fmt(n):
    """Render a coefficient the way a student would write it."""
    return str(n)


def _show(e) -> str:
    """Render an expression safely for Discord.

    SymPy prints powers as x**2, and Discord reads ** as bold -- so an
    expression dropped into a message silently turns into mangled italics.
    Convert to the ^ students actually write, and wrap in a code span so
    no markdown can touch it.
    """
    s = str(e).replace("**", "^")
    s = re.sub(r"(?<=\d)\*(?=\d)", "×", s)   # keep 2*3 readable
    s = s.replace("*", "")                    # 5*x -> 5x, the way students write
    return "`" + s + "`"


def _quadratic_coeffs(expr, x):
    try:
        p = sympy.Poly(expr, x)
        if p.degree() != 2:
            return None
        a, b, c = p.all_coeffs()
        return a, b, c
    except Exception:
        return None


class _Fill(dict):
    """Placeholder lookup that degrades gracefully.

    If we can't work out the student's actual `c`, the question still reads
    sensibly as "...multiplies to give your last term".
    """
    _GENERIC = {
        "expr": "your expression", "a": "a", "b": "your middle number",
        "c": "your last term", "ac": "a×c", "terms": "your terms",
        "den": "your denominator", "inside": "what's inside your log",
        "base": "your base", "t1": "your first term", "t2": "your second term",
    }

    def __missing__(self, key):
        return self._GENERIC.get(key, "…")


def fill_values(expr, x) -> dict:
    """Everything we can work out about the student's expression.

    Nothing here computes an ANSWER -- only the raw ingredients a student
    would read off the page themselves.
    """
    v = {}
    if expr is None:
        return v
    try:
        v["expr"] = _show(expr)

        co = _quadratic_coeffs(expr, x)
        if co:
            a, b, c = co
            v.update(a=_fmt(a), b=_fmt(b), c=_fmt(c), ac=_fmt(a * c))

        if isinstance(expr, sympy.Add):
            v["terms"] = ", ".join(_show(t) for t in expr.args)
            if len(expr.args) == 2:
                pos = [t for t in expr.args if not t.could_extract_minus_sign()]
                neg = [-t for t in expr.args if t.could_extract_minus_sign()]
                if len(pos) == 1 and len(neg) == 1:
                    v["t1"], v["t2"] = _show(pos[0]), _show(neg[0])

        n, d = sympy.fraction(sympy.together(expr))
        if d != 1:
            v["den"] = _show(d)

        logs = list(expr.atoms(sympy.log))
        if logs:
            v["inside"] = _show(logs[0].args[0])

        pows = [p for p in expr.atoms(sympy.Pow) if p.exp.free_symbols]
        if pows:
            v["base"] = _show(pows[0].base)
    except Exception:
        pass
    return v


def render_questions(concept: Concept, values: dict) -> list:
    """The ladder, with the student's own numbers dropped in."""
    fill = _Fill(values)
    out = []
    for q in (concept.questions or [concept.ask]):
        try:
            out.append(q.format_map(fill))
        except Exception:
            out.append(q)
    return out


def personalise(concept_id: str, expr, x) -> str:
    """Legacy single-question hook, kept for the plain-English path."""
    if expr is None:
        return ""
    try:
        return _personalise(concept_id, expr, x) or ""
    except Exception:
        return ""


def _personalise(concept_id, expr, x):
    if concept_id == "factoring-quadratic-simple":
        co = _quadratic_coeffs(expr, x)
        if not co:
            return None
        a, b, c = co
        if a == 1:
            return (f"For your {_show(expr)} — what two numbers **multiply to "
                    f"{_fmt(c)}** and **add to {_fmt(b)}**?\n"
                    f"Write out the factor pairs of {_fmt(c)} first, then check "
                    f"which pair adds up. Don't skip the writing-out part.")
        return (f"Your leading coefficient is {_fmt(a)}, so use the AC method: "
                f"find two numbers that **multiply to a×c = {_fmt(a*c)}** and "
                f"**add to {_fmt(b)}**.")

    if concept_id == "factoring-by-grouping":
        co = _quadratic_coeffs(expr, x)
        if co:
            a, b, c = co
            return (f"Find two numbers that **multiply to a×c = {_fmt(a*c)}** and "
                    f"**add to {_fmt(b)}**. Use them to split your middle term "
                    f"into two, then group the four terms into pairs.")
        return None

    if concept_id == "difference-of-squares":
        if isinstance(expr, sympy.Add) and len(expr.args) == 2:
            pos = [t for t in expr.args if not t.could_extract_minus_sign()]
            neg = [-t for t in expr.args if t.could_extract_minus_sign()]
            if len(pos) == 1 and len(neg) == 1:
                return (f"**What squared gives {_show(pos[0])}?** And what squared "
                        f"gives {_show(neg[0])}?\nOnce you have those two, the "
                        f"pattern hands you the answer — no searching needed.")
        return None

    if concept_id == "gcf-factoring":
        if isinstance(expr, sympy.Add):
            terms = ", ".join(_show(t) for t in expr.args)
            return (f"Your terms are: {terms}.\nWhat is the largest number "
                    f"that divides into all of them? And is there a letter that "
                    f"appears in every single one?")
        return None

    if concept_id == "quadratic-formula":
        co = _quadratic_coeffs(expr, x)
        if co:
            a, b, c = co
            return (f"Here a = {_fmt(a)}, b = {_fmt(b)}, c = {_fmt(c)}.\n"
                    f"**Work out b² − 4ac on its own first.** If it's a perfect "
                    f"square, this would have factored. If not, the formula is "
                    f"your route.")
        return None

    if concept_id in ("log-product-rule", "log-quotient-rule", "log-power-rule"):
        logs = list(expr.atoms(sympy.log))
        if logs:
            inside = logs[0].args[0]
            return (f"Look at what's inside your log: {_show(inside)}.\n"
                    f"Are those pieces multiplied, divided, or is one raised to a "
                    f"power? Each case has its own rule — which one is yours?")
        return None

    if concept_id == "solving-exponential-equations":
        pows = [p for p in expr.atoms(sympy.Pow) if p.exp.free_symbols]
        if pows:
            base = pows[0].base
            return (f"Your unknown is stuck in the exponent of {_show(base)}.\n"
                    f"What operation brings an exponent back down to ground "
                    f"level? Apply it to *both* sides.")
        return None

    if concept_id == "domain-of-rational":
        n, d = sympy.fraction(sympy.together(expr))
        if d != 1:
            return (f"Your denominator is {_show(d)}.\n"
                    f"What value of x would make that equal zero? That's the one "
                    f"place your function can't exist.")
        return None

    return None


# ---------------------------------------------------------------------------

@dataclass
class TutorResponse:
    ok: bool
    concept: Concept = None
    confidence: float = 0.0
    alternatives: list = field(default_factory=list)
    ladder: list = field(default_factory=list)
    message: str = ""
    log_concept_id: str = ""
    tailored_ask: str = ""
    values: dict = field(default_factory=dict)

    # -- TIER 1: questions only. This is what a student gets by default. ----
    def to_text(self, tier: str = "questions") -> str:
        if not self.ok:
            return self.message
        if tier == "hint":
            return self._hint()
        if tier == "example":
            return self._example()

        c = self.concept
        out = [f"**This is: {c.name}**", "",
               "Work through these in order. Don't skip ahead — "
               "each one sets up the next.", ""]

        # "1)" rather than "1." so Discord doesn't renumber or indent them
        for i, q in enumerate(render_questions(c, self.values), 1):
            out.append(f"**{i})**  {q}")

        out += ["", "_Tell me which number you get stuck on and I'll go from there._"]

        if len(self.ladder) > 1:
            names = " → ".join(x.name for x in self.ladder[:-1])
            out += [f"_Builds on: {names} — ask me about those if they feel shaky._"]

        out += [f"_Tried and still stuck? `/hint {c.id}` for the rule behind it. "
                f"`/example {c.id}` for one worked through._"]

        if self.alternatives:
            alts = ", ".join(a.name for a in self.alternatives)
            out += [f"_Not what you meant? Could also be: {alts}._"]

        return "\n".join(out)

    # -- TIER 2: the rule and the reasoning. Opt-in. -----------------------
    def _hint(self) -> str:
        c = self.concept
        out = [f"**{c.name} — the rule behind it**", "",
               "_Only worth reading once you've had a real go at the questions._", "",
               f"**What you're always doing:** {c.plain}", "",
               f"**The rule:**  `{c.rule}`", "",
               f"**Why it's allowed:** {c.why}", "",
               f"**The usual trap:** {c.mistake}"]
        if c.when_stuck:
            out += ["", f"**If the method stalls:** {c.when_stuck}"]
        out += ["", f"_Still not landing? `/example {c.id}`._"]
        return "\n".join(out)

    # -- TIER 3: a full worked example, different numbers. Opt-in. --------
    def _example(self) -> str:
        c, ex = self.concept, self.concept.example
        out = [f"**{c.name} — worked through with different numbers**", "",
               f"**{ex['problem']}**"]
        out += [f"{i})  {s}" for i, s in enumerate(ex["steps"], 1)]
        if ex.get("note"):
            out += ["", f"_{ex['note']}_"]
        out += ["", "_Now go back to your own problem and do it yourself — "
                    "reading a solution isn't the same as being able to write one._"]
        return "\n".join(out)


# ---------------------------------------------------------------------------

_NOT_FOUND = (
    "I couldn't work out which idea that step is using. Try telling me in "
    "words instead — something like *\"why can I split a log of a product\"* "
    "or *\"how do I factor when there are four terms\"*."
)


def _build(hits, math_expr=None):
    lib = library()
    if not hits:
        return TutorResponse(ok=False, message=_NOT_FOUND)

    concept = lib.get(hits[0].concept_id)
    if concept is None:
        return TutorResponse(ok=False, message=_NOT_FOUND)

    alts = [lib.get(h.concept_id) for h in hits[1:3]]
    alts = [a for a in alts if a]

    x = _free_symbol(math_expr) if math_expr is not None else sympy.Symbol("x")

    return TutorResponse(
        ok=True,
        concept=concept,
        confidence=hits[0].confidence,
        alternatives=alts,
        ladder=lib.learning_path(concept.id),
        log_concept_id=concept.id,
        tailored_ask=personalise(concept.id, math_expr, x),
        values=fill_values(math_expr, x),
    )


def explain_step(before_text: str, after_text: str) -> TutorResponse:
    """Student shows one step of their own work: 'I went from A to B'."""
    try:
        b_shape = parse_student(before_text, structural=True)
        a_shape = parse_student(after_text, structural=True)
        b_math = parse_student(before_text)     # evaluated, for coefficients
    except MathInputError as exc:
        return TutorResponse(ok=False, message=str(exc))
    return _build(detect_transformation(b_shape, a_shape), math_expr=b_math)


def explain_stuck(expr_text: str) -> TutorResponse:
    """Student sends one expression: 'I don't know what to do here'."""
    try:
        shape = parse_student(expr_text, structural=True)
        math = parse_student(expr_text)
    except MathInputError as exc:
        return TutorResponse(ok=False, message=str(exc))
    return _build(detect_in_single(shape), math_expr=math)


def explain_question(text: str) -> TutorResponse:
    """Student asks in plain English: 'why does log of a product split up?'"""
    hits = library().search(text, limit=3)
    if not hits:
        return TutorResponse(ok=False, message=_NOT_FOUND)
    lib = library()
    c = hits[0]
    return TutorResponse(
        ok=True, concept=c, confidence=min(1.0, c._score / 12.0),
        alternatives=hits[1:3], ladder=lib.learning_path(c.id),
        log_concept_id=c.id,
    )


def explain_concept_by_id(concept_id: str) -> TutorResponse:
    lib = library()
    c = lib.get(concept_id)
    if not c:
        return TutorResponse(
            ok=False,
            message=f"I don't have a concept called `{concept_id}`. "
                    f"Try `/concepts` to see what I know.")
    return TutorResponse(ok=True, concept=c, confidence=1.0,
                         ladder=lib.learning_path(c.id), log_concept_id=c.id)
