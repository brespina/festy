"""festbot entry point.

- Loads cogs
- Starts the APScheduler
- Runs a tiny aiohttp healthcheck server so Uptime Kuma can monitor liveness
- Syncs slash commands to DISCORD_GUILD_ID for instant availability
"""
from __future__ import annotations
import asyncio
import logging

import discord
from discord.ext import commands
from aiohttp import web

from bot.config import (
    DISCORD_TOKEN,
    DISCORD_GUILD_ID,
    HEALTHCHECK_PORT,
    LOG_LEVEL,
)
from bot.utils.checks import handle_check_error
from bot.utils.scheduler import scheduler


logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("festbot")


INITIAL_COGS = [
    "bot.cogs.trips",
    "bot.cogs.roster",
    "bot.cogs.lodging",
    "bot.cogs.packing",
    "bot.cogs.countdown",
]


class FestBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # needed for role assignment & display names
        intents.message_content = False
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        for cog in INITIAL_COGS:
            await self.load_extension(cog)
            log.info("Loaded %s", cog)

        # Sync slash commands to the dev guild for instant propagation
        guild = discord.Object(id=DISCORD_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("Synced %d commands to guild %s", len(synced), DISCORD_GUILD_ID)

        if not scheduler.running:
            scheduler.start()
            log.info("Scheduler started")

    async def on_ready(self):
        log.info("Logged in as %s (id=%s)", self.user, self.user.id)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ):
        if await handle_check_error(interaction, error):
            return
        log.exception("Unhandled app command error", exc_info=error)
        msg = "Something went wrong. Check the bot logs."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


# ---------------------------------------------------------------
# Healthcheck server
# ---------------------------------------------------------------
async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _run_health_server():
    app = web.Application()
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTHCHECK_PORT)
    await site.start()
    log.info("Healthcheck listening on :%d/health", HEALTHCHECK_PORT)


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
async def main():
    bot = FestBot()
    # Tree error handler (app commands route through here)
    bot.tree.on_error = bot.on_app_command_error

    async with bot:
        await _run_health_server()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
