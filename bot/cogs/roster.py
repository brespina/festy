"""Roster: /roster with Join/Leave buttons and a modal for editing details."""
from __future__ import annotations
from datetime import date, datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries as q
from bot.utils.checks import in_trip_channel
from bot.utils.embeds import base_embed, success_embed, error_embed, trip_header

log = logging.getLogger(__name__)


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _roster_embed(trip: dict) -> discord.Embed:
    members = q.list_members(trip["id"])
    embed = base_embed(
        f"🎪 Roster — {trip['name']}",
        trip_header(trip) + f"\n\n**{len(members)} going**",
    )
    if not members:
        embed.add_field(
            name="Nobody yet",
            value="Click **Join** below to RSVP.",
            inline=False,
        )
        return embed

    lines = []
    for m in members:
        parts = [f"<@{m['discord_user_id']}>"]
        if m.get("arrival") or m.get("departure"):
            arr = m.get("arrival") or "?"
            dep = m.get("departure") or "?"
            parts.append(f"· {arr} → {dep}")
        flags = []
        if m.get("needs_ride"):
            flags.append("🚗 needs ride")
        if m.get("can_offer_ride"):
            flags.append("🚙 can drive")
        if flags:
            parts.append("· " + ", ".join(flags))
        lines.append(" ".join(parts))
    embed.add_field(name="Attending", value="\n".join(lines), inline=False)
    return embed


class EditDetailsModal(discord.ui.Modal, title="Your trip details"):
    arrival = discord.ui.TextInput(
        label="Arrival date (YYYY-MM-DD)", required=False, max_length=10
    )
    departure = discord.ui.TextInput(
        label="Departure date (YYYY-MM-DD)", required=False, max_length=10
    )
    needs_ride = discord.ui.TextInput(
        label="Need a ride? (yes/no)", required=False, max_length=3
    )
    can_drive = discord.ui.TextInput(
        label="Can offer a ride? (yes/no)", required=False, max_length=3
    )
    notes = discord.ui.TextInput(
        label="Notes",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=300,
    )

    def __init__(self, member: dict, trip: dict):
        super().__init__()
        self.member = member
        self.trip = trip
        # pre-fill
        if member.get("arrival"):
            self.arrival.default = member["arrival"]
        if member.get("departure"):
            self.departure.default = member["departure"]
        self.needs_ride.default = "yes" if member.get("needs_ride") else "no"
        self.can_drive.default = "yes" if member.get("can_offer_ride") else "no"
        if member.get("notes"):
            self.notes.default = member["notes"]

    async def on_submit(self, interaction: discord.Interaction):
        updates: dict = {}

        if self.arrival.value.strip():
            d = _parse_date(self.arrival.value.strip())
            if not d:
                await interaction.response.send_message(
                    embed=error_embed("Arrival must be `YYYY-MM-DD`."), ephemeral=True
                )
                return
            updates["arrival"] = d.isoformat()
        if self.departure.value.strip():
            d = _parse_date(self.departure.value.strip())
            if not d:
                await interaction.response.send_message(
                    embed=error_embed("Departure must be `YYYY-MM-DD`."), ephemeral=True
                )
                return
            updates["departure"] = d.isoformat()

        updates["needs_ride"] = self.needs_ride.value.strip().lower().startswith("y")
        updates["can_offer_ride"] = self.can_drive.value.strip().lower().startswith("y")
        if self.notes.value.strip():
            updates["notes"] = self.notes.value.strip()

        q.update_member(self.member["id"], **updates)
        await interaction.response.send_message(
            embed=success_embed("Updated your trip details."), ephemeral=True
        )


class RosterView(discord.ui.View):
    """Persistent view — buttons survive bot restarts via custom_ids."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _resolve_trip(self, interaction: discord.Interaction) -> dict | None:
        trip = q.trip_for_channel(interaction.channel_id)
        if not trip:
            await interaction.response.send_message(
                embed=error_embed("This channel isn't linked to a trip."),
                ephemeral=True,
            )
            return None
        return trip

    @discord.ui.button(
        label="Join", style=discord.ButtonStyle.success, custom_id="roster:join"
    )
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        trip = await self._resolve_trip(interaction)
        if not trip:
            return
        q.add_member(
            trip["id"], interaction.user.id, interaction.user.display_name
        )
        # Grant the trip role if configured
        if trip.get("discord_role_id") and isinstance(interaction.user, discord.Member):
            role = interaction.guild.get_role(trip["discord_role_id"])
            if role and role not in interaction.user.roles:
                try:
                    await interaction.user.add_roles(role, reason="festbot: joined trip")
                except discord.Forbidden:
                    pass
        await interaction.response.send_message(
            embed=success_embed(
                f"You're on the roster for **{trip['name']}**.\n"
                "Use `/roster edit` to set your arrival / ride details."
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Leave", style=discord.ButtonStyle.danger, custom_id="roster:leave"
    )
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        trip = await self._resolve_trip(interaction)
        if not trip:
            return
        q.remove_member(trip["id"], interaction.user.id)
        if trip.get("discord_role_id") and isinstance(interaction.user, discord.Member):
            role = interaction.guild.get_role(trip["discord_role_id"])
            if role and role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role, reason="festbot: left trip")
                except discord.Forbidden:
                    pass
        await interaction.response.send_message(
            embed=success_embed(f"Removed you from the **{trip['name']}** roster."),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        custom_id="roster:refresh",
    )
    async def refresh(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        trip = await self._resolve_trip(interaction)
        if not trip:
            return
        await interaction.response.edit_message(embed=_roster_embed(trip), view=self)


class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="roster", description="Who's going on this trip")

    @group.command(name="show", description="Show the trip roster")
    @in_trip_channel()
    async def show(self, interaction: discord.Interaction):
        trip = interaction.extras["trip"]
        await interaction.response.send_message(
            embed=_roster_embed(trip), view=RosterView()
        )

    @group.command(name="edit", description="Edit your arrival, ride, and notes")
    @in_trip_channel()
    async def edit(self, interaction: discord.Interaction):
        trip = interaction.extras["trip"]
        member = q.get_member(trip["id"], interaction.user.id)
        if not member:
            await interaction.response.send_message(
                embed=error_embed("Join the roster first with `/roster show`."),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(EditDetailsModal(member, trip))


async def setup(bot: commands.Bot):
    await bot.add_cog(Roster(bot))
    bot.add_view(RosterView())  # register persistent view
