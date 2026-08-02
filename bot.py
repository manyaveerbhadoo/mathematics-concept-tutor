#!/usr/bin/env python3
"""
bot.py — the Discord layer.

This file deliberately contains NO teaching logic and NO math. It only
receives messages, hands them to mathcore, and posts what comes back.
Everything the bot can say lives in concepts/library.json.

Commands
    /step      "I went from A to B, what idea is that?"
    /ask       a plain-English question
    /stuck     paste an expression, get pointed at the idea
    /concepts  list everything the bot knows
    /report    instructor only: anonymous weekly digest
"""

import os
import logging

import discord
from discord import app_commands
from dotenv import load_dotenv

from mathcore.tutor import (explain_step, explain_question, explain_stuck,
                            explain_concept_by_id, library)
from mathcore.storage import log_event, weekly_report, RateLimiter

load_dotenv()

TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")        # instant command sync
INSTRUCTOR_IDS = {s.strip() for s in os.environ.get("INSTRUCTOR_IDS", "").split(",") if s.strip()}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("mathbot")

limiter = RateLimiter(max_calls=12, per_seconds=60)

intents = discord.Intents.default()          # no message-content intent needed
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DISCORD_LIMIT = 1900   # real cap is 2000; leave headroom


def _chunk(text: str):
    """Discord rejects messages over 2000 characters."""
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


async def _reply(interaction, text: str, ephemeral: bool = False):
    parts = _chunk(text)
    await interaction.response.send_message(parts[0], ephemeral=ephemeral)
    for p in parts[1:]:
        await interaction.followup.send(p, ephemeral=ephemeral)


async def _guard(interaction) -> bool:
    ok, wait = limiter.check(interaction.user.id)
    if not ok:
        await interaction.response.send_message(
            f"Slow down a moment — try again in {wait}s. "
            "Take a run at the last hint while you wait.",
            ephemeral=True)
    return ok


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

@tree.command(name="step", description="Show a step you took and learn the idea behind it")
@app_commands.describe(before="What you started with, e.g. x^2 - 5x + 6",
                       after="What you turned it into, e.g. (x-2)(x-3)")
async def step(interaction: discord.Interaction, before: str, after: str):
    if not await _guard(interaction):
        return
    r = explain_step(before, after)
    log_event(interaction.user.id, "step", r.log_concept_id or None, r.confidence)
    await _reply(interaction, r.to_text())


@tree.command(name="ask", description="Ask about a pre-calculus idea in your own words")
@app_commands.describe(question="e.g. why can I split a log of a product")
async def ask(interaction: discord.Interaction, question: str):
    if not await _guard(interaction):
        return
    r = explain_question(question)
    log_event(interaction.user.id, "question", r.log_concept_id or None, r.confidence)
    await _reply(interaction, r.to_text())


@tree.command(name="stuck", description="Paste where you're stuck and get pointed at the idea")
@app_commands.describe(expression="e.g. (x^2 - 9)/(x + 3)")
async def stuck(interaction: discord.Interaction, expression: str):
    if not await _guard(interaction):
        return
    r = explain_stuck(expression)
    if not r.ok:
        r = explain_question(expression)
    log_event(interaction.user.id, "stuck", r.log_concept_id or None, r.confidence)
    await _reply(interaction, r.to_text())


@tree.command(name="hint", description="Only after you've tried the questions: the rule behind it")
@app_commands.describe(concept="The concept id, e.g. factoring-quadratic-simple")
async def hint(interaction: discord.Interaction, concept: str):
    if not await _guard(interaction):
        return
    r = explain_concept_by_id(concept.strip().lower())
    log_event(interaction.user.id, "hint", r.log_concept_id or None, 1.0)
    await _reply(interaction, r.to_text(tier="hint"))


@hint.autocomplete("concept")
async def _hint_ac(interaction: discord.Interaction, current: str):
    cur = (current or "").lower()
    hits = [c for c in library().concepts.values()
            if cur in c.id or cur in c.name.lower()][:25]
    return [app_commands.Choice(name=c.name, value=c.id) for c in hits]


@tree.command(name="example", description="Last resort: one worked through with different numbers")
@app_commands.describe(concept="The concept id, e.g. factoring-quadratic-simple")
async def example(interaction: discord.Interaction, concept: str):
    if not await _guard(interaction):
        return
    r = explain_concept_by_id(concept.strip().lower())
    log_event(interaction.user.id, "example", r.log_concept_id or None, 1.0)
    await _reply(interaction, r.to_text(tier="example"))


@example.autocomplete("concept")
async def _example_ac(interaction: discord.Interaction, current: str):
    cur = (current or "").lower()
    hits = [c for c in library().concepts.values()
            if cur in c.id or cur in c.name.lower()][:25]
    return [app_commands.Choice(name=c.name, value=c.id) for c in hits]


@tree.command(name="concepts", description="Everything I can explain")
async def concepts(interaction: discord.Interaction):
    lib = library()
    by_topic = {}
    for c in lib.concepts.values():
        by_topic.setdefault(c.topic, []).append(c.name)
    lines = ["**Here's everything I know. Ask me about any of it.**", ""]
    for topic in sorted(by_topic):
        lines.append(f"__{topic.replace('-', ' ').title()}__")
        lines += [f"  - {n}" for n in sorted(by_topic[topic])]
        lines.append("")
    lines.append("_I don't give answers. I ask the questions that get you there._")
    lines.append("_`/step` and `/stuck` give you a ladder of questions. "
                 "`/hint <concept>` gives the rule. `/example <concept>` shows one worked._")
    await _reply(interaction, "\n".join(lines), ephemeral=True)


@tree.command(name="report", description="Instructor only: anonymous weekly summary")
async def report(interaction: discord.Interaction):
    if str(interaction.user.id) not in INSTRUCTOR_IDS:
        await interaction.response.send_message(
            "That one's for the instructor. Try `/ask` or `/step`.", ephemeral=True)
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
    """A student should never see a stack trace."""
    log.exception("command error", exc_info=error)
    msg = "Something went wrong on my end — that's my bug, not your maths. Try again?"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


def main():
    if not TOKEN:
        raise SystemExit(
            "No DISCORD_TOKEN found.\n"
            "Copy .env.example to .env and put your bot token in it.\n"
            "Never commit the .env file."
        )
    library()          # fail fast if the concept library is malformed
    client.run(TOKEN)


if __name__ == "__main__":
    main()
