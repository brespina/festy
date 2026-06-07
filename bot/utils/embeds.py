"""Shared embed styling so the bot looks consistent across cogs."""
from __future__ import annotations
import discord
from datetime import date

BRAND_COLOR = discord.Color.from_rgb(139, 92, 246)  # violet — change to taste


def base_embed(title: str, description: str | None = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=BRAND_COLOR)


def trip_header(trip: dict) -> str:
    days = (date.fromisoformat(trip["end_date"]) - date.fromisoformat(trip["start_date"])).days + 1
    fest = f" · {trip['festival_name']}" if trip.get("festival_name") else ""
    return f"**{trip['name']}**{fest} · {trip['start_date']} → {trip['end_date']} ({days}d)"


def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(title="⚠️ Error", description=msg, color=discord.Color.red())


def success_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {msg}", color=discord.Color.green())
