"""Tests for the concept library and lookup engine."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mathcore.concepts import ConceptLibrary, render, render_path

# Realistic things a confused student types, and the concept they mean.
STUDENT_QUESTIONS = [
    ("why can you split log(8*4) into two logs",   "log-product-rule"),
    ("how do I get x down from the exponent",      "solving-exponential-equations"),
    ("what does log even mean",                    "log-definition"),
    ("I don't get factoring by grouping",          "factoring-by-grouping"),
    ("how do you find the domain",                 "domain-of-rational"),
    ("why is sin^2 + cos^2 = 1",                   "pythagorean-identity"),
    ("what is x^2 - 9 factored",                   "difference-of-squares"),
    ("absolute value two cases",                   "absolute-value-equations"),
    ("can I cancel in a fraction",                 "simplify-rational"),
    ("do I add or multiply exponents",             "exponent-rules"),
]


def run():
    passed = failed = 0
    lib = ConceptLibrary()
    print(f"Library loaded and validated: {len(lib.all_ids())} concepts\n")

    print("=" * 70)
    print("TEST 1 — matching a student's plain-English question")
    print("=" * 70)
    for question, expected in STUDENT_QUESTIONS:
        hits = lib.search(question)
        got = hits[0].id if hits else None
        ok = got == expected
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  [{'PASS' if ok else 'FAIL'}] {question!r:46} -> {got}")
        if not ok:
            print(f"         expected {expected}; ranked: {[h.id for h in hits]}")

    print()
    print("=" * 70)
    print("TEST 2 — prerequisite ladders (foundations first)")
    print("=" * 70)
    for cid in ["factoring-by-grouping", "simplify-rational", "solving-exponential-equations"]:
        path = lib.learning_path(cid)
        names = " -> ".join(c.id for c in path)
        ok = path[-1].id == cid and len(path) > 1
        # every prereq must appear BEFORE the concept that needs it
        pos = {c.id: i for i, c in enumerate(path)}
        for c in path:
            for p in c.prereqs:
                if p in pos and pos[p] > pos[c.id]:
                    ok = False
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid}")
        print(f"         {names}")

    print()
    print("=" * 70)
    print("TEST 3 — 'I already know GCF' skips that rung")
    print("=" * 70)
    full = lib.learning_path("factoring-by-grouping")
    trimmed = lib.learning_path("factoring-by-grouping", known={"gcf-factoring"})
    ok = len(trimmed) < len(full) and all(c.id != "gcf-factoring" for c in trimmed)
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] full={[c.id for c in full]}")
    print(f"         trimmed={[c.id for c in trimmed]}")

    print()
    print("=" * 70)
    print("TEST 4 — content quality guardrails")
    print("=" * 70)
    for c in lib.concepts.values():
        problems = []
        if len(c.plain) < 80:
            problems.append("explanation too short")
        if not c.example.get("steps"):
            problems.append("no worked steps")
        if not c.mistake:
            problems.append("no common mistake listed")
        if not c.keywords:
            problems.append("no keywords")
        ok = not problems
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        if not ok:
            print(f"  [FAIL] {c.id}: {', '.join(problems)}")
    print(f"  checked {len(lib.concepts)} concepts for completeness")

    print()
    print("=" * 70)
    print("TEST 5 — the bot ASKS, it doesn't TELL")
    print("=" * 70)
    # The default reply is questions only. This guards the core teaching rule:
    # if someone later writes a 'question' that's really a statement handing
    # over a conclusion, this fails.
    for c in lib.concepts.values():
        problems = []
        if len(c.questions) < 3:
            problems.append(f"only {len(c.questions)} questions (need 3+)")
        asked = sum(1 for q in c.questions if q.rstrip().endswith("?"))
        if c.questions and asked / len(c.questions) < 0.5:
            problems.append(f"only {asked}/{len(c.questions)} actually ask something")
        for q in c.questions:
            low = q.lower()
            for tell in ("this means that", "so the answer is", "therefore the answer"):
                if tell in low:
                    problems.append(f"states a conclusion: '{q[:40]}...'")
        ok = not problems
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        if not ok:
            print(f"  [FAIL] {c.id}: {'; '.join(problems)}")
    total_q = sum(len(c.questions) for c in lib.concepts.values())
    print(f"  checked {len(lib.concepts)} ladders, {total_q} questions total")

    print()
    print("=" * 70)
    print("SAMPLE OUTPUT — student asks: 'I don't get factoring by grouping'")
    print("=" * 70)
    hit = lib.search("I don't get factoring by grouping")[0]
    print(render_path(lib.learning_path(hit.id)))
    print()
    print(render(hit))

    print()
    print("=" * 70)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 70)
    return failed


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
