"""Permission check decorators for slash commands.

The access model:
  1. Channel gate (in_trip_channel): command only works if the channel is
     linked to a trip. Discord's own permissions already gate who's in the
     channel, so this implicitly scopes access.
  2. Membership gate (is_trip_member): user must be a member of the trip
     (row in `members` table) — used for actions that modify trip data.
  3. Admin gate (is_admin): user has the admin role — used for destructive
     or setup operations.
"""
from __future__ import annotations
import discord
from discord import app_commands
from bot.config import ADMIN_ROLE_NAME
from bot.db import queries as q


class NotInTripChannel(app_commands.CheckFailure):
    pass


class NotTripMember(app_commands.CheckFailure):
    pass


class NotAdmin(app_commands.CheckFailure):
    pass


async def _trip_from_interaction(interaction: discord.Interaction) -> dict | None:
    return q.trip_for_channel(interaction.channel_id)


def in_trip_channel():
    async def predicate(interaction: discord.Interaction) -> bool:
        trip = await _trip_from_interaction(interaction)
        if not trip:
            raise NotInTripChannel(
                "This channel isn't linked to a trip. Run this in a trip's "
                "logistics channel, or ask an admin to `/trip link` it."
            )
        # cache on interaction for downstream access without re-querying
        interaction.extras["trip"] = trip
        return True

    return app_commands.check(predicate)


def is_trip_member():
    async def predicate(interaction: discord.Interaction) -> bool:
        trip = interaction.extras.get("trip") or await _trip_from_interaction(interaction)
        if not trip:
            raise NotInTripChannel("Not a trip channel.")
        member = q.get_member(trip["id"], interaction.user.id)
        if not member:
            raise NotTripMember(
                "You're not on this trip's roster. Run `/roster` and click Join first."
            )
        interaction.extras["trip"] = trip
        interaction.extras["member"] = member
        return True

    return app_commands.check(predicate)


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            raise NotAdmin("Admin check only works in a server.")
        if any(r.name == ADMIN_ROLE_NAME for r in interaction.user.roles):
            return True
        # Also accept server owner / administrator permission as admin
        if interaction.user.guild_permissions.administrator:
            return True
        raise NotAdmin(
            f"This command requires the `{ADMIN_ROLE_NAME}` role."
        )

    return app_commands.check(predicate)


async def handle_check_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> bool:
    """Central error handler for check failures. Returns True if handled."""
    if isinstance(error, (NotInTripChannel, NotTripMember, NotAdmin)):
        msg = str(error)
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return True
    return False
