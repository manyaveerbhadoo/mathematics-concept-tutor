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

    lines = [f"**Math 1B bot — last {days} days**",
             f"{total} questions from {people} students.", ""]
    if rows:
        lines.append("**Where the class is getting stuck:**")
        top = rows[0][1]
        for cid, n, students in rows[:10]:
            bar = "#" * max(1, round(12 * n / top))
            lines.append(f"  {bar:<12} {n:>3}  ({students} students)  {cid}")
    if unknown:
        lines += ["", f"_{unknown} questions couldn't be matched to a concept "
                      f"-- worth reading; they may be gaps in the library._"]
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
