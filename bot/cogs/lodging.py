"""Lodging: track Airbnbs, hotel rooms, campsites and who's in each."""
from __future__ import annotations
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries as q
from bot.utils.checks import in_trip_channel, is_trip_member
from bot.utils.embeds import base_embed, success_embed, error_embed

log = logging.getLogger(__name__)

LODGING_TYPES = [
    app_commands.Choice(name="Airbnb", value="airbnb"),
    app_commands.Choice(name="Hotel", value="hotel"),
    app_commands.Choice(name="Campsite", value="campsite"),
    app_commands.Choice(name="Tent / RV", value="tent"),
    app_commands.Choice(name="Other", value="other"),
]


def _lodging_embed(trip: dict, lodgings: list[dict]) -> discord.Embed:
    embed = base_embed(f"🏠 Lodging — {trip['name']}")
    if not lodgings:
        embed.description = "No lodging added yet. Admins or members can run `/lodging add`."
        return embed

    for lg in lodgings:
        assignments = lg.get("lodging_members") or []
        header_bits = []
        if lg.get("type"):
            header_bits.append(lg["type"].title())
        if lg.get("capacity"):
            header_bits.append(f"cap {len(assignments)}/{lg['capacity']}")
        if lg.get("total_cost"):
            header_bits.append(f"${lg['total_cost']}")
        header = " · ".join(header_bits) if header_bits else ""

        if assignments:
            lines = []
            for a in assignments:
                m = a.get("members") or {}
                name = f"<@{m.get('discord_user_id')}>" if m.get("discord_user_id") else "?"
                owe = f" — ${a['amount_owed']}" if a.get("amount_owed") is not None else ""
                paid = " ✅" if a.get("paid") else ""
                lines.append(f"• {name}{owe}{paid}")
            body = "\n".join(lines)
        else:
            body = "_empty_"

        if lg.get("notes"):
            body += f"\n\n_{lg['notes']}_"

        embed.add_field(
            name=f"{lg['name']}" + (f" — {header}" if header else ""),
            value=body,
            inline=False,
        )
    return embed


class Lodging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="lodging", description="Rooms, tents, Airbnbs")

    @group.command(name="list", description="Show all lodging for this trip")
    @in_trip_channel()
    async def list_cmd(self, interaction: discord.Interaction):
        trip = interaction.extras["trip"]
        lodgings = q.list_lodging(trip["id"])
        await interaction.response.send_message(embed=_lodging_embed(trip, lodgings))

    @group.command(name="add", description="Add a lodging option")
    @app_commands.describe(
        name="Display name, e.g. 'Red House Airbnb'",
        type="Kind of lodging",
        capacity="Max people",
        total_cost="Total cost (for splitting)",
        address="Address",
        notes="Anything else",
    )
    @app_commands.choices(type=LODGING_TYPES)
    @is_trip_member()
    async def add(
        self,
        interaction: discord.Interaction,
        name: str,
        type: app_commands.Choice[str] | None = None,
        capacity: int | None = None,
        total_cost: float | None = None,
        address: str | None = None,
        notes: str | None = None,
    ):
        trip = interaction.extras["trip"]
        lg = q.create_lodging(
            trip["id"],
            name,
            type_=type.value if type else None,
            address=address,
            total_cost=total_cost,
            capacity=capacity,
            notes=notes,
        )
        await interaction.response.send_message(
            embed=success_embed(f"Added **{lg['name']}** (id `{lg['id']}`)."),
            ephemeral=True,
        )

    @group.command(name="join", description="Assign yourself to a lodging")
    @app_commands.describe(
        lodging_id="Lodging ID (see /lodging list)",
        amount_owed="What you owe (optional — will auto-split if left blank later)",
    )
    @is_trip_member()
    async def join(
        self,
        interaction: discord.Interaction,
        lodging_id: int,
        amount_owed: float | None = None,
    ):
        trip = interaction.extras["trip"]
        member = interaction.extras["member"]
        # Verify lodging belongs to this trip
        lodgings = q.list_lodging(trip["id"])
        if not any(l["id"] == lodging_id for l in lodgings):
            await interaction.response.send_message(
                embed=error_embed(f"No lodging with id {lodging_id} in this trip."),
                ephemeral=True,
            )
            return
        q.assign_lodging(lodging_id, member["id"], amount_owed=amount_owed)
        await interaction.response.send_message(
            embed=success_embed(f"You're in lodging `#{lodging_id}`."),
            ephemeral=True,
        )

    @group.command(name="leave", description="Remove yourself from a lodging")
    @app_commands.describe(lodging_id="Lodging ID")
    @is_trip_member()
    async def leave(self, interaction: discord.Interaction, lodging_id: int):
        member = interaction.extras["member"]
        q.unassign_lodging(lodging_id, member["id"])
        await interaction.response.send_message(
            embed=success_embed(f"Removed you from lodging `#{lodging_id}`."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Lodging(bot))
