# Math 1B Concept Tutor

A Discord bot for UCI **MATH 1B (Pre-Calculus II)** that explains the *idea* behind a step a student is stuck on — and never gives away an answer.

Built by Manyaveer Bhadoo, Learning Assistant, Fall 2026.

---

## What it does

A student sends a step from their own work:

```
/step  before: x^2 - 5x + 6   after: (x - 2)(x - 3)
```

The bot replies:

> **The idea here is: Factoring x² + bx + c**
>
> **Before I explain — have a go at this:**
> > What two numbers multiply to your last term and add to your middle one?
>
> *…plain explanation, the rule, why it works, a fully worked example **using different numbers**, and the mistake students usually make.*
>
> *This one builds on: The Distributive Property → Factoring Out the GCF.*

### Commands

| Command | For |
|---|---|
| `/step before after` | "I did this — what idea is that?" |
| `/ask question` | Plain English: *"why can I split a log of a product?"* |
| `/stuck expression` | "I don't know what to do here." |
| `/concepts` | Everything the bot knows |
| `/report` | Instructor only — anonymous weekly digest |

---

## The design rule that makes it safe

**The bot has no capacity to produce an answer.** This is architectural, not a filter.

It identifies which *concept* a step uses by looking at the structural shape of the expression, then reads a pre-written explanation out of a file. It never solves, never simplifies toward a result, and never says whether the student's step was right or wrong.

That matters because filters get jailbroken and architecture doesn't. There is no "ignore previous instructions" here — there is no answer stored anywhere to leak, and no model generating one.

Consequences:

- Can't be used to do homework, so there's nothing to gain by trying.
- Can't be used as an oracle to guess answers against, because it never confirms anything.
- Every word it can say is in `concepts/library.json`, which an instructor can read end to end in ten minutes.

---

## Setup

**1. Install**

```bash
git clone <your-repo-url>
cd math1b-bot
pip install -r requirements.txt
```

**2. Try it with no Discord account at all**

```bash
python3 try_it.py --demo     # canned conversations
python3 try_it.py            # interactive
```

**3. Create the Discord bot**

- Go to <https://discord.com/developers/applications> → **New Application**
- **Bot** → **Reset Token** → copy it
- **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; permissions `Send Messages`, `Use Slash Commands`
- Open the generated URL to invite the bot to a server you own

**4. Configure**

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # for MATHBOT_SALT
```

Fill in `.env`. **Never commit it** — it's already in `.gitignore`. If a token leaks, reset it in the developer portal immediately.

**5. Run**

```bash
python3 bot.py
```

---

## How it's put together

```
bot.py                 Discord only. No math, no teaching logic.
try_it.py              Terminal version — test everything without Discord.

mathcore/
  parser.py            Student text -> SymPy. Two modes (see below).
  detect.py            Which concept does this step use?
  concepts.py          Loads the library; walks prerequisite chains.
  tutor.py             Decides what to actually say.
  storage.py           Anonymous logging + rate limiting.

concepts/library.json  Everything the bot can say. Plain data.

tests/
  test_parser.py       27 tests: messy input, broken input, injection attempts
  test_concepts.py     29 tests: matching, prerequisite ordering, content quality
  benchmark_detect.py  45 labeled student steps — accuracy measurement
```

Run everything:

```bash
python3 tests/test_parser.py && python3 tests/test_concepts.py && python3 tests/benchmark_detect.py
```

### The two parser modes

SymPy simplifies as it parses: `3(x+2)` becomes `3x+6` instantly, and `log_2(8)` becomes `3`. That's fine for computing, but it destroys the *shape* the student typed — and the shape is exactly what tells us which idea they used.

```python
parse_student("3(x+2)")                    # -> 3*x + 6      (math mode)
parse_student("3(x+2)", structural=True)   # -> 3*(x + 2)    (shape mode)
```

The detector uses shape mode. Getting this wrong held detection accuracy at 60%; fixing it took it to 100%.

### Safety in the parser

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
  "plain": "Beginner-level explanation...",
  "ask": "The question to put back to the student first",
  "rule": "The formal statement",
  "why": "Why this is allowed",
  "example": {
    "problem": "Use DIFFERENT numbers than any homework",
    "steps": ["...", "..."],
    "note": "optional"
  },
  "mistake": "The trap students fall into"
}
```

The library validates itself on startup: unknown prerequisites and circular chains raise an error immediately rather than failing in front of a student. `tests/test_concepts.py` enforces that every entry has a worked example, a listed mistake, and a real explanation.

**One content rule:** examples must use different numbers than anything on a problem set. Otherwise the bot accidentally hands over an answer.

---

## Privacy

- Discord user IDs are **SHA-256 hashed with a secret salt** before touching disk. The bot can tell "same person twice" from "two people once" — nothing more.
- Student expressions are **never stored**. Only the concept ID.
- No names, no handles, no message content.
- `/report` shows aggregate counts only, and only to IDs listed in `INSTRUCTOR_IDS`.

---

## Current state

| Test suite | Result |
|---|---|
| Parser (messy input, malformed input, injection) | 27/27 |
| Concept library (matching, prerequisites, content) | 29/29 |
| Detector benchmark, 45 labeled steps | 100% top-1 |

**Caveat worth stating plainly:** 100% is measured on cases written by the author. Real student input is messier. The benchmark exists to be re-run against real steps once the bot is in front of a class — that number is the honest one.

## Before deploying to a real class

- [ ] Get written approval from the Math 1B instructor
- [ ] Expand the library to full syllabus coverage (completing the square, unit circle, inverse functions, graph transformations)
- [ ] Test with 5–10 students who aren't in the course
- [ ] Re-run the benchmark against real student steps and record the number
- [ ] Confirm `.env` is not in git history: `git log --all --full-history -- .env`
