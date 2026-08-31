#!/usr/bin/env python3
"""
Pokemon GO Announcement Watcher
===============================
Scrapes Pokemon Go announcements from multiple public sources and forwards
them to an ntfy.sh topic for instant phone notifications.
No Discord bot perms needed. No PC required to stay on.

Sources scraped:
- PokemonGoLive.com official news (HTML scraped — slugs + per-article titles)
- Reddit /r/pokemongo (Atom RSS — filtered for announcements)

Relayed to: ntfy.sh/pokemongo-announcements

Run locally:  python3 pokemongo_announce_watcher.py
Deploy to:   Render.com (free tier, no credit card needed)
"""

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests
from flask import Flask

app = Flask(__name__)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

NTFY_TOPIC = "pokemongo-announcements"   # phone subscribes to this
NTFY_PRIORITY = "5"                     # 1 (lowest) .. 5 (highest)
POLL_INTERVAL = 300                     # 5 minutes between checks
STATE_FILE = Path(__file__).with_suffix(".state.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/127.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) "
                  "Gecko/20100101 Firefox/115.0",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# FILTERS
# ---------------------------------------------------------------------------

# Sources that are HIGH-CONFIDENCE announcement feeds (always include regardless of keyword match)
HIGH_CONFIDENCE_SOURCES = {"Pokemon GO Live"}

# Keywords that indicate this is a real announcement (not random content)
KEYWORDS = [
    "announcement", "update", "news", "event", "launch", "release",
    "community day", "raid day", "raid hour", "ex raid", "go battle league",
    "season ", "go fest", "maintenance", "patch note", "bug fix",
    "mega evolution", "mega", "primal", "origin raid", "ultra beast",
    "mewtwo", "celebi", "mew ", "rayquaza", "groudon", "kyogre",
    "jirachi", "deoxys", "phione", "manaphy",
    "august", "july", "september", "october", "november", "december",
    "january", "february", "march", "april", "june",
    "hatch day", "research day", "encounter",
    "twilight", "finale", "celebration", "marathon", "rally",
    "championship", "gadget", "quest", "festival", "hatchathon",
    "team rocket", "shadow", "purified",
]

# Substrings that indicate noise we should skip
NOISE = [
    "spoiler","discussion","question","help",
    "iv","cp","trade","raid invite","looking for","lfg",
    "shundo","hundo","nundo","iv check",
    "my day","lmao","imagine","payed",
    "passed away","rest in peace","rip",
    "complaint","entitled","lured","shiny",
]

def contains_keyword(title: str, source: str = "") -> bool:
    """Check if title is an announcement. High-confidence sources bypass keyword check."""
    if source in HIGH_CONFIDENCE_SOURCES:
        return True
    tl = title.lower()
    return any(k in tl for k in KEYWORDS) and not any(n in tl for n in NOISE)


# ---------------------------------------------------------------------------
# SCRAPERS
# ---------------------------------------------------------------------------

def scrape_pokemongolive() -> list[dict]:
    """
    Scrape official Pokemon GO Live news index for article slugs,
    then fetch each article page for its real title.
    """
    results = []
    try:
        resp = requests.get(
            "https://pokemongolive.com/en/news/",
            headers=HEADERS,
            timeout=12,
        )
        resp.raise_for_status()
        html = resp.text

        # Extract the LATEST 3 article slugs (newest first)
        slugs = re.findall(r'href="/news/([a-z0-9\-_]+)"', html)[:3]
        seen_slugs = set()

        for slug in slugs:
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            article_url = f"https://pokemongolive.com/news/{slug}/"

            title = slug.replace("-", " ").replace("_", " ").title()
            try:
                art = requests.get(article_url, headers=HEADERS, timeout=5)
                if art.status_code == 200:
                    title_match = re.search(r'<title>([^<]+)', art.text)
                    if title_match:
                        title = unescape(title_match.group(1))
                        # Strip " — Pokémon GO" suffix
                        title = re.sub(r' — Pokemon GO$', '', title, flags=re.IGNORECASE)
                        title = title.strip()
            except Exception:
                pass  # fallback to slug-based title

            if contains_keyword(title, "Pokemon GO Live"):
                results.append({
                    "source": "Pokemon GO Live",
                    "title": title,
                    "url": article_url,
                })
    except Exception as e:
        print(f"[WARN] pokemongolive scrape failed: {e}")
    return results


def scrape_serebii() -> list[dict]:
    """Scrape Serebii.net/pogo/ for recent news archive links."""
    results = []
    try:
        resp = requests.get("https://serebii.net/pogo/", headers=HEADERS, timeout=12)
        resp.raise_for_status()
        html = resp.text
        # Serebii pogo news archive links: /pogo/news/YYYYMMDD.shtml
        links = re.findall(r'href="(/pogo/news/\d+\.shtml)"', html)
        seen = set()
        for link in sorted(set(links)):
            if link in seen:
                continue
            seen.add(link)
            url = urljoin("https://serebii.net", link)
            date_match = re.search(r'(\d{8})', link)
            title = "Serebii Pokemon GO News"
            if date_match:
                try:
                    d = datetime.strptime(date_match.group(1), "%Y%m%d")
                    title = f"Serebii Pokemon GO — {d.strftime('%b %d, %Y')}"
                except Exception:
                    pass
            results.append({
                "source": "Serebii.net",
                "title": title,
                "url": url,
            })
    except Exception as e:
        print(f"[WARN] serebii scrape failed: {e}")
    return results


def scrape_reddit() -> list[dict]:
    """
    Scrape Reddit r/pokemongo RSS (Atom) — filter for announcement-like titles.
    Uses raw XML parsing (no feedparser dependency).
    """
    results = []
    try:
        resp = requests.get(
            "https://www.reddit.com/r/pokemongo/.rss?limit=25",
            headers=REDDIT_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall(".//atom:entry", ns)
        for entry in entries:
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            updated_el = entry.find("atom:updated", ns) or entry.find("atom:published", ns)
            if title_el is None or link_el is None:
                continue
            title = unescape(title_el.text or "")
            url = link_el.get("href", "")
            # Skip pinned/distinguished posts that are just discussions
            if not contains_keyword(title, "Reddit r/pokemongo"):
                continue
            results.append({
                "source": "Reddit r/pokemongo",
                "title": title.strip(),
                "url": url,
                "updated": updated_el.text if updated_el is not None else "",
            })
    except ET.ParseError:
        # Regex fallback
        try:
            resp = requests.get(
                "https://www.reddit.com/r/pokemongo/.rss?limit=25",
                headers=REDDIT_HEADERS, timeout=15)
            titles = re.findall(r'<title>(.*?)</title>', resp.text)
            urls = re.findall(r'<link[^>]*href="([^"]+)"', resp.text)
            for t, u in zip(titles[1:], urls[1:]):
                title = unescape(t)
                url = u.split("?")[0]
                if contains_keyword(title, "Reddit r/pokemongo"):
                    results.append({
                        "source": "Reddit r/pokemongo",
                        "title": title.strip(),
                        "url": url,
                    })
        except Exception as e:
            print(f"[WARN] reddit regex fallback failed: {e}")
    except Exception as e:
        print(f"[WARN] reddit scrape failed: {e}")
    return results


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


def hash_entry(source: str, title: str, url: str) -> str:
    raw = f"{source}|{title}|{url}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# NTFY RELAY
# ---------------------------------------------------------------------------

def notify_ntfy(source: str, title: str, url: str, updated: str = ""):
    """Send a notification to ntfy.sh."""
    body_parts = [f"**{title}**", f"via {source}"]
    if updated:
        body_parts.append(f"Posted: {updated}")
    body_parts.append(url)
    body = "\n".join(body_parts)
    payload = body.encode("utf-8", errors="replace")

    headers = {
        "Title": f"PKGO — {title[:80]}",
        "Priority": NTFY_PRIORITY,
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
        else:
            print(f"[NTFY] Error {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[NTFY] Send failed: {e}")


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------

def process_entries(entries: list[dict], seen: dict, send: bool = True) -> int:
    """Process a batch of entries — dedup, filter, optionally send."""
    found_new = 0
    for entry in entries:
        h = hash_entry(entry["source"], entry["title"], entry["url"])
        if h in seen:
            continue
        if not contains_keyword(entry["title"], entry["source"]):
            continue
        seen[h] = time.time()
        if send:
            notify_ntfy(
                entry["source"],
                entry["title"],
                entry["url"],
                entry.get("updated", ""),
            )
        found_new += 1
    return found_new


def main():
    print("=== Pokemon GO Announcement Watcher ===")
    print(f"Target: ntfy.sh/{NTFY_TOPIC}")
    print(f"Poll interval: {POLL_INTERVAL}s\n")

    state = load_state()
    seen: dict = state["seen"]

    while True:
        found_new = 0
        for src_key, scraper in [
            ("pokemongolive", scrape_pokemongolive),
            ("serebii", scrape_serebii),
            ("reddit", scrape_reddit),
        ]:
            try:
                entries = scraper()
            except Exception as e:
                print(f"[ERROR] {src_key} crashed: {e}")
                entries = []
            found_new += process_entries(entries, seen)

        # Prune old hashes (keep last 500)
        if len(seen) > 500:
            cut = len(seen) - 375
            for k in sorted(seen, key=lambda k: seen[k])[:cut]:
                del seen[k]

        if found_new == 0:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] No new announcements found.")
        save_state(state)
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# FLASK HEALTH ENDPOINT (for BetterStack/Render pings)
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return "OK", 200


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # If RUN_ONCE=1, do one sweep and report (for testing, no ntfy send)
    if os.environ.get("RUN_ONCE"):
        print("=== TEST RUN (single sweep, no notifications) ===\n")
        state = load_state()
        seen = state["seen"]

        for src_key, scraper in [
            ("pokemongolive", scrape_pokemongolive),
            ("serebii", scrape_serebii),
            ("reddit", scrape_reddit),
        ]:
            print(f"\n--- Checking {src_key} ---")
            try:
                entries = scraper()
            except Exception as e:
                print(f"  ERROR: {e}")
                entries = []
            new = process_entries(entries, seen, send=False)
            if new > 0:
                for entry in entries:
                    h = hash_entry(entry["source"], entry["title"], entry["url"])
                    if h not in seen or time.time() - seen.get(h, 0) < 5:
                        print(f"  [NEW] [{entry['source']}] {entry['title'][:80]}")
            else:
                print("  No new announcements.")

        print(f"\nTotal new entries this sweep: {sum(1 for v in state['seen'].values())}")
    else:
        # Start Flask in a background thread for health checks (keeps Render alive)
        port = int(os.environ.get("PORT", 8080))
        flask_thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=port, threaded=True),
            daemon=True,
        )
        flask_thread.start()
        print(f"Flask health endpoint: http://0.0.0.0:{port}/health")
        # Run the polling loop in the main thread
        main()
