"""
Discord Demo Picker Bot
------------------------
Randomly picks a demo link (SoundCloud or Dropbox only) from recent messages
in a channel. Any other domain is ignored, so random/scam links can't win.

Setup:
    1. pip install -U discord.py
    2. Create a bot at https://discord.com/developers/applications
       - Enable "MESSAGE CONTENT INTENT" under Bot > Privileged Gateway Intents
       - Invite it to your server with "applications.commands" + "bot" scopes
         (permissions: View Channel, Read Message History, Send Messages)
    3. Set your token as an environment variable:
         export DISCORD_BOT_TOKEN="your-token-here"
    4. Run:
         python demo_picker_bot.py

Usage in Discord:
    /pickdemo                -> picks from the last 500 messages in the current channel
    /pickdemo limit:1000     -> picks from the last 1000 messages
    /pickdemo channel:#demos -> picks from a specific channel
"""

import os
import re
import random
import discord
from discord import app_commands
from discord.ext import commands

# ---- Config ----------------------------------------------------------

ALLOWED_DOMAINS = ("soundcloud.com", "dropbox.com")
DEFAULT_HISTORY_LIMIT = 500
MAX_HISTORY_LIMIT = 2000

URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)

# ---- Bot setup ---------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True  # needed to read link text in messages

bot = commands.Bot(command_prefix="!", intents=intents)


def extract_allowed_links(content: str) -> list[str]:
    """Return only URLs whose domain matches the whitelist."""
    found = []
    for url in URL_PATTERN.findall(content):
        url_clean = url.rstrip(").,>\"'")
        # crude domain extraction without extra deps
        domain = url_clean.split("//", 1)[-1].split("/", 1)[0].lower()
        domain = domain.split("@")[-1]  # strip any userinfo@ prefix
        if any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS):
            found.append(url_clean)
    return found


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user}. Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Sync failed: {e}")


@bot.tree.command(name="pickdemo", description="Randomly pick a SoundCloud/Dropbox demo link from this channel")
@app_commands.describe(
    limit="How many recent messages to scan (default 500, max 2000)",
    channel="Channel to scan (default: this channel)",
)
async def pickdemo(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, MAX_HISTORY_LIMIT] = DEFAULT_HISTORY_LIMIT,
    channel: discord.TextChannel | None = None,
):
    target_channel = channel or interaction.channel
    await interaction.response.defer(thinking=True)

    candidates = []  # (url, author_display_name, jump_url)
    async for message in target_channel.history(limit=limit):
        if message.author.bot:
            continue
        for url in extract_allowed_links(message.content):
            candidates.append((url, message.author.display_name, message.jump_url))

    if not candidates:
        await interaction.followup.send(
            f"No SoundCloud or Dropbox links found in the last {limit} messages of {target_channel.mention}."
        )
        return

    url, author, jump_url = random.choice(candidates)

    embed = discord.Embed(
        title="🎲 Demo Picked!",
        description=f"[Listen here]({url})",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Submitted by", value=author, inline=True)
    embed.add_field(name="Original message", value=f"[Jump to it]({jump_url})", inline=True)
    embed.set_footer(text=f"Picked from {len(candidates)} eligible link(s) • whitelist: soundcloud.com, dropbox.com")

    await interaction.followup.send(embed=embed)


if __name__ == "__main__":
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Set the DISCORD_BOT_TOKEN environment variable before running this bot.")
    bot.run(token)
