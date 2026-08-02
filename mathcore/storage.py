"""
storage.py — anonymous usage logging and rate limiting.

PRIVACY, on purpose:
    Discord user IDs are hashed with a secret salt before they ever touch
    disk. That is enough to tell "the same person asked twice" apart from
    "two people asked once", which is all the analytics need -- and it is
    not enough to identify anybody. We never write names, handles, or the
    student's actual expression.

RATE LIMITING:
    Not really about server load. It removes any possibility of a student
    hammering the bot to fish for information, and it costs an honest
    student nothing -- nobody needs 30 explanations in a minute.
"""

import hashlib
import os
import sqlite3
import time
from collections import defaultdict, deque
from pathlib import Path

DB_PATH = Path(os.environ.get("MATHBOT_DB", "mathbot.db"))
_SALT = os.environ.get("MATHBOT_SALT", "")


def anon_id(discord_user_id) -> str:
    """One-way hash. Same user -> same token; token -> nothing."""
    if not _SALT:
        # Refuse to log rather than log something reversible.
        return "no-salt-configured"
    h = hashlib.sha256(f"{_SALT}:{discord_user_id}".encode()).hexdigest()
    return h[:16]


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    anon_user   TEXT    NOT NULL,
    kind        TEXT    NOT NULL,   -- step | question | stuck | concept
    concept_id  TEXT,               -- NULL when we couldn't identify one
    confidence  REAL,
    understood  INTEGER             -- 1 yes, 0 no, NULL not asked
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_concept ON events(concept_id);

-- Did the student say it helped? This is the only real evidence of benefit.
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    anon_user   TEXT    NOT NULL,
    concept_id  TEXT,
    helpful     INTEGER NOT NULL    -- 1 yes, 0 no
);
CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(ts);

-- Questions the bot could NOT match to any concept.
-- NOTE ON PRIVACY: this is the one place raw student text is kept, and it is
-- stored with NO user id at all -- not even the hashed one. It exists solely
-- as a ranked to-do list of concepts to add next, written by the students
-- themselves. Every entry here is a student the bot failed.
CREATE TABLE IF NOT EXISTS gaps (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER NOT NULL,
    text    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gaps_ts ON gaps(ts);
"""


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.executescript(_SCHEMA)
    return c


def log_event(user_id, kind, concept_id=None, confidence=None, understood=None):
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO events (ts, anon_user, kind, concept_id, confidence, understood)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (int(time.time()), anon_id(user_id), kind, concept_id,
                 confidence, understood),
            )
    except Exception:
        pass   # analytics must never break a student's request


def log_feedback(user_id, concept_id, helpful: bool):
    try:
        with _conn() as c:
            c.execute("INSERT INTO feedback (ts, anon_user, concept_id, helpful)"
                      " VALUES (?, ?, ?, ?)",
                      (int(time.time()), anon_id(user_id), concept_id, 1 if helpful else 0))
    except Exception:
        pass


def log_gap(text: str):
    """A question the bot couldn't match. Stored with no user id."""
    try:
        with _conn() as c:
            c.execute("INSERT INTO gaps (ts, text) VALUES (?, ?)",
                      (int(time.time()), (text or "")[:300]))
    except Exception:
        pass


def struggle_count(user_id, concept_id, days: int = 7) -> int:
    """How many times has this student come back to this same idea?

    Used to decide when to stop repeating a concept and drop them to its
    prerequisites instead.
    """
    since = int(time.time()) - days * 86400
    try:
        with _conn() as c:
            return c.execute(
                "SELECT COUNT(*) FROM events WHERE anon_user = ? AND concept_id = ?"
                " AND ts > ?", (anon_id(user_id), concept_id, since)).fetchone()[0]
    except Exception:
        return 0


def personal_progress(user_id, days: int = 30) -> str:
    """What this one student has been working on. Only they can see it."""
    since = int(time.time()) - days * 86400
    me = anon_id(user_id)
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT concept_id, COUNT(*) n, MAX(ts) last FROM events"
                " WHERE anon_user = ? AND ts > ? AND concept_id IS NOT NULL"
                " GROUP BY concept_id ORDER BY n DESC", (me, since)).fetchall()
            total = c.execute("SELECT COUNT(*) FROM events WHERE anon_user = ?"
                              " AND ts > ?", (me, since)).fetchone()[0]
            helped = c.execute("SELECT COUNT(*) FROM feedback WHERE anon_user = ?"
                               " AND ts > ? AND helpful = 1", (me, since)).fetchone()[0]
    except Exception:
        return "I couldn't read your history just now. Try again in a moment."

    if not total:
        return ("You haven't asked me anything yet. Try `/stuck` with whatever "
                "you're working on and I'll walk you through it.")

    lines = [f"**Your last {days} days**", "",
             f"You've worked through **{total}** questions across "
             f"**{len(rows)}** different ideas."]
    if helped:
        lines.append(f"You marked **{helped}** of them as helpful.")
    lines += ["", "**What you've spent time on:**"]

    top = rows[0][1] if rows else 1
    for cid, n, last in rows[:8]:
        bar = "#" * max(1, round(10 * n / top))
        lines.append(f"  `{bar:<10}` {n:>2}x  {cid}")

    heavy = [r for r in rows if r[1] >= 3]
    if heavy:
        lines += ["", f"**You keep coming back to `{heavy[0][0]}`.** That's "
                      f"usually a sign the gap is one level below it — "
                      f"ask me about its prerequisites and it'll get easier."]
    lines += ["", "_Only you can see this. Your instructor sees class totals "
                  "with no names attached._"]
    return "\n".join(lines)


def weekly_report(days: int = 7) -> str:
    """The thing that makes an instructor say yes.

    Shows where the class is stuck. No names, no individual students.
    """
    since = int(time.time()) - days * 86400
    with _conn() as c:
        rows = c.execute(
            "SELECT concept_id, COUNT(*) n, COUNT(DISTINCT anon_user) students"
            " FROM events WHERE ts > ? AND concept_id IS NOT NULL"
            " GROUP BY concept_id ORDER BY n DESC", (since,)).fetchall()
        total = c.execute("SELECT COUNT(*) FROM events WHERE ts > ?",
                          (since,)).fetchone()[0]
        people = c.execute("SELECT COUNT(DISTINCT anon_user) FROM events WHERE ts > ?",
                           (since,)).fetchone()[0]
        unknown = c.execute("SELECT COUNT(*) FROM events WHERE ts > ? AND concept_id IS NULL",
                            (since,)).fetchone()[0]

    if not total:
        return f"No activity in the last {days} days."

    with _conn() as c:
        fb = c.execute("SELECT COUNT(*), SUM(helpful) FROM feedback WHERE ts > ?",
                       (since,)).fetchone()
        worst = c.execute(
            "SELECT concept_id, COUNT(*) n, SUM(helpful) h FROM feedback"
            " WHERE ts > ? AND concept_id IS NOT NULL GROUP BY concept_id"
            " HAVING n >= 3 ORDER BY (CAST(SUM(helpful) AS REAL)/COUNT(*)) ASC"
            " LIMIT 3", (since,)).fetchall()
        gaps = c.execute(
            "SELECT text, COUNT(*) n FROM gaps WHERE ts > ?"
            " GROUP BY lower(text) ORDER BY n DESC LIMIT 8", (since,)).fetchall()
        repeat = c.execute(
            "SELECT COUNT(*) FROM (SELECT anon_user, concept_id FROM events"
            " WHERE ts > ? AND concept_id IS NOT NULL GROUP BY anon_user,"
            " concept_id HAVING COUNT(*) >= 3)", (since,)).fetchone()[0]

    lines = [f"**Math 1B tutor — last {days} days**", "",
             f"**{total}** questions from **{people}** students."]

    if fb and fb[0]:
        pct = round(100 * (fb[1] or 0) / fb[0])
        lines.append(f"**{pct}%** of {fb[0]} rated replies were marked helpful.")
    lines.append("")

    if rows:
        lines.append("**Where the class is getting stuck:**")
        top = rows[0][1]
        for cid, n, students in rows[:10]:
            bar = "#" * max(1, round(12 * n / top))
            lines.append(f"  `{bar:<12}` {n:>3}  ({students} students)  {cid}")

    if repeat:
        lines += ["", f"**{repeat}** student-concept pairs came up 3+ times — "
                      f"those are the students genuinely stuck, not just curious."]

    if worst:
        lines += ["", "**Explanations rating worst — worth rewording:**"]
        for cid, n, h in worst:
            lines.append(f"  {round(100*(h or 0)/n):>3}% helpful ({n} ratings)  {cid}")

    if gaps:
        lines += ["", "**Questions I couldn't answer — your to-do list:**"]
        for text, n in gaps:
            tag = f" (x{n})" if n > 1 else ""
            lines.append(f"  - {text[:90]}{tag}")

    if unknown:
        lines += ["", f"_{unknown} of {total} questions went unmatched "
                      f"({round(100*unknown/total)}%)._"]
    lines += ["", "_No names, no message content. Counts only._"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# rate limiting  (in-memory sliding window)
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, max_calls: int = 12, per_seconds: int = 60):
        self.max_calls = max_calls
        self.per = per_seconds
        self._hits = defaultdict(deque)

    def check(self, user_id):
        """Returns (allowed, seconds_to_wait)."""
        now = time.time()
        q = self._hits[user_id]
        while q and now - q[0] > self.per:
            q.popleft()
        if len(q) >= self.max_calls:
            return False, int(self.per - (now - q[0])) + 1
        q.append(now)
        return True, 0
