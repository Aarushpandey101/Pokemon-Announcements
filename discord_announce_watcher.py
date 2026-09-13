#!/usr/bin/env python3
"""
Discord Announcement Watcher
============================
Monitors your Discord server's announcement channel and forwards
new messages to ntfy.sh for instant phone notifications.

Runs on Render.com free tier (Flask + BetterStack keep-alike).
No web scraping — uses Discord API directly.

Setup:
1. Create a Discord bot application (https://discord.com/developers/applications)
2. Invite bot to your server with appropriate permissions
3. Set environment variables: DISCORD_TOKEN, DISCORD_CHANNEL_ID, NTFY_TOPIC
4. Deploy to Render.com
"""

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask

app = Flask(__name__)

# ---------------------------------------------------------------------------
# CONFIGURATION (from environment variables)
# ---------------------------------------------------------------------------

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")  # Your bot token
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "")  # Target channel ID
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "discord-announcements")  # ntfy topic
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))  # seconds between checks

STATE_FILE = Path(__file__).with_suffix(".state.json")

if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
    raise RuntimeError(
        "Missing Discord configuration. Set DISCORD_TOKEN and DISCORD_CHANNEL_ID environment variables."
    )

# ---------------------------------------------------------------------------
# STATE MANAGEMENT (dedup)
# ---------------------------------------------------------------------------


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {"seen": {}}
    return {"seen": {}}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def hash_entry(source: str, identifier: str) -> str:
    raw = f"{source}|{identifier}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DISCORD API HELPER
# ---------------------------------------------------------------------------


DISCORD_API_BASE = "https://discord.com/api/v10"


def discord_headers():
    return {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "User-Agent": "DiscordAnnouncementWatcher/1.0",
    }


def get_last_message_id() -> str:
    state = load_state()
    return state.get("last_message_id", "")


def set_last_message_id(msg_id: str):
    state = load_state()
    state["last_message_id"] = msg_id
    save_state(state)


# ---------------------------------------------------------------------------
# NTFY RELAY
# ---------------------------------------------------------------------------


def notify_ntfy(title: str, message: str, url: str = "") -> bool:
    body_parts = [f"**{title}**", message]
    if url:
        body_parts.append(url)
    body = "\n".join(body_parts)
    payload = body.encode("utf-8", errors="replace")

    # HTTP headers must be Latin-1 encodable. An em dash (or any non-ASCII
    # character) here throws an exception before the request is even sent —
    # that was silently eating every notification. Keep header text ASCII-only;
    # the UTF-8 body (payload) is fine with any character.
    headers = {
        "Title": f"DISCORD: {title[:80]}".encode("ascii", errors="replace").decode("ascii"),
        "Priority": "5",
        "Tags": "video_game",
        "Click": url,
    }
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=payload,
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"[NTFY] Sent: {title[:60]}")
            return True
        else:
            print(f"[NTFY] Error {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"[NTFY] Send failed: {e}")
        return False


# ---------------------------------------------------------------------------
# MAIN PROCESSING
# ---------------------------------------------------------------------------


def fetch_discord_announcements() -> list[dict]:
    announcements = []
    try:
        resp = requests.get(
            f"{DISCORD_API_BASE}/channels/{DISCORD_CHANNEL_ID}/messages?limit=5",
            headers=discord_headers(),
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[WARN] Discord API returned {resp.status_code}")
            return announcements

        messages = resp.json()
        if not isinstance(messages, list):
            return announcements

        for msg in messages:
            # NOTE: messages crossposted from a followed channel (or sent by
            # any bot/webhook, e.g. an announcement bot) have author.bot=True.
            # We WANT those, so we no longer skip bot-authored messages here.
            # If you ever add a bot of your own that posts into this same
            # channel and want to ignore its own messages, filter by comparing
            # msg["author"]["id"] to your bot's own user ID instead.

            content = msg.get("content", "").strip()
            if not content:
                continue

            clean_content = re.sub(r"\s+", " ", content).strip()

            identifier = f"{msg['id']}|{DISCORD_CHANNEL_ID}"

            announcements.append({
                "source": "Discord",
                "title": clean_content[:200],
                "url": f"https://discord.com/channels/{DISCORD_CHANNEL_ID}/{msg['id']}",
                "identifier": identifier,
                "full_content": content,
                "timestamp": msg.get("timestamp", ""),
            })

    except Exception as e:
        print(f"[ERROR] Discord fetch failed: {e}")
    return announcements


# ---------------------------------------------------------------------------
# MAIN PROCESSING LOOP
# ---------------------------------------------------------------------------


def main():
    print("=== Discord Announcement Watcher ===")
    print(f"Target: ntfy.sh/{NTFY_TOPIC}")
    print(f"Discord channel: {DISCORD_CHANNEL_ID}")
    print(f"Poll interval: {POLL_INTERVAL}s\n")

    state = load_state()
    seen: dict = state["seen"]
    last_msg_id = get_last_message_id()

    while True:
        try:
            announcements = fetch_discord_announcements()

            found_new = 0
            for entry in announcements:
                identifier = entry["identifier"]

                if identifier in seen:
                    continue

                if last_msg_id and entry["timestamp"] <= last_msg_id:
                    continue

                seen[identifier] = time.time()

                title = entry["title"][:80]
                url = entry["url"]
                message = f"via Discord — {entry['full_content'][:200]}"

                if notify_ntfy(title, message, url):
                    found_new += 1

            if announcements:
                last_msg_id = announcements[0]["timestamp"]
                set_last_message_id(last_msg_id)

            if len(seen) > 500:
                cut = len(seen) - 375
                for k in sorted(seen, key=lambda k: seen[k])[:cut]:
                    del seen[k]

            if found_new == 0:
                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}] No new announcements.")

            save_state(state)

        except Exception as e:
            print(f"[ERROR] Main loop crashed: {e}")

        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# FLASK HEALTH ENDPOINT
# ---------------------------------------------------------------------------


@app.route("/health")
@app.route("/")
def health():
    return "OK", 200


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if os.environ.get("RUN_ONCE"):
        print("=== TEST RUN (single sweep) ===\n")
        state = load_state()  # was missing — caused a NameError before any
                               # notification could be sent in this mode
        announcements = fetch_discord_announcements()
        found_new = 0

        for entry in announcements:
            identifier = entry["identifier"]
            if identifier in state["seen"]:
                continue
            title = entry["title"][:80]
            url = entry["url"]
            message = f"via Discord — {entry['full_content'][:200]}"
            if notify_ntfy(title, message, url):
                found_new += 1
                print(f"  [NEW] {title[:60]}")

        print(f"\n=== Total: {found_new} new entries ===")
        print(f"Seen cache: {len(state['seen'])} entries")
    else:
        port = int(os.environ.get("PORT", 8080))
        flask_thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=port, threaded=True),
            daemon=True,
        )
        flask_thread.start()
        print(f"Flask health endpoint: http://0.0.0.0:{port}/health")
        main()