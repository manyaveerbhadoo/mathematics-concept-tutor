"""Tests for the conversational layer.

Rules under test:
  1. A wrong answer earns a NARROWER QUESTION, never the answer itself.
  2. The bot never tells a student it "can't verify" something.
  3. A correct student is never marked wrong.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mathcore.tutor import explain_stuck, render_questions, library
from mathcore import session as convo
from mathcore import phrasing
from mathcore.session import _yes_no, _numbers_in, _stuck_signal, check

passed = failed = 0
LIB = library()


def ok(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label}  {detail}")


def hdr(t):
    print()
    print("=" * 70)
    print(t)
    print("=" * 70)


hdr("TEST 1 — reading plain-English yes/no")
# "no it isn't" must not read as agreement because "it is" sits inside "it isn't"
for text, want in [("no it isn't", False), ("yes it is", True),
                   ("it is a perfect square", True), ("it is not", False),
                   ("nope", False), ("yeah", True), ("correct", True),
                   ("dunno", None)]:
    ok(f"{text!r} -> {_yes_no(text)}", _yes_no(text) == want, f"wanted {want}")

hdr("TEST 2 — recognising a student who is lost, not answering")
for text, want in [("idk i'm stuck", True), ("no idea", True),
                   ("I don't understand", True), ("?", True),
                   ("-2 and -3", False), ("17", False)]:
    ok(f"{text!r} -> stuck={_stuck_signal(text)}", _stuck_signal(text) == want)

hdr("TEST 3 — pulling numbers out of natural phrasing")
for text, want in [("2 and 3", [2, 3]), ("b is -5, c is 6", [-5, 6]),
                   ("I got 17", [17]), ("a=2, b=3, c=-1", [2, 3, -1])]:
    got = [int(n) for n in _numbers_in(text)]
    ok(f"{text!r} -> {got}", got == want, f"wanted {want}")

hdr("TEST 4 — checking a factor pair (x^2 - 5x + 6)")
FQ = LIB.get("factoring-quadratic-simple")
V = {"b": "-5", "c": "6"}
cases = [("-2 and -3", True, "the pair"), ("1 and 6", False, "product ok, sum wrong"),
         ("2 and 3", False, "product ok, signs wrong"),
         ("-1 and -4", False, "sum ok, product wrong"), ("7 and 9", False, "neither")]
for text, want, why in cases:
    v, nudge = check(FQ, 2, text, V)
    ok(f"{text!r} -> {v}  ({why})", v == want, f"wanted {want}")

hdr("TEST 5 — a wrong answer must never contain the right one")
for text, want, _why in cases:
    v, nudge = check(FQ, 2, text, V)
    if v is False:
        leaked = "-2" in nudge and "-3" in nudge
        ok(f"nudge for {text!r} hides the answer", not leaked, nudge)

hdr("TEST 6 — discriminant and perfect square (2x^2 + 3x - 1)")
QF = LIB.get("quadratic-formula")
W = {"a": "2", "b": "3", "c": "-1"}
for text, want, why in [("17", True, "9 + 8"), ("9", False, "forgot -4ac"),
                        ("1", False, "wrong")]:
    v, _ = check(QF, 1, text, W)
    ok(f"discriminant {text!r} -> {v}  ({why})", v == want, f"wanted {want}")
# 17 is not a perfect square, so "no" is the CORRECT student answer
for text, want in [("no it isn't", True), ("nope", True), ("yes", False)]:
    v, _ = check(QF, 2, text, W)
    ok(f"perfect square? {text!r} -> {v}", v == want, f"wanted {want}")

hdr("TEST 7 — the bot never admits it can't check something")
BANNED = ["can't verify", "cannot verify", "can't check", "unable to",
          "i'm not able", "automatically"]
r = explain_stuck("x^2 - 5x + 6")
c = LIB.get(r.concept.id)
s = convo.start(99, c.id, r.values, r.expr)
rendered = render_questions(c, r.values)
transcript = [convo.first_question(s, rendered, c)]
done = False
for ans in ["b=-5 c=6", "1x6, 2x3", "-2 and -3", "(x-2)(x-3)", "yes it matches"]:
    msg, done = convo.advance(s, c, ans, rendered)
    transcript.append(msg)
    if done:
        break
whole = " ".join(transcript).lower()
for phrase in BANNED:
    ok(f"never says {phrase!r}", phrase not in whole)

hdr("TEST 8 — no mechanical 'Question 3 of 5' numbering")
ok("no 'question N of M' framing",
   "question 1 of" not in whole and "question 3 of" not in whole)
ok("conversation reached the end", done)
ok("ending credits the student", "you" in transcript[-1].lower())

hdr("TEST 9 — wrong answers hold position, right answers advance")
s2 = convo.start(100, c.id, r.values, r.expr)
for a in ["b=-5 c=6", "pairs listed"]:
    convo.advance(s2, c, a, rendered)
at = s2.q_index
msg, _ = convo.advance(s2, c, "1 and 6", rendered)
ok("wrong answer does not advance", s2.q_index == at)
ok("wrong answer still encourages",
   any(w in msg.lower() for w in ("nearly", "closer", "instinct", "good")), msg[:60])
msg, _ = convo.advance(s2, c, "-2 and -3", rendered)
ok("right answer advances", s2.q_index == at + 1)

hdr("TEST 10 — 'I'm stuck' is treated kindly, not as a wrong answer")
s3 = convo.start(101, c.id, r.values, r.expr)
msg, _ = convo.advance(s3, c, "idk i'm stuck", rendered)
ok("stays on the same question", s3.q_index == 0)
ok("responds kindly", "no problem" in msg.lower() or "normal" in msg.lower())
ok("offers the hint as an option", "/hint" in msg)

hdr("TEST 11 — concurrency: students never see each other's conversation")
convo.start(201, "gcf-factoring", {})
convo.start(202, "unit-circle", {})
convo.start(203, "law-of-sines", {})
ok("three separate sessions",
   convo.get(201).concept_id == "gcf-factoring"
   and convo.get(202).concept_id == "unit-circle"
   and convo.get(203).concept_id == "law-of-sines")
convo.end(202)
ok("ending one leaves the others",
   convo.get(202) is None and convo.get(201) is not None
   and convo.get(203) is not None)
ok("unknown user has no session", convo.get(999999) is None)

hdr("TEST 12 — the optional LLM layer fails closed")
ok("disabled without an API key", phrasing.available() is False)
ok("returns None rather than raising", phrasing.react("q", "a", True, "c") is None)

print()
print("=" * 70)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 70)
sys.exit(1 if failed else 0)
