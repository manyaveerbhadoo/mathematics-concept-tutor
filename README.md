# Mathematics Concept Tutor

[![tests](https://github.com/manyaveerbhadoo/mathematics-concept-tutor/actions/workflows/tests.yml/badge.svg)](https://github.com/manyaveerbhadoo/mathematics-concept-tutor/actions/workflows/tests.yml)

**A Discord tutor that refuses to give answers — and asks the questions that make a student find their own.**

Built for UCI **MATH 1B (Pre-Calculus II)** by Manyaveer Bhadoo, Learning Assistant, Fall 2026.

---

## The idea

Most homework help produces memorisers. A student sees a worked solution, copies the shape onto their own numbers, and gets the answer without ever doing the reasoning. It feels like learning. It isn't — the next unfamiliar problem puts them right back where they started.

This bot is built to produce the opposite. **It never states a conclusion the student could reach on their own.** Every reply is a ladder of questions, built from the student's own coefficients, that walks them toward the answer without ever handing it over.

The point isn't to get the problem done. It's that the student ends up able to do the next one alone.

---

## What a student actually sees

They send a step they're stuck on:

```
/step   before: x^2 - 5x + 6    after: (x - 2)(x - 3)
```

The bot works out which concept is in play and replies with **questions only**:

> **This is: Factoring x² + bx + c**
>
> Work through these in order. Don't skip ahead — each one sets up the next.
>
> **1)** In `x^2 - 5x + 6`, what is your b (the middle number) and your c (the last one)?
> **2)** Write down every pair of whole numbers that multiplies to give 6. All of them.
> **3)** Which of those pairs adds up to -5?
> **4)** If none of them do — what do you think that tells you about this quadratic?
> **5)** If you found a pair: multiply your factors back out. Does it match the original?

No rule. No worked example. No answer. Just the sequence of thinking, with their numbers in it.

### It won't let them waste time either

Send a quadratic that doesn't factor and the bot doesn't announce that — it makes them establish it:

> **1)** For `2x^2 + 3x - 1`, write down a, b and c.
> **2)** Work out b² − 4ac on its own. What number do you get?
> **3)** Is that number a perfect square? Check it.
> **4)** What do you think your answer to that tells you about whether this factors into whole numbers?
> **5)** Now substitute a, b and c into the formula.

The student computes 17, sees it isn't a perfect square, and draws the conclusion themselves. That inference is the thing worth owning — so the bot doesn't steal it.

---

## Three tiers, each one opt-in

| Tier | Command | What it gives |
|---|---|---|
| **1. Questions** | `/step`, `/stuck`, `/ask` | The ladder. This is the default and usually the end of it. |
| **2. The rule** | `/hint <concept>` | The formula, why it's valid, the usual trap. Prefaced *"only worth reading once you've had a real go."* |
| **3. Worked example** | `/example <concept>` | A full solution with **different numbers**, ending with *"now go do yours yourself."* |

A student has to consciously choose to be told. That friction is deliberate — the moment before you're given the answer is the moment you actually learn something.

### It's a conversation, not a leaflet

The bot asks **one question at a time**, waits, and reads the answer:

> **Q3:** Which of those pairs adds up to −5?
>
> `/reply 1 and 6`
>
> **Not yet.** Your product is right — those two do multiply to 6. Now add them. Is that the middle coefficient you need? What does that tell you about the signs?

SymPy checks the answer where it can. A wrong answer earns a **narrower question**, never a correction — and the correct pair is never named. A test enforces that: no nudge may contain the answer it's withholding.

### All commands

| Command | For |
|---|---|
| `/stuck expression` | "I don't know what to do here" — starts the guided ladder |
| `/step before after` | "I did this — what idea is that?" |
| `/ask question` | Plain English: *"why can I split a log of a product?"* |
| `/reply answer` | Answers the question the bot just asked |
| `/hint concept` | The rule behind it |
| `/example concept` | One worked through |
| `/progress` | Your own history — private to you |
| `/concepts` | Everything the bot knows |
| `/report` | Instructor only — class digest, gaps, worst-rated explanations |

### It adapts when someone is stuck

Come back to the same idea three times in a week and the bot stops repeating itself:

> *You've come back to **Solving Trigonometric Equations** a few times this week. Let's drop one level — **Reference Angles** is what it's built on, and it usually turns out to be the real gap.*

Students who are lost are usually lost one level below where they think they are.

---

## Why it can't be used to cheat

**The bot has no capacity to produce an answer.** That's architectural, not a filter.

It identifies which *concept* a step uses by matching the structural shape of the expression, then reads pre-written questions out of a file. It never solves, never simplifies toward a result, and never says whether a step was right or wrong.

Filters get jailbroken. Architecture doesn't. There is no "ignore previous instructions" here — there's no answer stored anywhere to leak, and no language model generating one.

- Can't do homework, so there's nothing to gain by trying.
- Can't be used as an oracle to test guesses against, because it never confirms anything.
- Every word it can say lives in `concepts/library.json`, which an instructor can read end to end in ten minutes.

---

## Setup

```bash
git clone https://github.com/manyaveerbhadoo/mathematics-concept-tutor
cd mathematics-concept-tutor
pip install -r requirements.txt
```

**Try it with no Discord account at all:**

```bash
python try_it.py --demo     # canned conversations
python try_it.py            # interactive
```

**Then create the bot:** [discord.com/developers/applications](https://discord.com/developers/applications) → New Application → **Bot** → Reset Token. Under **OAuth2 → URL Generator**, tick scopes `bot` and `applications.commands`, permission `Send Messages`, and open the generated URL to invite it.

No privileged gateway intents are needed — the bot uses slash commands only and never reads message content.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # for MATHBOT_SALT
python setup_check.py --live     # validates everything, tests your token
python bot.py
```

`setup_check.py` checks your Python version, packages, every `.env` field, that `.env` isn't tracked by git, that the concept library loads, that detection works end to end — then logs in to Discord to prove the token is real. Every failure comes with the exact command to fix it.

---

## How it's put together

```
bot.py                 Discord only. No math, no teaching logic.
try_it.py              Terminal version — test everything without Discord.
setup_check.py         Preflight validation.

mathcore/
  parser.py            Student text -> SymPy. Two modes (see below).
  session.py           The conversation: state, answer checking, nudges.
  detect.py            Which concept does this step use?
  concepts.py          Loads the library; walks prerequisite chains.
  tutor.py             Decides what to actually say.
  storage.py           Anonymous logging + rate limiting.

  phrasing.py          Optional LLM layer. Off by default. Never sees answers.

concepts/library.json  Every word the bot can say. Plain data.

tests/
  test_parser.py       27 tests: messy input, malformed input, injection
  test_concepts.py     102 tests: matching, prerequisites, content, teaching rule
  test_session.py      39 tests: answer checking, the no-answer-leak rule
  benchmark_detect.py  45 labeled student steps — accuracy measurement
```

### The two parser modes

SymPy simplifies as it parses: `3(x+2)` becomes `3x+6` instantly and `log_2(8)` becomes `3`. Fine for computing, fatal here — it destroys the *shape* the student typed, and the shape is what identifies the concept.

```python
parse_student("3(x+2)")                    # -> 3*x + 6      (math mode)
parse_student("3(x+2)", structural=True)   # -> 3*(x + 2)    (shape mode)
```

Getting this wrong held detection accuracy at 60%. Fixing it took it to 100%.

### Parser safety

SymPy's parser calls `eval()` underneath. Two layers guard it: a blocklist scan, and a locked namespace where the only reachable names are `sin`, `cos`, `log`, `sqrt`, `pi` and friends — no Python builtins. Four injection attempts are in the test suite.

---

## Adding a concept

Append an entry to `concepts/library.json`. No code:

```json
{
  "id": "completing-the-square",
  "name": "Completing the Square",
  "topic": "polynomials",
  "prereqs": ["distributive-property"],
  "keywords": ["complete the square", "perfect square trinomial"],
  "questions": [
    "In {expr}, what is the coefficient of your x term?",
    "Halve it, then square that. What do you get?",
    "What happens to the expression's value if you add that number? How do you compensate?"
  ],
  "plain": "…",  "rule": "…",  "why": "…",  "mistake": "…",
  "when_stuck": "…",
  "example": { "problem": "use DIFFERENT numbers", "steps": ["…"] }
}
```

`{expr}`, `{b}`, `{c}`, `{terms}`, `{den}` and friends are filled with the student's own values; anything that can't be worked out falls back to a readable generic phrase.

**The one rule for writing questions:** never state a conclusion the student could reach. `test_concepts.py` enforces it — every concept needs 3+ questions, at least half must actually ask something, and any that hands over a conclusion fails the build.

The library validates itself at startup too: unknown prerequisites and circular chains raise immediately rather than failing in front of a student.

---

## Running costs

**Zero.** Discord bots are free, SymPy is open source, and the bot runs on your
own machine. There is no paid service in the default path.

`phrasing.py` can optionally call a language model for warmer replies, but it
requires **two** deliberate switches — an `ANTHROPIC_API_KEY` *and*
`MATHBOT_LLM=1`. With either missing it never makes a network call. An API key
sitting in your environment for some other project cannot quietly start
billing through this one.

---

## Privacy

- Discord user IDs are **SHA-256 hashed with a secret salt** before touching disk. The bot can tell "same person twice" from "two people once" — nothing more.
- Student expressions are **never stored**. Only the concept ID.
- No names, no handles, no message content.
- `/report` shows aggregate counts only, and only to IDs in `INSTRUCTOR_IDS`.
- `/progress` is visible only to the student who runs it, and is sent ephemerally.
- **One exception, deliberately made:** questions the bot fails to match are stored
  as raw text in a `gaps` table with **no user id at all** — not even the hashed one.
  It exists purely as a ranked to-do list of concepts to add next, written by the
  students the bot let down.

The weekly digest tells an instructor where the class is stuck — *"47 questions about log properties this week"* — in time to act on it, rather than finding out at the midterm.

---

## Current state

| Test suite | Result |
|---|---|
| Parser — messy input, malformed input, injection | 27/27 |
| Concept library — matching, prerequisites, content, teaching rule | 102/102 |
| Conversation — answer checking, no-answer-leak rule, session flow | 39/39 |
| Detector benchmark — 45 labeled steps | 100% top-1 |

**44 concepts, 180 questions**, covering all 29 lectures of the
[UCI Math 1B department syllabus](https://www.math.uci.edu/sites/math.uci.edu/files/syllabus/lower_division/1B_syllabus.pdf)
— linear and absolute-value equations, quadratics, functions and transformations,
polynomial division, inverses, exponentials and logarithms, the unit circle,
right-triangle and inverse trig, identities, trig equations, and the laws of
sines and cosines.

**Stated plainly:** 100% is measured on cases written by the author. Real student input is messier. The benchmark exists to be re-run against real steps once the bot is in front of a class — that number will be the honest one.

## Before deploying to a real class

- [ ] Written approval from the Math 1B instructor
- [ ] Full syllabus coverage (completing the square, unit circle, inverse functions, graph transformations)
- [ ] Test with students who aren't in the course
- [ ] Re-run the benchmark against real student steps and record the number
- [ ] Confirm `.env` was never committed: `git log --all --full-history -- .env`
