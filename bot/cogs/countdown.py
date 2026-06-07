"""Daily countdown messages to each trip's primary channel."""
from __future__ import annotations
from datetime import date
import logging

import discord
from discord.ext import commands

from bot.config import COUNTDOWN_HOUR, COUNTDOWN_MINUTE
from bot.db import queries as q
from bot.utils.scheduler import scheduler
from bot.utils.embeds import base_embed

log = logging.getLogger(__name__)


class Countdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _run_countdowns(self):
        """Post a countdown in each active trip's primary channel."""
        for guild in self.bot.guilds:
            trips = q.list_trips(guild.id)
            today = date.today()

            for trip in trips:
                start = date.fromisoformat(trip["start_date"])
                end = date.fromisoformat(trip["end_date"])
                days_to = (start - today).days

                # Auto-update status
                if today > end and trip["status"] != "past":
                    q.set_trip_status(trip["id"], "past")
                    continue
                if start <= today <= end and trip["status"] != "active":
                    q.set_trip_status(trip["id"], "active")

                # Only announce during a meaningful window
                if not (-0 <= days_to <= 30 or (start <= today <= end)):
                    continue

                channel_id = q.get_primary_channel(trip["id"])
                if not channel_id:
                    continue
                channel = guild.get_channel(channel_id)
                if channel is None:
                    continue

                if days_to > 0:
                    msg = f"**{days_to}** day{'s' if days_to != 1 else ''} until **{trip['name']}** 🎉"
                elif days_to == 0:
                    msg = f"🚀 **Today's the day — {trip['name']} starts!**"
                else:
                    msg = f"🔥 **{trip['name']}** is happening now. Have fun out there."

                try:
                    await channel.send(embed=base_embed(trip["name"], msg))
                except discord.Forbidden:
                    log.warning("Cannot send countdown in channel %s", channel_id)

    @commands.Cog.listener()
    async def on_ready(self):
        if scheduler.get_job("daily_countdown"):
            return
        scheduler.add_job(
            self._run_countdowns,
            "cron",
            hour=COUNTDOWN_HOUR,
            minute=COUNTDOWN_MINUTE,
            id="daily_countdown",
        )
        log.info(
            "Scheduled daily countdown at %02d:%02d", COUNTDOWN_HOUR, COUNTDOWN_MINUTE
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Countdown(bot))
