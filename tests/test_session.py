"""Tests for the conversational layer.

The rule under test: a wrong answer earns a NARROWER QUESTION, never a
correction. If any nudge here starts handing over answers, that's a bug.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mathcore.tutor import explain_stuck, render_questions, library
from mathcore import session as convo
from mathcore.session import _yes_no, _numbers_in, check

passed = failed = 0


def ok(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label}  {detail}")


print("=" * 70)
print("TEST 1 — reading a student's plain-English yes/no")
print("=" * 70)
# "no it isn't" must not read as agreement just because "it is" is a substring.
for text, want in [("no it isn't", False), ("yes it is", True),
                   ("it is a perfect square", True), ("it is not", False),
                   ("nope", False), ("yeah", True), ("correct", True),
                   ("dunno", None)]:
    got = _yes_no(text)
    ok(f"{text!r} -> {got}", got == want, f"wanted {want}")

print()
print("=" * 70)
print("TEST 2 — pulling numbers out of however they phrased it")
print("=" * 70)
for text, want in [("2 and 3", [2, 3]), ("b is -5, c is 6", [-5, 6]),
                   ("I got 17", [17]), ("-2 and -3", [-2, -3])]:
    got = [int(n) for n in _numbers_in(text)]
    ok(f"{text!r} -> {got}", got == want, f"wanted {want}")

print()
print("=" * 70)
print("TEST 3 — checking a factor pair (x^2 - 5x + 6, so b=-5, c=6)")
print("=" * 70)
V = {"b": "-5", "c": "6"}
cases = [
    ("-2 and -3", True,  "the correct pair"),
    ("1 and 6",   False, "multiplies right, sums wrong"),
    ("2 and 3",   False, "multiplies right, sums wrong (signs)"),
    ("-1 and -4", False, "sums right, multiplies wrong"),
    ("7 and 9",   False, "neither"),
]
for text, want, why in cases:
    verdict, nudge = check("factoring-quadratic-simple", 2, text, V)
    ok(f"{text!r} -> {verdict}  ({why})", verdict == want, f"wanted {want}")

print()
print("=" * 70)
print("TEST 4 — a wrong answer must NEVER contain the right answer")
print("=" * 70)
# The correct pair is -2 and -3. No nudge may leak it.
for text, _, _ in cases:
    verdict, nudge = check("factoring-quadratic-simple", 2, text, V)
    if verdict is False:
        leaked = ("-2" in nudge and "-3" in nudge)
        ok(f"nudge for {text!r} keeps the answer hidden", not leaked, nudge)

print()
print("=" * 70)
print("TEST 5 — discriminant and perfect-square checks (2x^2 + 3x - 1)")
print("=" * 70)
W = {"a": "2", "b": "3", "c": "-1"}
for text, want, why in [("17", True, "b^2-4ac = 9+8 = 17"),
                        ("9", False, "forgot the -4ac"),
                        ("1", False, "wrong")]:
    v, _ = check("quadratic-formula", 1, text, W)
    ok(f"discriminant {text!r} -> {v}  ({why})", v == want, f"wanted {want}")

# 17 is not a perfect square, so "no" is the CORRECT student answer
for text, want in [("no it isn't", True), ("yes", False)]:
    v, _ = check("quadratic-formula", 2, text, W)
    ok(f"perfect square? {text!r} -> {v}", v == want, f"wanted {want}")

print()
print("=" * 70)
print("TEST 6 — a full conversation, wrong answer then right")
print("=" * 70)
r = explain_stuck("x^2 - 5x + 6")
c = library().get(r.concept.id)
s = convo.start(99, c.id, r.values, r.expr)
rendered = render_questions(c, r.values)

ok("starts at question 1", s.q_index == 0)
ok("uses the student's own numbers",
   "6" in rendered[1] and "-5" in rendered[2], rendered[1])

msg, done = convo.advance(s, c, "b is -5 and c is 6", rendered)
ok("unverifiable answer still advances", s.q_index == 1 and not done)

msg, done = convo.advance(s, c, "1 and 6 and 2 and 3", rendered)
ok("advances past the listing question", s.q_index == 2)

before = s.q_index
msg, done = convo.advance(s, c, "1 and 6", rendered)
ok("wrong answer does NOT advance", s.q_index == before)
ok("wrong answer re-asks the same question", "Question 3" in msg, msg[:80])
ok("wrong answer gives a nudge, not the answer",
   "Not yet" in msg and "-2" not in msg.split("Question")[0])

msg, done = convo.advance(s, c, "-2 and -3", rendered)
ok("right answer advances", s.q_index == before + 1)

while not done:
    msg, done = convo.advance(s, c, "ok", rendered)
ok("conversation reaches an end", done)
ok("ending credits the student, not the bot",
   "yourself" in msg or "without me" in msg, msg[:80])

print()
print("=" * 70)
print("TEST 7 — session lifecycle")
print("=" * 70)
convo.start(1234, "gcf-factoring", {})
ok("session is retrievable", convo.get(1234) is not None)
convo.end(1234)
ok("session ends cleanly", convo.get(1234) is None)
ok("unknown user has no session", convo.get(55555) is None)

print()
print("=" * 70)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 70)
sys.exit(1 if failed else 0)
