# festy

A slim Discord bot for coordinating festival attendance + logistics for a friend group.
No database, no Docker — one Python file, run as a systemd service on a Raspberry Pi.

## How it works

- **One festival = one role + one private category + channels.** The role and
  category share a name; that's how the bot maps a channel back to its festival.
- **Visibility is gated by the category's permissions:** `@everyone → view off`,
  `festival role → view on`. No role means you don't see the channels.
- **The roster IS the role's member list.** There's no database — "who's going"
  is literally who has the role.
- **All mutating commands are admin-only.** Members have no command that grants
  themselves a role; people are added by an admin via `/festival add`.
- **Logistics** (dates, lodging, packing) live in pinned messages in `#logistics`.

## Commands

All under `/festival`. Admin-only except `roster`.

| Command | Who | What |
| --- | --- | --- |
| `/festival create name:` | admin | Creates the role, a private category, and `#general #logistics #carpools`. Run anywhere. |
| `/festival add member:` | admin | Adds someone to the festival of the current channel (assigns the role). |
| `/festival remove member:` | admin | Removes someone from the festival. |
| `/festival roster` | attendees | Embed of who's going + headcount. |
| `/festival list` | admin | All festivals with headcounts. |
| `/festival archive` | admin | Locks a festival read-only when it's over (non-destructive). |

`add`, `remove`, `roster`, and `archive` infer which festival you mean from the
channel's category — run them inside the festival's channels.

## Admins

A user is an admin if they have the **`festival-admin`** role (configurable via
`ADMIN_ROLE_NAME`) **or** Discord's **Manage Server** permission. Create the role
in Server Settings → Roles and assign it to whoever should manage trips —
multiple people is fine.

## Setup

### 1. Discord application

1. <https://discord.com/developers/applications> → New Application
2. **Bot → Reset Token**, copy it
3. **Bot → Privileged Gateway Intents → enable Server Members Intent**
4. **OAuth2 → URL Generator**
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: Manage Roles, Manage Channels, View Channels, Send
     Messages, Embed Links, Read Message History, Use Slash Commands
5. Open the generated URL and invite the bot to your server.

### 2. Role hierarchy (important)

In **Server Settings → Roles**, drag the **bot's own role above** the festival
roles. If it sits below them, `add`/`remove` fail with a Forbidden error. This is
the most common first-run problem.

### 3. Configure `.env`

Create `.env` next to `bot.py`. No quotes, no spaces around `=`, no inline
comments (systemd's `EnvironmentFile` is strict).

```
DISCORD_TOKEN=your-bot-token
GUILD_ID=your-server-id
ADMIN_ROLE_NAME=festival-admin
```

`GUILD_ID`: enable Developer Mode (Discord Settings → Advanced), then right-click
your server icon → Copy Server ID.

### 4. Install

```bash
cd ~/festy
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Test it runs before installing the service:

```bash
.venv/bin/python bot.py
```

You should see `Logged in as ...` and `Slash commands synced to guild ...`.
Ctrl+C to stop.

### 5. Run 24/7 with systemd

Edit `festy.service` so `User` and the paths match your Pi (username and the
`/home/<user>/festy` directory), then:

```bash
sudo cp festy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now festy
systemctl status festy
```

`enable` starts it on every boot; `Restart=on-failure` relaunches it on a crash.
As long as the Pi has power and internet, the bot stays up.

## Usage

```
# as an admin, anywhere:
/festival create name:"EDC 2026"

# then inside one of its channels (e.g. #general):
/festival add member:@friend
/festival roster
```

## Day-to-day commands

```bash
systemctl status festy          # is it running?
sudo systemctl restart festy    # after editing bot.py or .env
journalctl -u festy -f          # tail logs
journalctl -u festy -n 50       # last 50 log lines
```

## Requirements

- Raspberry Pi (or any Linux box) with Python 3.11+
- `discord.py >= 2.3`, `python-dotenv >= 1.0`
- On Python 3.13+, also `audioop-lts` (the stdlib `audioop` module was removed in
  3.13 and discord.py depends on it).

## Design notes / limits

- **No database by design.** State lives in Discord (roles, channels, pinned
  messages). This keeps deployment to a single file.
- The point where you'd need to add SQLite is when you want the bot to *compute
  or query* over data — expense balances, "who still needs a ride," reports
  across trips. Roles and pinned messages can't do that. Until then, stay slim.
- **Native Discord Events are not used.** External/IRL events are visible
  server-wide regardless of channel permissions, which would leak a festival's
  existence to non-attendees. Dates go in pinned messages in `#logistics`
  instead.
- `archive` is intentionally non-destructive: it locks channels read-only and
  prepends `[archived]` to the category. Delete roles/channels by hand if you
  want them fully gone, so a misfired command can't nuke history.
