"""Trip management: /trip create | link | info | list | archive."""
from __future__ import annotations
from datetime import date, datetime
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries as q
from bot.utils.checks import is_admin, in_trip_channel
from bot.utils.embeds import base_embed, success_embed, error_embed, trip_header

log = logging.getLogger(__name__)


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _slug(s: str) -> str:
    """discord-safe channel name slug."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:90] or "trip"


class Trips(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="trip", description="Manage festival trips")

    # ------------------------------------------------------------
    # /trip create
    # ------------------------------------------------------------
    @group.command(name="create", description="Create a new trip (admin only)")
    @app_commands.describe(
        name="Short name, e.g. 'EDC 2026'",
        start="Start date YYYY-MM-DD",
        end="End date YYYY-MM-DD",
        festival="Optional full festival name",
    )
    @is_admin()
    async def create(
        self,
        interaction: discord.Interaction,
        name: str,
        start: str,
        end: str,
        festival: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        start_d = _parse_date(start)
        end_d = _parse_date(end)
        if not start_d or not end_d:
            await interaction.followup.send(
                embed=error_embed("Dates must be `YYYY-MM-DD`."), ephemeral=True
            )
            return
        if end_d < start_d:
            await interaction.followup.send(
                embed=error_embed("End date is before start date."), ephemeral=True
            )
            return

        guild = interaction.guild
        assert guild is not None

        # 1. DB row
        trip = q.create_trip(
            name=name,
            festival_name=festival,
            start_date=start_d,
            end_date=end_d,
            guild_id=guild.id,
            created_by_discord_id=interaction.user.id,
        )

        # 2. Trip role
        try:
            role = await guild.create_role(
                name=name,
                mentionable=True,
                reason=f"festbot: trip '{name}' created by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed(
                    "Bot lacks `Manage Roles`. Trip DB row created but no role."
                ),
                ephemeral=True,
            )
            return

        # Grant the creator the role automatically
        try:
            await interaction.user.add_roles(role, reason="festbot: trip creator")
        except discord.Forbidden:
            pass  # not fatal

        # 3. Category + channels, visible only to role-holders
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        try:
            category = await guild.create_category(
                name=name, overwrites=overwrites, reason="festbot: trip category"
            )
            general = await guild.create_text_channel(
                name=f"{_slug(name)}-general", category=category, overwrites=overwrites
            )
            logistics = await guild.create_text_channel(
                name=f"{_slug(name)}-logistics", category=category, overwrites=overwrites
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed(
                    "Bot lacks `Manage Channels`. Role + DB created, channels missing."
                ),
                ephemeral=True,
            )
            return

        # 4. Wire up refs and channel links
        q.set_trip_discord_refs(trip["id"], role_id=role.id, category_id=category.id)
        q.link_channel(trip["id"], general.id, is_primary=False)
        q.link_channel(trip["id"], logistics.id, is_primary=True)

        # 5. Welcome message in logistics
        embed = base_embed(
            f"🎉 {name} is live",
            f"{trip_header(trip)}\n\n"
            f"This is the logistics channel — run bot commands here.\n"
            f"• `/roster` to join and see who's going\n"
            f"• `/lodging list` for rooms and tents\n"
            f"• `/packing list` for the shared checklist",
        )
        await logistics.send(content=role.mention, embed=embed)

        await interaction.followup.send(
            embed=success_embed(
                f"Trip **{name}** created. Channels: {general.mention}, {logistics.mention}."
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # /trip link — link an existing channel to an existing trip
    # ------------------------------------------------------------
    @group.command(
        name="link",
        description="Link the current channel (or one you pick) to a trip (admin)",
    )
    @app_commands.describe(
        trip_id="Trip ID — see /trip list",
        channel="Channel to link (default: current channel)",
        primary="Mark as primary channel (bot announcements go here)",
    )
    @is_admin()
    async def link(
        self,
        interaction: discord.Interaction,
        trip_id: int,
        channel: discord.TextChannel | None = None,
        primary: bool = False,
    ):
        trip = q.get_trip(trip_id)
        if not trip:
            await interaction.response.send_message(
                embed=error_embed(f"No trip with id {trip_id}."), ephemeral=True
            )
            return
        target = channel or interaction.channel
        q.link_channel(trip["id"], target.id, is_primary=primary)
        await interaction.response.send_message(
            embed=success_embed(
                f"Linked {target.mention} to **{trip['name']}**"
                + (" as primary" if primary else "")
                + "."
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # /trip info — info about the trip for the current channel
    # ------------------------------------------------------------
    @group.command(name="info", description="Show info about this channel's trip")
    @in_trip_channel()
    async def info(self, interaction: discord.Interaction):
        trip = interaction.extras["trip"]
        members = q.list_members(trip["id"])
        days_to = (date.fromisoformat(trip["start_date"]) - date.today()).days

        desc = trip_header(trip)
        if days_to > 0:
            desc += f"\n**{days_to} days to go** 🎉"
        elif days_to == 0:
            desc += "\n**Today's the day!** 🚀"
        elif date.today() <= date.fromisoformat(trip["end_date"]):
            desc += "\n**Happening right now** 🔥"
        else:
            desc += f"\n_Ended {-days_to} day(s) ago_"
        desc += f"\n\n**Roster:** {len(members)} going"

        embed = base_embed(f"Trip: {trip['name']}", desc)
        embed.set_footer(text=f"Status: {trip['status']} · ID: {trip['id']}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------
    # /trip list — all trips in this server
    # ------------------------------------------------------------
    @group.command(name="list", description="List all trips in this server")
    @app_commands.describe(include_archived="Include archived trips")
    async def list_trips(
        self, interaction: discord.Interaction, include_archived: bool = False
    ):
        trips = q.list_trips(interaction.guild_id, include_archived=include_archived)
        if not trips:
            await interaction.response.send_message(
                "No trips yet. An admin can run `/trip create`.", ephemeral=True
            )
            return
        lines = []
        for t in trips:
            badge = {
                "planning": "📝",
                "active": "🔥",
                "past": "📦",
                "archived": "🗄️",
            }.get(t["status"], "•")
            lines.append(
                f"{badge} `#{t['id']}` **{t['name']}** — {t['start_date']} → {t['end_date']}"
            )
        embed = base_embed("Trips", "\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------
    # /trip archive
    # ------------------------------------------------------------
    @group.command(name="archive", description="Archive a trip (admin)")
    @app_commands.describe(trip_id="Trip to archive")
    @is_admin()
    async def archive(self, interaction: discord.Interaction, trip_id: int):
        trip = q.get_trip(trip_id)
        if not trip:
            await interaction.response.send_message(
                embed=error_embed(f"No trip with id {trip_id}."), ephemeral=True
            )
            return
        q.set_trip_status(trip_id, "archived")
        await interaction.response.send_message(
            embed=success_embed(
                f"**{trip['name']}** archived. Data kept, hidden from default lists."
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Trips(bot))
