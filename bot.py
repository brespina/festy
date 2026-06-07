"""
festy — a slim Discord bot for festival attendance + logistics.

Design:
  - One festival = one category + one role (named identically) + channels inside it.
  - Visibility is gated by the category's permission overwrites:
        @everyone -> view_channel = False
        <festival role> -> view_channel = True
    People without the role simply don't see the category or its channels.
  - The roster IS the role's member list. No database.
  - All mutating commands are ADMIN-ONLY. There is no way for a member to add
    themselves. They can only be added by an admin via /festival add.

The festival that a command applies to is inferred from the channel you run it
in (its category). So run /festival add inside the festival's channels.
"""

import os
import logging

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])  # for instant slash-command sync
ADMIN_ROLE = os.environ.get("ADMIN_ROLE_NAME", "festival-admin")

# Channels created inside every new festival category.
DEFAULT_CHANNELS = ("general", "logistics", "carpools")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("festy")

intents = discord.Intents.default()
intents.members = True  # privileged — enable "Server Members Intent" in the Dev Portal
bot = commands.Bot(command_prefix="!", intents=intents)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def is_admin():
    """Allow if the user has the admin role OR Manage Server permission."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.manage_guild:
            return True
        return any(r.name == ADMIN_ROLE for r in interaction.user.roles)

    return app_commands.check(predicate)


def festival_role(interaction: discord.Interaction) -> discord.Role | None:
    """The festival role for the channel this command was run in.

    Convention: the role is named identically to the channel's category.
    """
    category = getattr(interaction.channel, "category", None)
    if category is None:
        return None
    return discord.utils.get(interaction.guild.roles, name=category.name)


# --------------------------------------------------------------------------- #
# /festival command group
# --------------------------------------------------------------------------- #
festival = app_commands.Group(
    name="festival", description="Manage festival trips (admin only)"
)


@festival.command(
    name="create",
    description="Create a new festival: role + private category + channels",
)
@app_commands.describe(name="Festival name, e.g. 'EDC 2026'")
@is_admin()
async def create(interaction: discord.Interaction, name: str):
    guild = interaction.guild
    await interaction.response.defer(ephemeral=True)

    if discord.utils.get(guild.categories, name=name):
        await interaction.followup.send(
            f"A festival called **{name}** already exists.", ephemeral=True
        )
        return

    role = discord.utils.get(guild.roles, name=name) or await guild.create_role(
        name=name, mentionable=True, reason=f"festy: festival {name}"
    )

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True),
        guild.me: discord.PermissionOverwrite(view_channel=True),
    }
    category = await guild.create_category(name, overwrites=overwrites, reason="festy")
    for ch in DEFAULT_CHANNELS:
        await guild.create_text_channel(ch, category=category, reason="festy")

    await interaction.followup.send(
        f"Created **{name}** 🎪 — role, private category, and channels "
        f"({', '.join('#' + c for c in DEFAULT_CHANNELS)}) are ready.\n"
        f"Add people with `/festival add` inside one of its channels.",
        ephemeral=True,
    )


@festival.command(name="add", description="Add a member to this channel's festival")
@app_commands.describe(member="The person to add")
@is_admin()
async def add(interaction: discord.Interaction, member: discord.Member):
    role = festival_role(interaction)
    if role is None:
        await interaction.response.send_message(
            "Run this inside a festival's channels — I infer the festival from the category.",
            ephemeral=True,
        )
        return
    if role in member.roles:
        await interaction.response.send_message(
            f"{member.mention} is already on **{role.name}**.", ephemeral=True
        )
        return
    await member.add_roles(role, reason=f"festy: added by {interaction.user}")
    await interaction.response.send_message(
        f"Added {member.mention} to **{role.name}**.", ephemeral=True
    )


@festival.command(
    name="remove", description="Remove a member from this channel's festival"
)
@app_commands.describe(member="The person to remove")
@is_admin()
async def remove(interaction: discord.Interaction, member: discord.Member):
    role = festival_role(interaction)
    if role is None:
        await interaction.response.send_message(
            "Run this inside a festival's channels.", ephemeral=True
        )
        return
    if role not in member.roles:
        await interaction.response.send_message(
            f"{member.mention} isn't on **{role.name}**.", ephemeral=True
        )
        return
    await member.remove_roles(role, reason=f"festy: removed by {interaction.user}")
    await interaction.response.send_message(
        f"Removed {member.mention} from **{role.name}**.", ephemeral=True
    )


@festival.command(
    name="roster", description="Show who's going to this channel's festival"
)
async def roster(interaction: discord.Interaction):
    role = festival_role(interaction)
    if role is None:
        await interaction.response.send_message(
            "Run this inside a festival's channels.", ephemeral=True
        )
        return
    members = sorted(role.members, key=lambda m: m.display_name.lower())
    if not members:
        body = "_Nobody added yet._"
    else:
        body = "\n".join(f"• {m.display_name}" for m in members)
    embed = discord.Embed(
        title=f"{role.name} — {len(members)} going",
        description=body,
        color=role.color if role.color.value else discord.Color.blurple(),
    )
    # roster is visible to anyone who can see the channel (i.e. attendees) — not ephemeral
    await interaction.response.send_message(embed=embed)


@festival.command(name="list", description="List all festivals")
@is_admin()
async def list_festivals(interaction: discord.Interaction):
    guild = interaction.guild
    cats = [c for c in guild.categories if discord.utils.get(guild.roles, name=c.name)]
    if not cats:
        await interaction.response.send_message("No festivals yet.", ephemeral=True)
        return
    lines = []
    for c in cats:
        role = discord.utils.get(guild.roles, name=c.name)
        lines.append(f"• **{c.name}** — {len(role.members)} going")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@festival.command(
    name="archive",
    description="Lock this festival read-only (keeps history for attendees)",
)
@is_admin()
async def archive(interaction: discord.Interaction):
    role = festival_role(interaction)
    category = getattr(interaction.channel, "category", None)
    if role is None or category is None:
        await interaction.response.send_message(
            "Run this inside a festival's channels.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True)
    # attendees keep view access but lose send access; everyone else still can't see it
    await category.set_permissions(
        role, view_channel=True, send_messages=False, reason="festy: archive"
    )
    if not category.name.startswith("[archived] "):
        await category.edit(name=f"[archived] {category.name}")
    await interaction.followup.send(
        f"Archived **{role.name}** — attendees can still read it, but it's now read-only.\n"
        f"(The role and channels remain; delete them by hand if you want them gone.)",
        ephemeral=True,
    )


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CheckFailure):
        msg = f"You need the **{ADMIN_ROLE}** role (or Manage Server) to do that."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    else:
        log.exception("command error", exc_info=error)
        msg = "Something went wrong running that command."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup_hook_impl():
    bot.tree.add_command(festival)
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)  # instant registration on your server
    log.info("Slash commands synced to guild %s", GUILD_ID)


bot.setup_hook = setup_hook_impl


if __name__ == "__main__":
    bot.run(TOKEN)
