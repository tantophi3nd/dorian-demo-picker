"""
Random Demo Picker — a lightweight Discord bot.

Scans a specific channel's message history for SoundCloud and Dropbox
links, and offers two ways to pick a random one for feedback:

  /randomdemo all              — searches the entire channel history
  /randomdemo timeframe <val>  — only searches recent messages (e.g. 7d, 24h)

No database, no caching — it just reads the channel live each time a
command is used, so it always reflects whatever's currently posted there.
"""

import os
import re
import random
import logging
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DEMO_CHANNEL_ID = int(os.getenv("DEMO_CHANNEL_ID", "0"))
# How many recent messages to scan per run when no timeframe is given.
# Raise this if your channel has a long history and links are getting missed.
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "2000"))

# Safety cap on messages scanned even when a timeframe IS given, in case a
# channel is extremely active. Time-filtered searches rarely need this.
TIMEFRAME_MESSAGE_CAP = int(os.getenv("TIMEFRAME_MESSAGE_CAP", "5000"))

# Accepts things like "30m", "24h", "7d", "2w" (case-insensitive).
TIMEFRAME_PATTERN = re.compile(r"^\s*(\d+)\s*([mhdw])\s*$", re.IGNORECASE)
TIMEFRAME_UNITS = {
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}

# Only links from these domains are considered valid demos.
# Subdomains are allowed (e.g. "www.dropbox.com", "on.soundcloud.com").
ALLOWED_DOMAINS = ("soundcloud.com", "dropbox.com")

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("randomdemo")

intents = discord.Intents.default()
intents.message_content = True  # required to read link text in messages

bot = commands.Bot(command_prefix="!", intents=intents)


def is_allowed_link(url: str) -> bool:
    """True if the URL's host is (or is a subdomain of) an allowed domain."""
    try:
        host = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).split("/")[0].lower()
        host = host.split("@")[-1]  # strip any userinfo@ prefix
        host = host.split(":")[0]   # strip port
    except Exception:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS)


def extract_allowed_links(text: str) -> list[str]:
    """Return all URLs in a message that belong to an allowed domain."""
    return [url.rstrip(").,>") for url in URL_PATTERN.findall(text) if is_allowed_link(url)]


def parse_timeframe(value: str) -> Optional[timedelta]:
    """Parse a string like '7d', '24h', '30m', or '2w' into a timedelta.
    Returns None if the string doesn't match the expected format."""
    match = TIMEFRAME_PATTERN.match(value)
    if not match:
        return None
    amount, unit = match.groups()
    return timedelta(**{TIMEFRAME_UNITS[unit.lower()]: int(amount)})


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d command(s)", len(synced))
    except Exception as e:
        log.error("Command sync failed: %s", e)
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


async def _run_randomdemo(interaction: discord.Interaction, delta: Optional[timedelta], scope_desc: str) -> None:
    """Shared logic for both subcommands: fetch the channel, scan its
    history (optionally bounded by `delta`), and reply with a random pick."""
    await interaction.response.defer()

    channel = bot.get_channel(DEMO_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(DEMO_CHANNEL_ID)
        except discord.NotFound:
            await interaction.followup.send(
                "Couldn't find the demo channel — check the `DEMO_CHANNEL_ID` in the bot's `.env` file."
            )
            return
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to view that channel. Make sure I have the "
                "**View Channel** and **Read Message History** permissions there."
            )
            return

    if delta is not None:
        history = channel.history(after=discord.utils.utcnow() - delta, limit=TIMEFRAME_MESSAGE_CAP)
    else:
        history = channel.history(limit=HISTORY_LIMIT)

    found = []
    async for message in history:
        for link in extract_allowed_links(message.content):
            found.append((link, message.author.display_name, message.jump_url))

    if not found:
        await interaction.followup.send(f"No SoundCloud or Dropbox links found in {scope_desc}.")
        return

    link, author, jump_url = random.choice(found)
    await interaction.followup.send(
        "🎲 **Random Demo Picked!**\n"
        f"Posted by **{author}**\n"
        f"{link}\n"
        f"[Jump to original message]({jump_url})\n\n"
        f"*(searched {scope_desc} — {len(found)} eligible demo{'s' if len(found) != 1 else ''} in the pool)*"
    )


demo_group = app_commands.Group(
    name="randomdemo",
    description="Pick a random demo link (SoundCloud/Dropbox) for feedback",
)


@demo_group.command(name="all", description="Pick a random demo from the entire channel history")
async def randomdemo_all(interaction: discord.Interaction):
    await _run_randomdemo(interaction, delta=None, scope_desc=f"the last {HISTORY_LIMIT} messages")


@demo_group.command(name="timeframe", description="Pick a random demo from messages posted within a timeframe")
@app_commands.describe(timeframe="How far back to search: a number plus m/h/d/w, e.g. 30m, 24h, 7d, 2w")
async def randomdemo_timeframe(interaction: discord.Interaction, timeframe: str):
    delta = parse_timeframe(timeframe)
    if delta is None:
        await interaction.response.send_message(
            "Couldn't understand that timeframe. Use a number plus a unit — "
            "`m` (minutes), `h` (hours), `d` (days), or `w` (weeks). "
            "Examples: `30m`, `24h`, `7d`, `2w`.",
            ephemeral=True,
        )
        return
    await _run_randomdemo(interaction, delta=delta, scope_desc=f"the last {timeframe.strip().lower()}")


bot.tree.add_command(demo_group)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    if not DEMO_CHANNEL_ID:
        raise SystemExit("DEMO_CHANNEL_ID is not set. Copy .env.example to .env and fill it in.")
    bot.run(TOKEN)
