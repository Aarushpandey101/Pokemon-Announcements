# Pokemon GO Announcement Watcher — Setup Guide

## What This Does
A 24/7 bot that monitors Pokemon Go official sources and sends you **instant phone notifications** via ntfy.sh — no Discord permissions, no PC always-on, nothing paid.

The bot runs as a **Render.com web service** (free tier) with a Flask health endpoint. You ping it every 3-5 minutes via BetterStack (free) to keep it awake.

## Quick Start

### 1. Deploy to Render.com (Free Web Service)
```bash
# Files needed:
# - pokemongo_announce_watcher.py
# - requirements.txt  (flask + requests)
# - render.yaml       (web service config)
# - SETUP.md          (this file)

# Push to GitHub, then:
1. Go to https://render.com → Sign up (GitHub)
2. Click "New" → "Web Service"
3. Connect your GitHub repo
4. Render auto-detects render.yaml
5. Click "Create Web Service"
```

### 2. Set Up BetterStack Keep-Alive Ping
1. Go to https://betterstack.com (free plan)
2. Create an Uptime Monitor → choose "HTTP"
3. URL: `https://your-app-name.onrender.com/health`
4. Set interval to **3 minutes** (or whatever you prefer)
5. This keeps the Render service awake indefinitely

### 3. Install ntfy App on Phone
- **Android**: [F-Droid](https://f-droid.org/packages/io.github.nntk5.ntfy/) or [Google Play](https://play.google.com/store/apps/details?id=io.github.nntk5.ntfy)
- Open ntfy → tap "+" → enter: `pokemongo-announcements` → Subscribe

## Files

| File | Purpose |
|------|---------|
| `pokemongo_announce_watcher.py` | Bot script (Flask health endpoint + RSS/HTML scrapers + ntfy relay) |
| `requirements.txt` | `flask` + `requests` |
| `render.yaml` | One-click deploy config for Render (web service, free tier) |
| `SETUP.md` | This file |

## What Gets Forwarded

### Sources monitored
1. **PokemonGoLive.com/en/news/** — official announcements (top 3 newest)
2. **Reddit /r/pokemongo RSS** — community-mirrored official posts (top 25)
3. **Serebii.net/pogo/** — news archive (if accessible)

### Notification content
Each ntfy notification contains:
- **Title**: Announcement headline (truncated to 80 chars)
- **Body**: Full headline + source + direct link to the article
- **Tap action**: Opens the full article in your browser

### Filters
**INCLUDE** (announcements): update, event, news, raid, mega, community day, season, go fest, maintenance, bug fix, etc.

**EXCLUDE** (noise): memes, discussion, shiny posts, IV talk, trade requests, "my day" posts, etc.

## Testing Locally
```bash
# One-time test sweep (prints what it WOULD send, doesn't send)
RUN_ONCE=1 python3 pokemongo_announce_watcher.py

# Full mode (runs Flask on :8080 + polling loop)
python3 pokemongo_announce_watcher.py
# Visit http://localhost:8080/health to verify Flask is alive
```

## Customization
Edit these values in `pokemongo_announce_watcher.py`:
- `NTFY_TOPIC` — your private notification channel (default: `pokemongo-announcements`)
- `POLL_INTERVAL` — seconds between checks (default: 300 = 5 min)
- `KEYWORDS` list — what counts as an announcement
- `NOISE` list — what to ignore
- `REDDIT_HEADERS["User-Agent"]` — Reddit sometimes blocks default UA

## Architecture
```
[ PokemonGoLive.com ] --scrape--> [ Your Bot on Render ]
[ Reddit r/pokemongo ]  --RSS--         |
[ Serebii.net ]      --scrape--       |--> ntfy.sh --> [ ntfy App on Phone ]
                    [ State: dedup cache ]            (push notification)
                    [ Flask: /health endpoint ]  <---- ping from BetterStack
```
