"""
Random Demo Picker — a lightweight Discord bot.

Scans a specific channel's message history for SoundCloud and Dropbox
links, and lets anyone run /randomdemo to get a random one for feedback.

No database, no caching — it just reads the channel live each time the
command is used, so it always reflects whatever's currently posted there.
"""

import os
import re
import random
import logging

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DEMO_CHANNEL_ID = int(os.getenv("DEMO_CHANNEL_ID", "0"))
# How many recent messages to scan per run. Raise this if your channel
# has a long history and links are getting missed.
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "2000"))

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


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d command(s)", len(synced))
    except Exception as e:
        log.error("Command sync failed: %s", e)
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


@bot.tree.command(name="randomdemo", description="Pick a random demo link (SoundCloud/Dropbox) from the demo channel")
async def randomdemo(interaction: discord.Interaction):
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

    found = []
    async for message in channel.history(limit=HISTORY_LIMIT):
        for link in extract_allowed_links(message.content):
            found.append((link, message.author.display_name, message.jump_url))

    if not found:
        await interaction.followup.send(
            "No SoundCloud or Dropbox links found in that channel (within the last "
            f"{HISTORY_LIMIT} messages)."
        )
        return

    link, author, jump_url = random.choice(found)
    await interaction.followup.send(
        "🎲 **Random Demo Picked!**\n"
        f"Posted by **{author}**\n"
        f"{link}\n"
        f"[Jump to original message]({jump_url})\n\n"
        f"*({len(found)} eligible demo{'s' if len(found) != 1 else ''} in the pool)*"
    )


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    if not DEMO_CHANNEL_ID:
        raise SystemExit("DEMO_CHANNEL_ID is not set. Copy .env.example to .env and fill it in.")
    bot.run(TOKEN)
