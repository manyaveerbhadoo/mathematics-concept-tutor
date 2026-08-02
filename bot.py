#!/usr/bin/env python3
"""
bot.py — the Discord layer.

Contains NO teaching logic and NO math. It receives commands, hands them to
mathcore, and posts what comes back. Everything the bot can say lives in
concepts/library.json.

Student commands
    /stuck     paste where you're stuck -> a guided ladder of questions
    /step      show a step you took -> the idea behind it
    /ask       a plain-English question
    /reply     answer the question the bot just asked
    /hint      the rule behind it (only after you've tried)
    /example   one worked through with different numbers
    /concepts  everything the bot knows
    /progress  your own history, private to you

Instructor
    /report    anonymous class digest, gaps, and worst-rated explanations

No privileged gateway intents. The bot cannot read message content at all.
"""

import os
import logging

import discord
from discord import app_commands
from dotenv import load_dotenv

from mathcore.tutor import (explain_step, explain_question, explain_stuck,
                            explain_concept_by_id, render_questions, library)
from mathcore import session as convo
from mathcore.storage import (log_event, log_feedback, log_gap, weekly_report,
                              personal_progress, struggle_count, RateLimiter)

load_dotenv()

TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
INSTRUCTOR_IDS = {s.strip() for s in os.environ.get("INSTRUCTOR_IDS", "").split(",") if s.strip()}

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("mathbot")

limiter = RateLimiter(max_calls=25, per_seconds=60)   # a conversation needs headroom

intents = discord.Intents.default()          # no message content intent
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DISCORD_LIMIT = 1900


def _chunk(text: str):
    if len(text) <= DISCORD_LIMIT:
        return [text]
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > DISCORD_LIMIT:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


# ---------------------------------------------------------------------------
# feedback buttons — the only evidence of benefit we'll ever have
# ---------------------------------------------------------------------------

class Feedback(discord.ui.View):
    def __init__(self, concept_id: str):
        super().__init__(timeout=1800)
        self.concept_id = concept_id

    @discord.ui.button(label="This helped", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, _b: discord.ui.Button):
        log_feedback(interaction.user.id, self.concept_id, True)
        await interaction.response.send_message(
            "Good — that's the bit I can't measure any other way. Thanks.",
            ephemeral=True)

    @discord.ui.button(label="Still confused", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, _b: discord.ui.Button):
        log_feedback(interaction.user.id, self.concept_id, False)
        await interaction.response.send_message(
            f"Noted, and that's useful — it tells me this explanation needs "
            f"rewriting.\n\nTry `/hint {self.concept_id}` for the rule, or ask "
            f"me about what sits underneath it.", ephemeral=True)

    @discord.ui.button(label="Start over", style=discord.ButtonStyle.secondary)
    async def restart(self, interaction: discord.Interaction, _b: discord.ui.Button):
        convo.end(interaction.user.id)
        await interaction.response.send_message(
            "Cleared. Send me `/stuck` with what you're working on.", ephemeral=True)


async def _reply(interaction, text: str, ephemeral=False, view=None):
    """Send a reply, splitting it if Discord's 2000-char limit demands it.

    NOTE on `view`: discord.py declares it as `view: BaseView = MISSING` and
    then runs `if view is not MISSING and not view.is_finished()`. Passing an
    explicit None therefore blows up with AttributeError *after* the message
    has already gone out -- which is exactly why every student was seeing a
    perfectly good answer followed by "something went wrong on my end".
    Only pass the argument when there is a real view.
    """
    parts = _chunk(text)
    kw = {"ephemeral": ephemeral}
    if view is not None:
        kw["view"] = view
    await interaction.response.send_message(parts[0], **kw)
    for p in parts[1:]:
        await interaction.followup.send(p, ephemeral=ephemeral)


async def _guard(interaction) -> bool:
    ok, wait = limiter.check(interaction.user.id)
    if not ok:
        await interaction.response.send_message(
            f"Slow down a moment — try again in {wait}s.", ephemeral=True)
    return ok


# ---------------------------------------------------------------------------
# starting a guided conversation
# ---------------------------------------------------------------------------

def _maybe_drop_to_prereq(user_id, concept):
    """If a student keeps returning to the same idea, start one level down.

    Being handed the same five questions for the fourth time confirms you're
    bad at maths. Being handed the thing underneath it, and succeeding, does
    the opposite.
    """
    if struggle_count(user_id, concept.id) < 3 or not concept.prereqs:
        return concept, ""
    lib = library()
    for pid in concept.prereqs:
        p = lib.get(pid)
        if p and struggle_count(user_id, pid) < 2:
            return p, (f"_You've come back to **{concept.name}** a few times "
                       f"this week. Let's drop one level — **{p.name}** is what "
                       f"it's built on, and it usually turns out to be the real "
                       f"gap._\n\n")
    return concept, ""


async def _begin(interaction, r, raw_text: str):
    """Start (or restart) a guided ladder from a tutor response."""
    if not r.ok:
        log_gap(raw_text)
        log_event(interaction.user.id, "unmatched", None, 0.0)
        await _reply(interaction, r.message + "\n\n_I've logged this — questions "
                                              "I can't answer are how the library "
                                              "grows._")
        return

    concept, note = _maybe_drop_to_prereq(interaction.user.id, r.concept)
    # A prerequisite is a different expression, so the student's coefficients
    # no longer apply to it -- fall back to the generic phrasing.
    same = concept.id == r.concept.id
    values = r.values if same else {}

    s = convo.start(interaction.user.id, concept.id, values,
                    r.expr if same else None)
    rendered = render_questions(concept, values)

    log_event(interaction.user.id, "start", concept.id, r.confidence)
    await _reply(interaction, note + convo.first_question(s, rendered, concept),
                 view=Feedback(concept.id))


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

@tree.command(name="stuck", description="Paste where you're stuck and I'll walk you through it")
@app_commands.describe(expression="e.g. 2x^2 + 3x - 1")
async def stuck(interaction: discord.Interaction, expression: str):
    if not await _guard(interaction):
        return
    r = explain_stuck(expression)
    if not r.ok:
        r = explain_question(expression)
    await _begin(interaction, r, expression)


@tree.command(name="step", description="Show a step you took and learn the idea behind it")
@app_commands.describe(before="What you started with", after="What you turned it into")
async def step(interaction: discord.Interaction, before: str, after: str):
    if not await _guard(interaction):
        return
    await _begin(interaction, explain_step(before, after), f"{before} -> {after}")


@tree.command(name="ask", description="Ask about a pre-calculus idea in your own words")
@app_commands.describe(question="e.g. why can I split a log of a product")
async def ask(interaction: discord.Interaction, question: str):
    if not await _guard(interaction):
        return
    await _begin(interaction, explain_question(question), question)


@tree.command(name="reply", description="Answer the question I just asked you")
@app_commands.describe(answer="Your answer, in your own words")
async def reply(interaction: discord.Interaction, answer: str):
    if not await _guard(interaction):
        return
    s = convo.get(interaction.user.id)
    if not s:
        await interaction.response.send_message(
            "We're not mid-conversation. Start with `/stuck` and whatever "
            "you're working on.", ephemeral=True)
        return

    concept = library().get(s.concept_id)
    rendered = render_questions(concept, s.values)
    msg, finished = convo.advance(s, concept, answer, rendered)
    log_event(interaction.user.id, "reply", s.concept_id, 1.0)
    if finished:
        convo.end(interaction.user.id)
        await _reply(interaction, msg, view=Feedback(concept.id))
    else:
        await _reply(interaction, msg)


@tree.command(name="hint", description="The rule behind it — only after you've tried")
@app_commands.describe(concept="Concept id, e.g. factoring-quadratic-simple")
async def hint(interaction: discord.Interaction, concept: str):
    if not await _guard(interaction):
        return
    r = explain_concept_by_id(concept.strip().lower())
    log_event(interaction.user.id, "hint", r.log_concept_id or None, 1.0)
    await _reply(interaction, r.to_text(tier="hint"),
                 view=Feedback(r.log_concept_id) if r.ok else None)


@tree.command(name="example", description="Last resort: one worked through with different numbers")
@app_commands.describe(concept="Concept id, e.g. factoring-quadratic-simple")
async def example(interaction: discord.Interaction, concept: str):
    if not await _guard(interaction):
        return
    r = explain_concept_by_id(concept.strip().lower())
    log_event(interaction.user.id, "example", r.log_concept_id or None, 1.0)
    await _reply(interaction, r.to_text(tier="example"),
                 view=Feedback(r.log_concept_id) if r.ok else None)


async def _concept_ac(interaction: discord.Interaction, current: str):
    cur = (current or "").lower()
    hits = [c for c in library().concepts.values()
            if cur in c.id or cur in c.name.lower()][:25]
    return [app_commands.Choice(name=c.name, value=c.id) for c in hits]

hint.autocomplete("concept")(_concept_ac)
example.autocomplete("concept")(_concept_ac)


@tree.command(name="progress", description="Your own history — private to you")
async def progress(interaction: discord.Interaction):
    await _reply(interaction, personal_progress(interaction.user.id), ephemeral=True)


@tree.command(name="concepts", description="Everything I can explain")
async def concepts(interaction: discord.Interaction):
    lib = library()
    by_topic = {}
    for c in lib.concepts.values():
        by_topic.setdefault(c.topic, []).append(c.name)
    lines = [f"**{len(lib.concepts)} ideas, straight off the Math 1B syllabus.**", ""]
    for topic in sorted(by_topic):
        lines.append(f"__{topic.replace('-', ' ').title()}__")
        lines += [f"  - {n}" for n in sorted(by_topic[topic])]
        lines.append("")
    lines.append("_I don't give answers. I ask the questions that get you there._")
    lines.append("_`/stuck` starts a guided conversation. `/reply` answers me back._")
    await _reply(interaction, "\n".join(lines), ephemeral=True)


@tree.command(name="report", description="Instructor only: anonymous class digest")
async def report(interaction: discord.Interaction):
    if str(interaction.user.id) not in INSTRUCTOR_IDS:
        await interaction.response.send_message(
            "That one's for the instructor. Try `/progress` for your own.",
            ephemeral=True)
        return
    await _reply(interaction, weekly_report(7), ephemeral=True)


# ---------------------------------------------------------------------------

@client.event
async def on_ready():
    try:
        if GUILD_ID:
            g = discord.Object(id=int(GUILD_ID))
            tree.copy_global_to(guild=g)
            await tree.sync(guild=g)
        else:
            await tree.sync()
    except Exception as exc:
        log.error("command sync failed: %s", exc)
    log.info("logged in as %s — %d concepts loaded",
             client.user, len(library().concepts))


@tree.error
async def on_error(interaction, error):
    """Never interrupt a student who already got a good answer.

    If the reply went out and something failed afterwards, that's my problem
    to read in the log -- not something to put in front of a student who is
    mid-thought. Only speak up if they got nothing at all.
    """
    log.exception("command error", exc_info=error)
    if interaction.response.is_done():
        return                      # they already have their answer; stay quiet
    try:
        await interaction.response.send_message(
            "That one tripped me up — give it another go? "
            "It's my bug, not your maths.", ephemeral=True)
    except Exception:
        pass


def main():
    if not TOKEN:
        raise SystemExit(
            "No DISCORD_TOKEN found.\n"
            "Copy .env.example to .env and put your bot token in it.\n"
            "Never commit the .env file."
        )
    library()
    client.run(TOKEN)


if __name__ == "__main__":
    main()
