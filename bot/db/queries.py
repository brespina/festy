"""All database operations in one place.

Centralizing queries makes it easy to audit what the bot reads/writes and
keeps the cogs focused on Discord logic.
"""
from __future__ import annotations
from datetime import date
from typing import Any
from bot.db import db


# ============================================================
# TRIPS
# ============================================================
def create_trip(
    *,
    name: str,
    festival_name: str | None,
    start_date: date,
    end_date: date,
    guild_id: int,
    created_by_discord_id: int,
) -> dict[str, Any]:
    res = db().table("trips").insert({
        "name": name,
        "festival_name": festival_name,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "discord_guild_id": guild_id,
        "created_by_discord_id": created_by_discord_id,
    }).execute()
    return res.data[0]


def set_trip_discord_refs(
    trip_id: int,
    *,
    role_id: int | None = None,
    category_id: int | None = None,
) -> None:
    payload: dict[str, Any] = {}
    if role_id is not None:
        payload["discord_role_id"] = role_id
    if category_id is not None:
        payload["discord_category_id"] = category_id
    if payload:
        db().table("trips").update(payload).eq("id", trip_id).execute()


def set_trip_status(trip_id: int, status: str) -> None:
    db().table("trips").update({"status": status}).eq("id", trip_id).execute()


def get_trip(trip_id: int) -> dict[str, Any] | None:
    res = db().table("trips").select("*").eq("id", trip_id).limit(1).execute()
    return res.data[0] if res.data else None


def list_trips(guild_id: int, *, include_archived: bool = False) -> list[dict[str, Any]]:
    q = db().table("trips").select("*").eq("discord_guild_id", guild_id)
    if not include_archived:
        q = q.neq("status", "archived")
    res = q.order("start_date").execute()
    return res.data or []


# ============================================================
# TRIP CHANNELS
# ============================================================
def link_channel(trip_id: int, channel_id: int, *, is_primary: bool = False) -> None:
    db().table("trip_channels").upsert({
        "trip_id": trip_id,
        "channel_id": channel_id,
        "is_primary": is_primary,
    }).execute()


def trip_for_channel(channel_id: int) -> dict[str, Any] | None:
    """Resolve the trip a channel is linked to, if any."""
    res = (
        db().table("trip_channels")
        .select("trip_id, trips(*)")
        .eq("channel_id", channel_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]["trips"]


def get_primary_channel(trip_id: int) -> int | None:
    res = (
        db().table("trip_channels")
        .select("channel_id")
        .eq("trip_id", trip_id)
        .eq("is_primary", True)
        .limit(1)
        .execute()
    )
    return res.data[0]["channel_id"] if res.data else None


# ============================================================
# MEMBERS
# ============================================================
def add_member(
    trip_id: int, discord_user_id: int, display_name: str
) -> dict[str, Any]:
    # Upsert so re-joins don't error
    res = (
        db().table("members")
        .upsert(
            {
                "trip_id": trip_id,
                "discord_user_id": discord_user_id,
                "display_name": display_name,
            },
            on_conflict="trip_id,discord_user_id",
        )
        .execute()
    )
    return res.data[0]


def remove_member(trip_id: int, discord_user_id: int) -> None:
    (
        db().table("members")
        .delete()
        .eq("trip_id", trip_id)
        .eq("discord_user_id", discord_user_id)
        .execute()
    )


def get_member(trip_id: int, discord_user_id: int) -> dict[str, Any] | None:
    res = (
        db().table("members")
        .select("*")
        .eq("trip_id", trip_id)
        .eq("discord_user_id", discord_user_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def list_members(trip_id: int) -> list[dict[str, Any]]:
    res = (
        db().table("members")
        .select("*")
        .eq("trip_id", trip_id)
        .order("display_name")
        .execute()
    )
    return res.data or []


def update_member(member_id: int, **fields: Any) -> None:
    if fields:
        db().table("members").update(fields).eq("id", member_id).execute()


# ============================================================
# LODGING
# ============================================================
def create_lodging(
    trip_id: int,
    name: str,
    *,
    type_: str | None = None,
    address: str | None = None,
    total_cost: float | None = None,
    capacity: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    res = db().table("lodging").insert({
        "trip_id": trip_id,
        "name": name,
        "type": type_,
        "address": address,
        "total_cost": total_cost,
        "capacity": capacity,
        "notes": notes,
    }).execute()
    return res.data[0]


def list_lodging(trip_id: int) -> list[dict[str, Any]]:
    res = (
        db().table("lodging")
        .select("*, lodging_members(*, members(display_name, discord_user_id))")
        .eq("trip_id", trip_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


def assign_lodging(
    lodging_id: int, member_id: int, *, amount_owed: float | None = None
) -> None:
    db().table("lodging_members").upsert({
        "lodging_id": lodging_id,
        "member_id": member_id,
        "amount_owed": amount_owed,
    }).execute()


def unassign_lodging(lodging_id: int, member_id: int) -> None:
    (
        db().table("lodging_members")
        .delete()
        .eq("lodging_id", lodging_id)
        .eq("member_id", member_id)
        .execute()
    )


# ============================================================
# PACKING
# ============================================================
def add_packing_item(
    trip_id: int,
    item: str,
    *,
    shared: bool,
    assigned_to_member_id: int | None = None,
    created_by_discord_id: int | None = None,
) -> dict[str, Any]:
    res = db().table("packing_items").insert({
        "trip_id": trip_id,
        "item": item,
        "shared": shared,
        "assigned_to_member_id": assigned_to_member_id,
        "created_by_discord_id": created_by_discord_id,
    }).execute()
    return res.data[0]


def list_packing(trip_id: int) -> list[dict[str, Any]]:
    res = (
        db().table("packing_items")
        .select("*, members(display_name, discord_user_id)")
        .eq("trip_id", trip_id)
        .order("shared", desc=True)
        .order("item")
        .execute()
    )
    return res.data or []


def toggle_packing_brought(item_id: int, brought: bool) -> None:
    db().table("packing_items").update({"brought": brought}).eq("id", item_id).execute()


def delete_packing_item(item_id: int) -> None:
    db().table("packing_items").delete().eq("id", item_id).execute()
