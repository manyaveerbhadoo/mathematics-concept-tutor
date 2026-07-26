"""
tutor.py — the bot's teaching voice. Ties Steps 1-3 together.

    parser.py   reads what the student typed
    detect.py   works out which idea they were reaching for
    concepts.py holds what we know about that idea
    tutor.py    decides what to actually SAY

THE TEACHING ORDER, and it is deliberate:
    1. Name the idea.
    2. Ask a question back.        <- the student thinks before we explain
    3. Explain it plainly.
    4. Show a DIFFERENT example.
    5. Warn about the usual trap.
    6. Offer the ladder underneath if the idea sits on prerequisites.

What never happens: solving the student's problem, or saying whether their
step was right. The bot points at the path. The student walks it.
"""

from dataclasses import dataclass, field

from .parser import parse_student, MathInputError
from .detect import detect_transformation, detect_in_single
from .concepts import ConceptLibrary, Concept

_LIB = None


def library() -> ConceptLibrary:
    global _LIB
    if _LIB is None:
        _LIB = ConceptLibrary()
    return _LIB


@dataclass
class TutorResponse:
    ok: bool
    concept: Concept = None
    confidence: float = 0.0
    alternatives: list = field(default_factory=list)
    ladder: list = field(default_factory=list)
    message: str = ""          # used when ok is False
    log_concept_id: str = ""   # for anonymous analytics

    # ---- rendering ----------------------------------------------------
    def to_text(self, show_ladder: bool = True) -> str:
        if not self.ok:
            return self.message

        c = self.concept
        out = [
            f"**The idea here is: {c.name}**",
            "",
            "**Before I explain — have a go at this:**",
            f"> {c.ask}",
            "",
            c.plain,
            "",
            f"**The rule:**  `{c.rule}`",
            f"**Why it works:** {c.why}",
            "",
            f"**Here's a different one, worked all the way through — {c.example['problem']}**",
        ]
        out += [f"  {i}. {s}" for i, s in enumerate(c.example["steps"], 1)]
        if c.example.get("note"):
            out += ["", f"_{c.example['note']}_"]
        out += ["", f"**Watch out:** {c.mistake}"]

        if show_ladder and len(self.ladder) > 1:
            names = " -> ".join(x.name for x in self.ladder[:-1])
            out += ["", f"_This one builds on: {names}._",
                    "_If any of those feel shaky, ask me about them first — "
                    "they make this one much easier._"]

        if self.alternatives:
            alts = ", ".join(a.name for a in self.alternatives)
            out += ["", f"_Not what you meant? It might also be: {alts}._"]

        return "\n".join(out)


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

_NOT_FOUND = (
    "I couldn't work out which idea that step is using. Try telling me in "
    "words instead — something like *\"why can I split a log of a product\"* "
    "or *\"how do I factor when there are four terms\"*."
)


def _build(hits, extra_alt_ids=()):
    lib = library()
    if not hits:
        return TutorResponse(ok=False, message=_NOT_FOUND)

    best = hits[0]
    concept = lib.get(best.concept_id)
    if concept is None:
        return TutorResponse(ok=False, message=_NOT_FOUND)

    alts = []
    for h in hits[1:3]:
        c = lib.get(h.concept_id)
        if c:
            alts.append(c)

    return TutorResponse(
        ok=True,
        concept=concept,
        confidence=best.confidence,
        alternatives=alts,
        ladder=lib.learning_path(concept.id),
        log_concept_id=concept.id,
    )


def explain_step(before_text: str, after_text: str) -> TutorResponse:
    """Student shows one step of their own work: 'I went from A to B'."""
    try:
        b = parse_student(before_text, structural=True)
        a = parse_student(after_text, structural=True)
    except MathInputError as exc:
        return TutorResponse(ok=False, message=str(exc))
    return _build(detect_transformation(b, a))


def explain_stuck(expr_text: str) -> TutorResponse:
    """Student sends one expression: 'I don't know what to do here'."""
    try:
        e = parse_student(expr_text, structural=True)
    except MathInputError as exc:
        return TutorResponse(ok=False, message=str(exc))
    return _build(detect_in_single(e))


def explain_question(text: str) -> TutorResponse:
    """Student asks in plain English: 'why does log of a product split up?'"""
    hits = library().search(text, limit=3)
    if not hits:
        return TutorResponse(ok=False, message=_NOT_FOUND)

    lib = library()
    concept = hits[0]
    return TutorResponse(
        ok=True,
        concept=concept,
        confidence=min(1.0, concept._score / 12.0),
        alternatives=hits[1:3],
        ladder=lib.learning_path(concept.id),
        log_concept_id=concept.id,
    )


def explain_concept_by_id(concept_id: str) -> TutorResponse:
    lib = library()
    c = lib.get(concept_id)
    if not c:
        return TutorResponse(ok=False, message=_NOT_FOUND)
    return TutorResponse(ok=True, concept=c, confidence=1.0,
                         ladder=lib.learning_path(c.id), log_concept_id=c.id)
