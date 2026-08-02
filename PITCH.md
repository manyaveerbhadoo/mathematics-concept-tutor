# A Concept Tutor for Math 1B

**Manyaveer Bhadoo — Learning Assistant, Fall 2026**

---

## The short version

I built a Discord bot for Math 1B that answers a student's question **with questions** — a sequence that walks them to the answer without ever giving it. It is architecturally incapable of producing a solution, and I would not put it in front of students without your approval.

The aim is to build problem-solvers rather than memorisers. A student who is shown a worked solution copies its shape onto their own numbers and learns nothing transferable. A student who is asked the right five questions in the right order has actually done the reasoning, and can do the next one alone.

---

## What a student sees

A student sends a step from their own work — say they're stuck factoring `x² − 5x + 6`. The bot identifies the concept and replies with **questions only**:

> **This is: Factoring x² + bx + c**
>
> **1)** In `x² − 5x + 6`, what is your b and your c?
> **2)** Write down every pair of whole numbers that multiplies to give 6. All of them.
> **3)** Which of those pairs adds up to −5?
> **4)** If none of them do — what do you think that tells you about this quadratic?
> **5)** If you found a pair: multiply your factors back out. Does it match?

No rule, no explanation, no answer. The questions use the student's own coefficients, so they can't be skimmed past.

**The rule sits behind `/hint`, and a worked example behind `/example`** — both opt-in, both prefaced with "only once you've had a real go." A student has to consciously choose to be told, and that friction is the point.

**Where it won't let them waste effort:** send a quadratic that doesn't factor, and the bot doesn't announce that. It asks them to compute b² − 4ac, check whether it's a perfect square, and say what that implies. The student draws the inference — which is the part worth owning.

**And it diagnoses downward.** If someone is stuck on factoring by grouping, the bot shows that grouping sits on GCF factoring, which sits on the distributive property, and offers to start at the bottom. Students who are lost are usually lost one or two levels below where they think they are.

---

## Why it cannot be used to cheat

This was the first design constraint, not an afterthought.

**The bot never computes an answer.** It reads the structural shape of what a student typed, matches it to a concept, and prints a pre-written explanation from a file. There is no solver in the system. There is no language model generating text. There is nothing to extract, because nothing is generated.

Three consequences:

- It **cannot** produce a solution to a homework problem, in any phrasing, under any prompt.
- It **cannot** be used to check guessed answers — it never says whether a step is right or wrong. Only what idea it uses.
- Every worked example uses **different numbers** from any problem set, by rule — and is only reachable by explicitly asking for it.

A test in the suite enforces the teaching rule directly: every concept must have at least three questions, at least half must genuinely ask something, and any entry that hands over a conclusion fails the build. The pedagogy is version-controlled, not just intended.

I'd contrast this with the obvious alternative: a bot that computes the answer and is *instructed* not to reveal it. That's a filter, and filters get broken — students would have a screenshot of it failing within a week. This has nothing to break.

---

## What it gives you

The bot keeps an anonymous log of which concepts students ask about, and produces a weekly digest:

```
Math 1B bot — last 7 days
143 questions from 61 students.

Where the class is getting stuck:
  ############   47  (31 students)  factoring-quadratic-simple
  ########       28  (22 students)  log-product-rule
  ####           14  (11 students)  domain-of-rational
```

You'd know before Wednesday's lecture that a third of the class is stuck on log properties. Right now that information arrives with the midterm.

**On privacy:** Discord IDs are one-way hashed with a secret salt before anything is written. The system can tell repeat visits apart from distinct students, and that's all. No names, no handles, and student expressions are never stored — only the concept ID.

---

## You control what it says

Everything the bot is capable of saying lives in a single plain-text file, `concepts/library.json`. It is data, not code. You can read all of it in about ten minutes, correct any wording you disagree with, delete an entry, or add your own — without touching any programming.

I'd rather you edit it than approve it as-is.

---

## Where it stands

It's built and tested: 56 passing tests covering input handling, content completeness, and security, plus a 45-case benchmark for concept identification accuracy. It runs, and I can demo it in about two minutes.

It covers 15 concepts right now — the core of factoring, logarithms, exponents, rational functions, trig identities, and absolute value. Full syllabus coverage is straightforward once I know what you emphasize.

---

## What I'm asking

1. **Ten minutes** to demo it and hear what you'd change.
2. **A look at the concept library** — tell me what's worded badly or explained wrong.
3. **Your decision** on whether it goes in front of students, and under what conditions.

I have not shared this with any Math 1B student and won't until you say so.

If the answer is no, that's completely fine — I learned an enormous amount building it and it was worth doing regardless.
