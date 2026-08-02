# Design notes

Why this is built the way it is. Written for anyone reading the code — including me in six months.

---

## The one constraint everything follows from

**The bot must be incapable of producing an answer.** Not discouraged from it. Incapable.

That single constraint decided almost every other choice:

- No language model in the answering path, so there's nothing to jailbreak.
- No solver, so there's no answer stored anywhere to leak.
- The bot never confirms whether a step is right or wrong at the *problem* level, so it can't be used as an oracle to test guesses against.
- Every word it can say lives in one reviewable data file.

The alternative design — compute the answer, then instruct a model not to reveal it — is a **filter**. Filters get broken, and the screenshot ends up in the class group chat. This has nothing to break.

---

## Why the parser has two modes

SymPy evaluates while it parses. `3(x+2)` becomes `3*x + 6` before you ever see it; `log_2(8)` becomes `3`.

That's fine for computing and fatal for this project, because the *shape* the student typed is exactly what identifies which concept they're using. If `before` and `after` both collapse to the same normalised form, there's no visible transformation left to detect.

```python
parse_student("3(x+2)")                    # 3*x + 6      — math mode
parse_student("3(x+2)", structural=True)   # 3*(x + 2)    — shape mode
```

Detection accuracy sat at **60%** until this was fixed, then went to **100%**. Every failure had the same root cause.

Two follow-on gotchas, both discovered the hard way:

- `evaluate=False` makes SymPy emit `Add(...)` / `Mul(...)` / `Pow(...)` calls, so those constructors must exist in the locked namespace or every parse dies with `NameError`.
- It also injects `evaluate=False` into *every* function call, so custom wrappers must accept that keyword.

## Why the parser namespace is locked

`parse_expr` calls `eval()` underneath. A student typing `__import__('os').system(...)` would otherwise run commands on the host.

Two layers: a blocklist scan, then a namespace containing only `sin`, `cos`, `log`, `sqrt`, `pi` and the handful of SymPy constructors the transformations need. No Python builtins are reachable. Four injection attempts live in the test suite.

One deliberate deviation from SymPy's defaults: `log(x)` is mapped to **base 10** and `ln(x)` to natural log, because that's the pre-calculus convention. SymPy's default would have silently marked correct student work as wrong.

---

## Why replies are questions, not explanations

A student shown a worked solution copies its shape onto their own numbers and learns nothing transferable. It *feels* like learning, which is what makes it dangerous.

So the default reply is a ladder of questions built from the student's own coefficients, and nothing else. The rule sits behind `/hint`; a worked example sits behind `/example`. A student has to consciously choose to be told, and that friction is the point.

**The rule for writing a question: never state a conclusion the student could reach.** `test_concepts.py` enforces it — every concept needs three or more questions, at least half must genuinely ask something, and any entry that hands over a conclusion fails the build. The pedagogy is version-controlled, not merely intended.

The clearest example is a quadratic that won't factor. The bot doesn't announce that. It asks the student to compute `b² − 4ac`, decide whether it's a perfect square, and say what that implies. The inference is the part worth owning, so the bot doesn't steal it.

---

## Why the conversation holds state

The first version fired five questions and stopped. A student answered question one and had nowhere to go — so they left and opened ChatGPT.

`session.py` keeps one conversation per user id, keyed so two hundred students never collide. The bot asks one thing, waits, reads the answer, checks it with SymPy where a check exists, and responds to what they actually wrote.

Two rules it never breaks:

1. **A wrong answer earns a narrower question, never a correction.** "Those two do multiply to 6 — now add them" is a nudge. "It's −2 and −3" is a solution. A test asserts that no nudge ever contains the answer it's withholding.
2. **It never says it "can't verify" something.** That phrase makes the bot sound broken and shoves the work back rudely. A student should not be able to tell which steps were verified. A test bans the phrasing.

"I don't know" is handled as its own case — a request for a smaller step, not a wrong answer.

## Why checks live in the data file

Answer checking is declared as `checks` entries parallel to `questions`, not written as Python:

```json
{"kind": "pair", "product": "c", "sum": "b"}
{"kind": "number", "value": "b**2 - 4*a*c"}
```

An instructor can see and change what counts as correct without touching code, and adding a concept doesn't mean adding a function.

---

## Why there's no LLM in the answering path

`phrasing.py` exists and is **off by default**, requiring two deliberate switches — an API key *and* an explicit opt-in — so a key present for another project can never quietly start billing through this one.

When it is on, it receives exactly three things: the question, what the student typed, and a `RIGHT`/`WRONG`/`UNKNOWN` verdict **already computed by SymPy**. It never receives the answer, never does arithmetic, and never decides correctness. It only chooses words.

That's the whole safety argument: you cannot extract from a context window what was never put in it. Any failure — missing key, timeout, suspicious output — falls straight back to templates.

---

## Privacy decisions

- Discord user ids are SHA-256 hashed with a secret salt before touching disk. Enough to tell "same person twice" from "two people once"; not enough to identify anyone.
- Student expressions are never stored. Only the concept id.
- No privileged gateway intents are requested, so the bot **cannot read message content at all** — not as policy, as capability.
- **One deliberate exception:** questions the bot fails to match are stored as raw text in a `gaps` table with *no user id at all*, not even the hashed one. It's a ranked to-do list of what to build next, written by the students the bot let down.

---

## Known limitations

- The 100% detection benchmark is measured on 45 cases written by the author. Real student input is messier. The harness exists to be re-run against real steps once the bot is in front of a class — that number will be the honest one.
- Answer checking covers the highest-traffic concepts, not all 44. Unchecked questions are accepted and the conversation moves on.
- Sessions are in-memory, so a restart ends every conversation in progress. Acceptable for a single-instance bot; would need Redis to scale horizontally.
- No image or PDF input. Handwriting OCR is unreliable, and an unreliable read means telling a *correct* student they're wrong — the worst failure available for a tool meant to build confidence.
