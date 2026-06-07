"""Packing: shared group checklist + personal items per member."""
from __future__ import annotations
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries as q
from bot.utils.checks import in_trip_channel, is_trip_member
from bot.utils.embeds import base_embed, success_embed, error_embed

log = logging.getLogger(__name__)


def _packing_embed(trip: dict) -> discord.Embed:
    items = q.list_packing(trip["id"])
    embed = base_embed(f"🎒 Packing — {trip['name']}")
    if not items:
        embed.description = "Empty. Add items with `/packing add`."
        return embed

    shared = [i for i in items if i["shared"]]
    personal = [i for i in items if not i["shared"]]

    def render(group: list[dict]) -> str:
        if not group:
            return "_nothing yet_"
        lines = []
        for it in group:
            check = "✅" if it["brought"] else "⬜"
            assignee = ""
            if it.get("members") and it["members"].get("discord_user_id"):
                assignee = f" — <@{it['members']['discord_user_id']}>"
            elif it.get("shared") and not it.get("assigned_to_member_id"):
                assignee = " — _unclaimed_"
            lines.append(f"{check} `#{it['id']}` {it['item']}{assignee}")
        return "\n".join(lines)

    embed.add_field(name="Group items", value=render(shared), inline=False)
    embed.add_field(name="Personal items", value=render(personal), inline=False)
    embed.set_footer(text="Use /packing check <id> to mark brought · /packing claim <id>")
    return embed


class Packing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="packing", description="Packing checklist")

    @group.command(name="list", description="Show the packing list")
    @in_trip_channel()
    async def list_cmd(self, interaction: discord.Interaction):
        trip = interaction.extras["trip"]
        await interaction.response.send_message(embed=_packing_embed(trip))

    @group.command(name="add", description="Add an item to pack")
    @app_commands.describe(
        item="What to bring, e.g. 'speaker', 'sunscreen'",
        kind="Group item (someone brings for everyone) or personal",
    )
    @app_commands.choices(kind=[
        app_commands.Choice(name="Group", value="group"),
        app_commands.Choice(name="Personal", value="personal"),
    ])
    @is_trip_member()
    async def add(
        self,
        interaction: discord.Interaction,
        item: str,
        kind: app_commands.Choice[str],
    ):
        trip = interaction.extras["trip"]
        member = interaction.extras["member"]
        is_shared = kind.value == "group"
        row = q.add_packing_item(
            trip["id"],
            item,
            shared=is_shared,
            assigned_to_member_id=None if is_shared else member["id"],
            created_by_discord_id=interaction.user.id,
        )
        await interaction.response.send_message(
            embed=success_embed(
                f"Added {'group' if is_shared else 'personal'} item `#{row['id']}` — {item}"
            ),
            ephemeral=True,
        )

    @group.command(name="claim", description="Claim a group item (you'll bring it)")
    @app_commands.describe(item_id="Item ID (see /packing list)")
    @is_trip_member()
    async def claim(self, interaction: discord.Interaction, item_id: int):
        trip = interaction.extras["trip"]
        member = interaction.extras["member"]
        items = q.list_packing(trip["id"])
        match = next((i for i in items if i["id"] == item_id), None)
        if not match:
            await interaction.response.send_message(
                embed=error_embed("No such item on this trip."), ephemeral=True
            )
            return
        if not match["shared"]:
            await interaction.response.send_message(
                embed=error_embed("Only group items can be claimed."), ephemeral=True
            )
            return
        q.db().table("packing_items").update(
            {"assigned_to_member_id": member["id"]}
        ).eq("id", item_id).execute()
        await interaction.response.send_message(
            embed=success_embed(f"You've got `#{item_id}` — {match['item']}."),
            ephemeral=True,
        )

    @group.command(name="check", description="Mark an item as brought/packed")
    @app_commands.describe(item_id="Item ID", brought="True for brought, false to undo")
    @is_trip_member()
    async def check(
        self,
        interaction: discord.Interaction,
        item_id: int,
        brought: bool = True,
    ):
        trip = interaction.extras["trip"]
        items = q.list_packing(trip["id"])
        match = next((i for i in items if i["id"] == item_id), None)
        if not match:
            await interaction.response.send_message(
                embed=error_embed("No such item on this trip."), ephemeral=True
            )
            return
        q.toggle_packing_brought(item_id, brought)
        await interaction.response.send_message(
            embed=success_embed(
                f"`#{item_id}` {match['item']} — {'packed ✅' if brought else 'unchecked'}"
            ),
            ephemeral=True,
        )

    @group.command(name="remove", description="Delete an item from the list")
    @app_commands.describe(item_id="Item ID")
    @is_trip_member()
    async def remove(self, interaction: discord.Interaction, item_id: int):
        trip = interaction.extras["trip"]
        items = q.list_packing(trip["id"])
        match = next((i for i in items if i["id"] == item_id), None)
        if not match:
            await interaction.response.send_message(
                embed=error_embed("No such item on this trip."), ephemeral=True
            )
            return
        q.delete_packing_item(item_id)
        await interaction.response.send_message(
            embed=success_embed(f"Deleted `#{item_id}`."), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Packing(bot))
