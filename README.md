# festbot

A Discord bot for coordinating multi-trip festival logistics. Built for groups who attend multiple festivals together with overlapping-but-different rosters.

## Architecture at a glance

- **One Discord server**, many trips (EDC 2026, Lost Lands 2026, etc.)
- **Each trip = a Discord category + role + rows in the DB**
- **Channel-scoped commands**: the bot figures out which trip you mean from the channel you ran the command in
- **Native Discord permissions**: channel visibility gates access — if you're not in the trip role, you don't see the channel, you can't run commands

## Stack

- Python 3.11+ / discord.py 2.x
- Supabase (Postgres) for persistence
- APScheduler for reminders and countdowns
- Docker Compose for deployment on tandu

## Phase 1 features (this repo)

- `/trip create | link | info | list | archive` — trip setup (admin)
- `/roster` — who's going, arrival/departure, rideshare flag
- `/lodging` — rooms/tents/Airbnbs with per-person cost split
- `/packing` — group + personal packing checklists
- Daily countdown messages per trip

Phase 2 (`/schedule`, `/meetup`, `/expense`) and Phase 3 (`/poll`, memory threads) live on the roadmap — architecture is ready for them.

## Setup

### 1. Create the Discord app

1. Go to https://discord.com/developers/applications, New Application
2. Bot → Reset Token, copy it
3. Privileged Gateway Intents: enable **Server Members Intent**
4. OAuth2 → URL Generator → scopes: `bot`, `applications.commands` → permissions: Manage Roles, Manage Channels, Send Messages, Embed Links, Read Message History, Use Slash Commands
5. Invite the bot to your server with the generated URL

### 2. Create the Supabase project

1. New project at supabase.com (free tier is fine)
2. SQL Editor → paste `migrations/001_init.sql` → run
3. Project Settings → API → copy the URL and the `service_role` key (bot needs write access; we use RLS-bypassing service role and enforce access in bot code)

### 3. Configure environment

```bash
cp .env.example .env
# edit .env with your tokens
```

Required:
- `DISCORD_TOKEN` — bot token
- `DISCORD_GUILD_ID` — your server ID (for instant slash command registration during dev)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `ADMIN_ROLE_NAME` — defaults to `festival-admin`

### 4. Create the admin role in Discord

Create a role called `festival-admin` (or whatever you set `ADMIN_ROLE_NAME` to) and give it to yourself + anyone who should manage trips.

### 5. Deploy to tandu

```bash
# from your machine
rsync -av ./ brandon@tandu.tailbe47ed.ts.net:~/festbot/
ssh brandon@tandu.tailbe47ed.ts.net
cd ~/festbot
docker compose up -d --build
docker compose logs -f
```

Then add a monitor in Uptime Kuma pointing at `http://tandu.tailbe47ed.ts.net:8765/health`.

## First-time usage

```
# as an admin, in any channel:
/trip create name:"EDC 2026" start:2026-05-15 end:2026-05-17 festival:"EDC Las Vegas"
# bot creates category, role, channels, and links them

# anyone with the trip role can now:
/roster              # shows current roster with Join/Leave buttons
/lodging list        # shows lodging assignments
/packing list        # shows the packing checklist
```

## Project layout

```
bot/
  main.py              # entry point, loads cogs, starts scheduler + healthcheck
  config.py            # env var loading
  db/
    client.py          # Supabase client singleton
    queries.py         # all SQL in one place (easier to review/audit)
  utils/
    checks.py          # decorators: in_trip_channel, is_trip_member, is_admin
    embeds.py          # shared embed styling
    scheduler.py       # APScheduler setup
  cogs/
    trips.py           # /trip ...
    roster.py          # /roster
    lodging.py         # /lodging ...
    packing.py         # /packing ...
    countdown.py       # daily countdown scheduled task
migrations/
  001_init.sql         # schema
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

## Notes for future-me

- Slash commands are registered to `DISCORD_GUILD_ID` for instant updates during dev. To go global, call `tree.sync()` without a guild arg — propagation takes up to an hour.
- The bot uses the Supabase **service_role** key and bypasses RLS. Access control is enforced in `utils/checks.py`. If you ever expose a web UI, switch to anon key + RLS.
- `bot/db/queries.py` centralizes all SQL. Keeps it easy to reason about what the bot can read/write.
- Healthcheck endpoint on port 8765 is there so Uptime Kuma can alert you when the bot dies.
