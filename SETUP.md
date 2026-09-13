# Discord Announcement Watcher — Setup Guide

## What This Does
A 24/7 bot running on Render.com that monitors your Discord server's announcement channel
and forwards **new messages** to **ntfy.sh** for instant phone notifications.

No web scraping — uses Discord API directly. More reliable than scraping since
you're already in the server.

## Quick Setup

### 1. Create a Discord Bot
1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. Click "New Application" → name it (e.g., `discord-announce-watcher`)
3. Go to "Bot" tab → click "Add Bot"
4. Under "Token", click "Reset Token" → copy the token
5. Enable "Message Content Intent" and "Server Members Intent" under "Privileged Gateway Intents"

### 2. Invite Bot to Your Server
1. Go to "OAuth2" → "URL Generator"
2. Select scopes: `bot`
3. Select bot permissions: `Read Messages/View Channels`, `Send Messages`, `Embed Links`
3. Copy the generated URL → open in browser → add bot to your server
4. **Note the Channel ID**: Enable Developer Mode (User Settings → Advanced → Developer Mode), right-click your announcement channel → "Copy ID". This is your `DISCORD_CHANNEL_ID`.

### 3. Set Up Render Deployment
1. Push these 4 files to a GitHub repo:
   - `discord_announce_watcher.py`
   - `requirements.txt`
   - `render.yaml`
   - `SETUP.md`
2. Go to [render.com](https://render.com) → sign up with GitHub
3. Click "New" → "Web Service" → connect your repo
4. Render auto-detects `render.yaml`:
   - Name: `discord-announce-watcher`
   - Build: `pip install -r requirements.txt`
   - Start: `python3 discord_announce_watcher.py`
   - Health check: `/health`
5. Click "Create Web Service"

### 4. Set Up BetterStack Keep-Alive
1. Go to [betterstack.com](https://betterstack.com) → free signup
2. Create a new Monitor → "Web"
3. URL: `https://your-app-name.onrender.com/health`
4. Interval: **3 minutes** (minimum free tier)
5. This pings your bot every 3 min to keep Render awake

### 5. Configure Environment Variables
In your Render dashboard → your service → "Environment" → add variables:
- `DISCORD_TOKEN` — your bot's token (from step 1)
- `DISCORD_CHANNEL_ID` — the channel ID you copied (from step 2)
- `NTFY_TOPIC` — optional: custom ntfy topic (default: `discord-announcements`)
- `POLL_INTERVAL` — optional: seconds between checks (default: `30`)

### 6. You're Done!
- Bot polls Discord every 30 seconds
- New messages in your announcement channel → push notification to phone
- BetterStack pings keep Render awake 24/7

## How It Works

```
[Your Discord Server] --Discord API--> [Your Bot on Render]
                                       |
                                       v
                               ntfy.sh --> [ntfy App on Phone]
                                       (push notification)
```

Each notification includes:
- **Title**: Clean message content (truncated to 80 chars)
- **Body**: Full message + "via Discord"
- **Tap**: Opens the Discord message in browser
- **Priority**: High (5) — buzzes even on silent

## Testing

```bash
# One-time test sweep (no notifications sent)
RUN_ONCE=1 python3 discord_announce_watcher.py

# Full mode (Flask + polling loop)
python3 discord_announce_watcher.py
# Then visit http://localhost:8080/health to verify Flask is alive
```

## Architecture

```
Discord Channel Messages
        |
        v
[Bot fetches last 5 messages via Discord API]
        |
        v
[Dedup via SHA-256 hash of (message ID + channel)]
        |
        v
[Only NEW messages → ntfy.sh push]
        |
        v
[Phone gets instant notification]
```

## Troubleshooting

- **"401 Unauthorized"** → Check `DISCORD_TOKEN` and that "Message Content Intent" is enabled
- **"404 Not Found"** → Verify `DISCORD_CHANNEL_ID` is correct (enable Developer Mode)
- **"No notifications"** → Send a test message to your announcement channel; bot polls every 30 sec
- **"Service sleeping"** → Make sure BetterStack monitor is pinging `/health` every 3 min
- **"Old messages forwarded"** → The dedup engine uses message IDs; only forward new messages