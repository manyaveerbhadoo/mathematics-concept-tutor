#!/usr/bin/env python3
"""
setup_check.py — run this BEFORE bot.py.

Discord's failure messages are cryptic ("Improper token", "PrivilegedIntents").
This checks everything in plain language and tells you exactly what to fix.

    python setup_check.py           checks your files and config
    python setup_check.py --live    also logs in to Discord to test the token
"""

import os
import sys
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
OK, WARN, BAD = "  [ OK ]", "  [WARN]", "  [FAIL]"
problems = []
warnings = []


def ok(msg):
    print(f"{OK} {msg}")


def bad(msg, fix):
    print(f"{BAD} {msg}")
    print(f"         -> {fix}")
    problems.append(msg)


def warn(msg, fix):
    print(f"{WARN} {msg}")
    print(f"         -> {fix}")
    warnings.append(msg)


def header(t):
    print()
    print(t)
    print("-" * 66)


# ---------------------------------------------------------------------------
header("1. Python and packages")

if sys.version_info < (3, 9):
    bad(f"Python {sys.version_info.major}.{sys.version_info.minor} is too old",
        "Install Python 3.9 or newer from python.org")
else:
    ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")

for mod, pipname in [("sympy", "sympy"), ("discord", "discord.py"),
                     ("dotenv", "python-dotenv")]:
    try:
        __import__(mod)
        ok(f"{pipname} installed")
    except ImportError:
        bad(f"{pipname} is missing",
            f"pip install -r requirements.txt")

# ---------------------------------------------------------------------------
header("2. Configuration (.env)")

env_path = HERE / ".env"
if not env_path.exists():
    bad(".env file not found",
        "Copy .env.example to .env, then fill it in:\n"
        "            copy .env.example .env        (Windows)\n"
        "            cp .env.example .env          (Mac/Linux)")
else:
    ok(".env exists")
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass

TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
SALT = os.environ.get("MATHBOT_SALT", "").strip()
GUILD = os.environ.get("DISCORD_GUILD_ID", "").strip()
INSTRUCTORS = os.environ.get("INSTRUCTOR_IDS", "").strip()

if not TOKEN or TOKEN == "paste_your_bot_token_here":
    bad("DISCORD_TOKEN is not set",
        "discord.com/developers/applications -> your app -> Bot -> Reset Token")
elif len(TOKEN) < 50:
    bad(f"DISCORD_TOKEN looks too short ({len(TOKEN)} chars)",
        "You may have copied the Application ID or Public Key by mistake. "
        "The token is a long string with two dots in it.")
elif TOKEN.count(".") < 2:
    warn("DISCORD_TOKEN doesn't have the usual two dots",
         "Double-check you copied the Bot token, not the Client Secret.")
else:
    ok(f"DISCORD_TOKEN present ({len(TOKEN)} chars, format looks right)")

if not SALT:
    bad("MATHBOT_SALT is not set — analytics logging is disabled",
        'Generate one:  python -c "import secrets; print(secrets.token_hex(32))"')
elif len(SALT) < 32:
    warn(f"MATHBOT_SALT is short ({len(SALT)} chars)",
         "Use at least 32 characters so hashes can't be brute-forced.")
else:
    ok(f"MATHBOT_SALT present ({len(SALT)} chars)")

if not GUILD:
    warn("DISCORD_GUILD_ID not set",
         "Without it, slash commands can take up to an hour to appear. "
         "Turn on Developer Mode in Discord, right-click your server, Copy Server ID.")
elif not GUILD.isdigit():
    bad("DISCORD_GUILD_ID should be digits only", f"Got: {GUILD!r}")
else:
    ok(f"DISCORD_GUILD_ID set ({GUILD})")

if INSTRUCTORS:
    badids = [i for i in INSTRUCTORS.split(",") if i.strip() and not i.strip().isdigit()]
    if badids:
        bad(f"INSTRUCTOR_IDS has non-numeric entries: {badids}",
            "Use Discord user IDs (right-click a user -> Copy User ID)")
    else:
        ok(f"INSTRUCTOR_IDS set ({len(INSTRUCTORS.split(','))} user(s))")
else:
    warn("INSTRUCTOR_IDS empty — nobody can run /report",
         "Right-click yourself in Discord -> Copy User ID, and put it here.")

# ---------------------------------------------------------------------------
header("3. Secrets are not going into git")

gi = HERE / ".gitignore"
if gi.exists() and ".env" in gi.read_text():
    ok(".env is listed in .gitignore")
else:
    bad(".env is NOT protected by .gitignore",
        "Add a line containing  .env  to .gitignore before committing anything")

try:
    tracked = subprocess.run(["git", "ls-files", ".env"], cwd=HERE,
                             capture_output=True, text=True, timeout=10)
    if tracked.stdout.strip():
        bad(".env is TRACKED BY GIT — your token may be exposed",
            "git rm --cached .env, then reset the token in the Discord portal")
    else:
        ok(".env is not tracked by git")
except Exception:
    warn("Couldn't check git status (git not installed, or not a repo yet)",
         "Fine for now — just never commit .env")

# ---------------------------------------------------------------------------
header("4. The bot's own code")

try:
    sys.path.insert(0, str(HERE))
    from mathcore.tutor import library, explain_step
    lib = library()
    ok(f"concept library loaded and validated ({len(lib.concepts)} concepts)")

    r = explain_step("x^2 - 5x + 6", "(x - 2)(x - 3)")
    if r.ok and r.concept.id == "factoring-quadratic-simple":
        ok("end-to-end check passed (detected factoring correctly)")
    else:
        bad("end-to-end check failed",
            "Run: python tests/benchmark_detect.py  to see what broke")
except Exception as exc:
    bad(f"couldn't load the bot's code: {type(exc).__name__}: {exc}",
        "Make sure you're running this from inside the math1b-bot folder")

# ---------------------------------------------------------------------------
if "--live" in sys.argv:
    header("5. Live Discord login test")
    if not TOKEN:
        bad("no token to test", "Fill in DISCORD_TOKEN first")
    else:
        try:
            import asyncio, discord

            async def probe():
                c = discord.Client(intents=discord.Intents.default())
                try:
                    await c.login(TOKEN)
                    me = c.user
                    ok(f"token works — logged in as {me} (id {me.id})")
                    return True
                except discord.LoginFailure:
                    bad("Discord rejected the token",
                        "Reset the token in the developer portal and paste the new one")
                except Exception as e:
                    bad(f"login failed: {type(e).__name__}: {e}",
                        "Check your internet connection and try again")
                finally:
                    await c.close()
                return False

            asyncio.run(probe())
        except Exception as exc:
            bad(f"couldn't run the login test: {exc}", "Skip it and try bot.py directly")
else:
    header("5. Live Discord login test")
    print("       skipped — run with --live to test your token against Discord")

# ---------------------------------------------------------------------------
print()
print("=" * 66)
if problems:
    print(f"NOT READY — {len(problems)} thing(s) to fix:")
    for p in problems:
        print(f"   - {p}")
elif warnings:
    print(f"READY TO RUN (with {len(warnings)} warning(s))")
    print("   Start the bot with:   python bot.py")
else:
    print("ALL CLEAR — start the bot with:   python bot.py")
print("=" * 66)
sys.exit(1 if problems else 0)
