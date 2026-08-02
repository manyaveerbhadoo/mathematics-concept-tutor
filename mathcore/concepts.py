"""
concepts.py — the bot's teaching brain.

Loads the curated concept library and answers three questions:
  1. "Which concept is this student asking about?"          -> search()
  2. "What does that concept say?"                          -> get()
  3. "What do they need to understand FIRST?"               -> learning_path()

Question 3 is the important one. If a student is lost on factoring by
grouping, throwing more grouping at them does not help -- they are usually
missing GCF factoring underneath it. The prerequisite graph lets the bot
walk backwards to solid ground and build up from there.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_LIBRARY_PATH = Path(__file__).parent.parent / "concepts" / "library.json"


@dataclass
class Concept:
    id: str
    name: str
    topic: str
    prereqs: list
    keywords: list
    plain: str
    ask: str          # the question the bot puts back to the student FIRST
    rule: str
    why: str
    example: dict
    mistake: str
    when_stuck: str = ""        # what to do when the standard method stalls
    questions: list = field(default_factory=list)   # the Socratic ladder
    checks: list = field(default_factory=list)      # how to judge each answer
    _score: float = field(default=0.0, compare=False)


class ConceptLibrary:
    def __init__(self, path: Path = _LIBRARY_PATH):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.concepts = {}
        for entry in raw["concepts"]:
            entry = {k: v for k, v in entry.items() if not k.startswith("_")}
            c = Concept(**entry)
            self.concepts[c.id] = c
        self._validate()

    # -- integrity --------------------------------------------------------
    def _validate(self):
        """Catch broken data at startup, not in front of a student."""
        for c in self.concepts.values():
            for p in c.prereqs:
                if p not in self.concepts:
                    raise ValueError(f"'{c.id}' lists unknown prerequisite '{p}'")

        # A cycle would make learning_path() loop forever.
        state = {}

        def visit(cid, trail):
            if state.get(cid) == "done":
                return
            if state.get(cid) == "visiting":
                raise ValueError(f"Prerequisite cycle: {' -> '.join(trail + [cid])}")
            state[cid] = "visiting"
            for p in self.concepts[cid].prereqs:
                visit(p, trail + [cid])
            state[cid] = "done"

        for cid in self.concepts:
            visit(cid, [])

    # -- access -----------------------------------------------------------
    def get(self, concept_id: str) -> Optional[Concept]:
        return self.concepts.get(concept_id)

    def all_ids(self):
        return list(self.concepts)

    def by_topic(self, topic: str):
        return [c for c in self.concepts.values() if c.topic == topic]

    # -- search -----------------------------------------------------------
    def search(self, query: str, limit: int = 3):
        """Rank concepts against a student's plain-English question.

        Deliberately simple and deterministic: no AI, no network call, and
        it cannot be talked into doing something else.
        """
        q = query.lower().strip()
        words = set(re.findall(r"[a-z0-9^]+", q))
        if not words:
            return []

        results = []
        for c in self.concepts.values():
            score = 0.0

            for kw in c.keywords:
                kw_l = kw.lower()
                if kw_l in q:                      # whole phrase present
                    score += 10 + len(kw_l) * 0.1  # longer phrase = better
                else:
                    overlap = words & set(kw_l.split())
                    score += 2.0 * len(overlap)

            name_words = set(re.findall(r"[a-z0-9^]+", c.name.lower()))
            score += 3.0 * len(words & name_words)

            if c.topic.replace("-", " ") in q:
                score += 4

            if score > 0:
                c._score = score
                results.append(c)

        results.sort(key=lambda c: -c._score)
        return results[:limit]

    # -- prerequisites ----------------------------------------------------
    def learning_path(self, concept_id: str, known: set = None) -> list:
        """Ordered list of concepts to cover, foundations first.

        `known` lets a student say 'I already get GCF' so the bot skips it.
        """
        known = known or set()
        if concept_id not in self.concepts:
            return []

        ordered, seen = [], set()

        def walk(cid):
            if cid in seen or cid in known:
                return
            seen.add(cid)
            for p in self.concepts[cid].prereqs:
                walk(p)
            ordered.append(self.concepts[cid])

        walk(concept_id)
        return ordered

    def depth(self, concept_id: str) -> int:
        """How many layers of prerequisites sit under this concept."""
        c = self.concepts.get(concept_id)
        if not c or not c.prereqs:
            return 0
        return 1 + max(self.depth(p) for p in c.prereqs)


# ---------------------------------------------------------------------------
# Rendering — the bot's voice.
# ---------------------------------------------------------------------------
# Note what is NOT here: no final answers, no solving the student's problem.
# Every example uses different numbers on purpose.

def render(c: Concept, include_example: bool = True) -> str:
    out = [f"**{c.name}**", "", c.plain, "", f"**The rule:**  `{c.rule}`", "",
           f"**Why it works:** {c.why}"]

    if include_example:
        ex = c.example
        out += ["", f"**Let's try a different one:**  {ex['problem']}"]
        out += [f"  {i}. {s}" for i, s in enumerate(ex["steps"], 1)]
        if ex.get("note"):
            out += ["", f"_{ex['note']}_"]

    out += ["", f"**Watch out:** {c.mistake}"]
    return "\n".join(out)


def render_path(path: list) -> str:
    """Show a student the ladder they're about to climb."""
    if len(path) <= 1:
        return ""
    lines = ["**Here's the path to this idea:**", ""]
    for i, c in enumerate(path, 1):
        marker = "->" if i == len(path) else "  "
        lines.append(f"{marker} {i}. {c.name}")
    lines += ["", "_We'll start at the bottom. Each one makes the next easier._"]
    return "\n".join(lines)
