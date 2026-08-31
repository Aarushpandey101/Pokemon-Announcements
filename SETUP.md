# Pokemon GO Announcement Watcher — Setup Guide

## What This Does
A 24/7 bot running on Render.com that monitors Pokemon Go official sources and sends
you instant phone notifications via ntfy.sh. No Discord permissions needed.

The bot runs as a **Flask web service** on Render (free tier) with a `/health`
endpoint that BetterStack pings every 3 minutes to keep it awake.

## Files
- `pokemongo_announce_watcher.py` — Main bot script (Flask + scrapers + ntfy relay)
- `requirements.txt` — Python dependencies (Flask + requests)
- `render.yaml` — Render.com auto-deploy configuration
- `SETUP.md` — This guide

## Setup Steps

### 1. Create GitHub Repo
```bash
git init
git add .
git commit -m "Pokemon GO announcement watcher"
git branch -M main
# Create repo at https://github.com/new
# Then follow GitHub's "push an existing repository" instructions
```

### 2. Deploy to Render
1. Go to https://render.com → sign up with GitHub
2. Click "New" → "Web Service"
3. Connect your GitHub repo
4. Render auto-detects render.yaml:
   - Name: pokemongo-announce-watcher
   - Build command: pip install -r requirements.txt
   - Start command: python3 pokemongo_announce_watcher.py
   - Health check path: /health
5. Click "Create Web Service"

### 3. Set Up BetterStack Keep-Alive
1. Go to https://betterstack.com → free signup
2. Create a new Monitor → choose "Web"
3. Name: `PKGO Watcher Keepalive`
4. URL: `https://your-app-name.onrender.com/health`
5. Monitoring interval: **3 minutes** (minimum free tier)
6. Region: same as Render (Oregon or Virginia)
7. Click "Create Monitor"

### 4. Install ntfy App on Phone
- **Android**: Install [ntfy app](https://play.google.com/store/apps/details?id=io.github.nntk5.ntfy)
  OR via [F-Droid](https://f-droid.org/packages/io.github.nntk5.ntfy/)
- Open ntfy → tap "+" → enter: `pokemongo-announcements` → Subscribe

### 5. You're Done!
- Every 5 minutes, your bot polls Pokemon Go sources
- New announcements → push notification to your phone
- BetterStack pings every 3 min → keeps Render service awake (free tier)

## Notifications Format
Each notification includes:
- **Title**: PKGO — [headline]
- **Body**: Announcement body with source + link
- **Tap**: Opens full article in browser
- **Priority**: High (5) — will buzz even on silent

## Testing
```bash
# Test scraping locally (no notifications sent)
RUN_ONCE=1 python3 pokemongo_announce_watcher.py

# Full run (Flask + polling loop)
python3 pokemongo_announce_watcher.py
# Then visit http://localhost:8080/health
```

## Troubleshooting
- **"Service unavailable"** on Render → Check Render logs for Python errors
- **No notifications** on phone → Verify ntfy app is subscribed to correct topic
- **Bot sleeping** → Make sure BetterStack monitor is pinging /health every 3 min
- **Too many notifications** → Bot uses SHA-256 dedup (same article won't repeat)
