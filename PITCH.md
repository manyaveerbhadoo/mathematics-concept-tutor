# A Concept Tutor for Math 1B

**Manyaveer Bhadoo — Learning Assistant, Fall 2026**

---

## The short version

I built a Discord bot for Math 1B that explains the *concept* behind a step a student is stuck on. It is architecturally incapable of solving a problem or producing an answer, and I would not put it in front of students without your approval.

---

## What a student sees

A student sends a step from their own work — say they went from `x² − 5x + 6` to `(x − 2)(x − 3)` and don't understand why that works. The bot identifies the underlying idea and responds with:

1. **The name of the concept** — "Factoring x² + bx + c"
2. **A question back to them** — *"What two numbers multiply to your last term and add to your middle one?"* The bot asks before it tells.
3. **A plain-language explanation**, written for a beginner
4. **The rule, and why the rule is true**
5. **A fully worked example using different numbers**
6. **The mistake students usually make here**
7. **The prerequisites underneath it**, if there are any

That last point is the part I care most about. If a student is stuck on factoring by grouping, the bot doesn't explain grouping louder — it shows them that grouping sits on top of GCF factoring, which sits on the distributive property, and offers to start at the bottom. Students who are lost are usually lost one or two levels below where they think they are.

---

## Why it cannot be used to cheat

This was the first design constraint, not an afterthought.

**The bot never computes an answer.** It reads the structural shape of what a student typed, matches it to a concept, and prints a pre-written explanation from a file. There is no solver in the system. There is no language model generating text. There is nothing to extract, because nothing is generated.

Three consequences:

- It **cannot** produce a solution to a homework problem, in any phrasing, under any prompt.
- It **cannot** be used to check guessed answers — it never says whether a step is right or wrong. Only what idea it uses.
- Every worked example uses **different numbers** from any problem set, by rule.

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
